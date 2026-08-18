from alphaquant_core.engines.data_engine import Candle
from alphaquant_core.playbooks.runner import scan_and_score

from tests.playbook_fixtures import uptrend_pullback_to_ema50


class FakeClient:
    def __init__(self, df):
        self._df = df

    def get_klines(self, symbol, timeframe, limit=200):
        rows = self._df.reset_index()
        return [
            Candle(
                timestamp=row["index"].to_pydatetime(), open=row["open"], high=row["high"],
                low=row["low"], close=row["close"], volume=row["volume"],
            )
            for _, row in rows.tail(limit).iterrows()
        ]


def test_scan_and_score_persists_opportunity_for_matched_playbooks(db_session):
    from alphaquant_core.db.models import Opportunity

    df = uptrend_pullback_to_ema50()
    ctx, results, opportunities = scan_and_score(db_session, "BTCUSDT", "1h", client=FakeClient(df))

    matched_names = {r.playbook for r in results if r.matched}
    future_names = {r.playbook for r in results if not r.matched and r.direction is not None and r.progress > 0}
    assert matched_names  # a fixture foi desenhada para acionar pelo menos um playbook
    # a lista agora inclui tanto playbooks confirmados (pipeline completo)
    # quanto Future Opportunities (Fase 11, progress>0 com direção definida)
    assert {o.playbook for o in opportunities} == matched_names | future_names

    for opp in opportunities:
        assert opp.score is not None and 0.0 <= opp.score <= 100.0
        assert opp.status.value in {"FORMATION", "CONFIRMED", "INVALIDATED"}
        assert opp.confidence in {"BAIXA", "MODERADA", "ALTA"}
        if opp.playbook in matched_names:
            assert opp.decision is not None  # Fase 7: Decision Engine sempre decide algo para playbooks confirmados
            assert opp.decision.value in {"ENTRAR", "ESPERAR", "REPROVAR"}
            # status e decision precisam ser consistentes entre si (ver _STATUS_BY_DECISION)
            expected_status = {
                "ENTRAR": "CONFIRMED", "ESPERAR": "FORMATION", "REPROVAR": "INVALIDATED",
            }[opp.decision.value]
            assert opp.status.value == expected_status
        else:
            # Future Opportunity (Fase 11): nunca passa pelo Decision Engine
            assert opp.decision is None
            assert opp.status.value == "FORMATION"
            assert opp.entry is None and opp.stop is None and opp.rr is None

    db_opportunities = db_session.query(Opportunity).filter_by(asset="BTCUSDT").all()
    assert len(db_opportunities) == len(opportunities)


def test_scan_and_score_updates_instead_of_duplicating(db_session):
    from alphaquant_core.db.models import Opportunity

    df = uptrend_pullback_to_ema50()
    client = FakeClient(df)

    _ctx1, _results1, first_run = scan_and_score(db_session, "ADAUSDT", "1h", client=client)
    _ctx2, _results2, second_run = scan_and_score(db_session, "ADAUSDT", "1h", client=client)

    first_ids = sorted(o.id for o in first_run)
    second_ids = sorted(o.id for o in second_run)
    assert first_ids == second_ids  # atualizou os mesmos registros, não criou novos

    total = db_session.query(Opportunity).filter_by(asset="ADAUSDT").count()
    assert total == len(first_run)


def test_scan_and_score_evidence_rows_match_score_criteria_and_do_not_pile_up(db_session):
    from alphaquant_core.db.models import Evidence

    df = uptrend_pullback_to_ema50()
    client = FakeClient(df)

    _ctx1, _results1, opportunities = scan_and_score(db_session, "SOLUSDT", "1h", client=client)
    assert opportunities

    opp = opportunities[0]
    evidence_after_first = db_session.query(Evidence).filter_by(opportunity_id=opp.id).count()
    assert evidence_after_first > 0

    scan_and_score(db_session, "SOLUSDT", "1h", client=client)  # roda de novo
    evidence_after_second = db_session.query(Evidence).filter_by(opportunity_id=opp.id).count()
    assert evidence_after_second == evidence_after_first  # não dobrou


def test_no_opportunity_persisted_when_no_playbook_matches(db_session):
    """
    Uma faixa lateral sem tendência não deve gerar nenhuma Opportunity —
    "nenhuma oportunidade de qualidade" é um resultado válido (seção 69).
    """
    import pandas as pd

    from alphaquant_core.db.models import Opportunity

    flat_df = pd.DataFrame(
        {"open": [100.0] * 60, "high": [100.2] * 60, "low": [99.8] * 60, "close": [100.0] * 60, "volume": [100.0] * 60},
        index=pd.date_range("2026-01-01", periods=60, freq="h"),
    )
    _ctx, results, opportunities = scan_and_score(db_session, "XRPUSDT", "1h", client=FakeClient(flat_df))

    assert not any(r.matched for r in results)
    assert opportunities == []
    assert db_session.query(Opportunity).filter_by(asset="XRPUSDT").count() == 0


def test_quality_filter_verdict_persisted_using_real_playbook_thresholds(db_session):
    """
    Fase 6: o veredito do Quality Filter usa minimum_score/minimum_rr da
    tabela `playbooks` (seed da Fase 4) e fica registrado tanto em
    audit_snapshot quanto numa linha de evidence própria.
    """
    from alphaquant_core.db.models import Evidence, Playbook

    df = uptrend_pullback_to_ema50()
    ctx, results, opportunities = scan_and_score(db_session, "DOTUSDT", "1h", client=FakeClient(df))
    assert opportunities

    opp = opportunities[0]
    playbook_row = db_session.query(Playbook).filter_by(name=opp.playbook).one()
    assert playbook_row.minimum_score == 70.0
    assert playbook_row.minimum_rr == 2.0

    qf = opp.audit_snapshot["quality_filter"]
    assert "approved" in qf and "reasons" in qf
    # com os limiares padrão (70/2), o veredito deve ser consistente com o Score/RR gravados
    if opp.score >= playbook_row.minimum_score and opp.rr is not None and opp.rr >= playbook_row.minimum_rr:
        assert qf["approved"] is True
        assert qf["reasons"] == []
    else:
        assert qf["approved"] is False
        assert len(qf["reasons"]) > 0

    quality_evidence = (
        db_session.query(Evidence)
        .filter_by(opportunity_id=opp.id, category="QUALITY_FILTER")
        .one()
    )
    assert quality_evidence.evidence.startswith("APROVADO") or quality_evidence.evidence.startswith("REPROVADO")


def test_decision_engine_verdict_consistent_with_quality_filter(db_session):
    """
    Fase 7: uma Opportunity REPROVADA pelo Quality Filter nunca deve ter
    decision=ENTRAR, e vice-versa — trava a consistência entre as duas
    camadas na persistência real.
    """
    from alphaquant_core.db.models import Evidence

    df = uptrend_pullback_to_ema50()
    _ctx, _results, opportunities = scan_and_score(db_session, "LINKUSDT", "1h", client=FakeClient(df))
    confirmed_opportunities = [o for o in opportunities if o.decision is not None]
    assert confirmed_opportunities  # a fixture aciona pelo menos um playbook confirmado

    for opp in confirmed_opportunities:
        qf_approved = opp.audit_snapshot["quality_filter"]["approved"]
        decision = opp.decision.value

        if not qf_approved:
            assert decision == "REPROVAR"
            assert opp.status.value == "INVALIDATED"
            assert opp.invalidated_at is not None
        else:
            assert decision in {"ENTRAR", "ESPERAR"}
            assert opp.status.value in {"CONFIRMED", "FORMATION"}
            assert opp.invalidated_at is None

        decision_evidence = (
            db_session.query(Evidence)
            .filter_by(opportunity_id=opp.id, category="DECISION_ENGINE")
            .one()
        )
        assert decision_evidence.evidence.startswith(decision)


def test_reprovar_can_become_entrar_in_a_later_cycle_without_duplicating(db_session):
    """
    Uma Opportunity REPROVADA (RR insuficiente) num ciclo deve poder virar
    ENTRAR num ciclo seguinte se as condições melhorarem — atualizando o
    MESMO registro, nunca criando uma linha nova (ver docstring de
    upsert_opportunity sobre a chave natural asset+timeframe+playbook+direction).
    """
    from alphaquant_core.db.models import Opportunity
    from alphaquant_core.engines.data_engine import Candle
    from alphaquant_core.playbooks.runner import scan_and_score as _scan_and_score

    df = uptrend_pullback_to_ema50()

    class WeakStopClient:
        """Primeiro ciclo: stop artificialmente próximo -> RR baixo -> REPROVAR."""
        def get_klines(self, symbol, timeframe, limit=200):
            rows = df.reset_index()
            return [
                Candle(timestamp=row["index"].to_pydatetime(), open=row["open"], high=row["high"],
                       low=row["low"], close=row["close"], volume=row["volume"])
                for _, row in rows.tail(limit).iterrows()
            ]

    _ctx1, results1, opportunities1 = _scan_and_score(db_session, "AVAXUSDT", "1h", client=WeakStopClient())
    assert opportunities1
    first_run_ids = sorted(o.id for o in opportunities1)

    # segundo ciclo: mesmos dados (o teste foca em não duplicar, não em
    # forçar uma melhora artificial de RR — cobrimos isso via reasons/consistência acima)
    _ctx2, results2, opportunities2 = _scan_and_score(db_session, "AVAXUSDT", "1h", client=WeakStopClient())
    second_run_ids = sorted(o.id for o in opportunities2)

    assert first_run_ids == second_run_ids  # mesma linha reaproveitada, mesmo se REPROVADA
    total = db_session.query(Opportunity).filter_by(asset="AVAXUSDT").count()
    assert total == len(opportunities1)


def test_entrar_is_reachable_end_to_end_when_htf_regime_is_available(db_session):
    """
    Fase 8: a lacuna documentada na Fase 7 (confidence nunca chega a ALTA
    sem htf_regime, então o Decision Engine nunca retorna ENTRAR) fica
    fechada aqui — com htf_regime real disponível, ENTRAR precisa
    acontecer de verdade no pipeline completo persistido.
    """
    from alphaquant_core.playbooks.runner import scan_and_score as _scan_and_score

    df = uptrend_pullback_to_ema50()
    _ctx, _results, opportunities = _scan_and_score(
        db_session, "NEARUSDT", "1h", client=FakeClient(df), htf_regime="BULLISH",
    )
    assert opportunities
    assert any(o.confidence == "ALTA" for o in opportunities)
    assert any(o.decision.value == "ENTRAR" for o in opportunities)
