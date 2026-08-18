from alphaquant_core.db.models import DecisionResult, Opportunity, OpportunityStatus
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


def test_future_opportunity_persisted_for_unmatched_playbook_with_direction(db_session):
    df = uptrend_pullback_to_ema50()
    _ctx, results, opportunities = scan_and_score(db_session, "FUTUREUSDT", "1h", client=FakeClient(df))

    future_results = [r for r in results if not r.matched and r.direction is not None and r.progress > 0]
    assert future_results  # a fixture produz pelo menos um playbook parcialmente formado

    future_names = {r.playbook for r in future_results}
    persisted_future = [o for o in opportunities if o.playbook in future_names]
    assert persisted_future

    for opp in persisted_future:
        assert opp.status == OpportunityStatus.FORMATION
        assert opp.decision is None
        assert opp.entry is None and opp.stop is None and opp.rr is None
        assert 0.0 <= opp.progress <= 100.0
        assert opp.audit_snapshot["quality_filter"] is None
        assert opp.audit_snapshot["decision"] is None


def test_future_opportunity_never_persisted_without_direction(db_session):
    """Um playbook sem direção definida (ex.: EMAs sem alinhamento) não é uma 'oportunidade futura' — é ruído."""
    from alphaquant_core.playbooks.base import Direction, PlaybookResult
    from alphaquant_core.playbooks.engine import build_context
    from alphaquant_core.engines.scoring import compute_score
    from alphaquant_core.services.opportunity_service import upsert_future_opportunity

    df = uptrend_pullback_to_ema50()
    ctx = build_context("NODIRUSDT", "1h", df)
    result_no_direction = PlaybookResult(playbook="X", matched=False, direction=None, progress=50.0)
    score = compute_score(ctx, result_no_direction, None)

    opp = upsert_future_opportunity(db_session, ctx, result_no_direction, score)
    assert opp is None


def test_future_opportunity_never_overwrites_confirmed_or_invalidated(db_session):
    """
    Uma Opportunity que já virou CONFIRMED/INVALIDATED pelo pipeline
    completo não pode ser 'rebaixada' de volta por uma leitura parcial
    (matched=False) de um ciclo seguinte.
    """
    df = uptrend_pullback_to_ema50()
    _ctx, results, opportunities = scan_and_score(
        db_session, "PROTECTEDUSDT", "1h", client=FakeClient(df), htf_regime="BULLISH",
    )
    confirmed = [o for o in opportunities if o.decision is not None]
    assert confirmed

    target = confirmed[0]
    original_status = target.status
    original_decision = target.decision

    # tenta "rebaixar" via caminho de Future Opportunity diretamente
    from alphaquant_core.playbooks.base import Direction as PBDirection
    from alphaquant_core.playbooks.base import PlaybookResult
    from alphaquant_core.playbooks.engine import build_context
    from alphaquant_core.engines.scoring import compute_score
    from alphaquant_core.services.opportunity_service import upsert_future_opportunity

    ctx = build_context(target.asset, target.timeframe, df)
    fake_partial_result = PlaybookResult(
        playbook=target.playbook, matched=False,
        direction=PBDirection(target.direction.value), progress=50.0,
    )
    score = compute_score(ctx, fake_partial_result, None)

    result = upsert_future_opportunity(db_session, ctx, fake_partial_result, score)
    assert result is None  # recusa mexer

    db_session.refresh(target)
    assert target.status == original_status
    assert target.decision == original_decision


def test_future_opportunity_updates_same_row_across_cycles(db_session):
    df = uptrend_pullback_to_ema50()
    _ctx1, results1, opportunities1 = scan_and_score(db_session, "REPEATUSDT", "1h", client=FakeClient(df))
    future_names = {r.playbook for r in results1 if not r.matched and r.direction is not None and r.progress > 0}
    first_ids = sorted(o.id for o in opportunities1 if o.playbook in future_names)
    assert first_ids

    _ctx2, results2, opportunities2 = scan_and_score(db_session, "REPEATUSDT", "1h", client=FakeClient(df))
    second_ids = sorted(o.id for o in opportunities2 if o.playbook in future_names)

    assert first_ids == second_ids  # mesma linha reaproveitada, não duplicou

    total = db_session.query(Opportunity).filter_by(asset="REPEATUSDT").count()
    assert total == len(opportunities1)  # nada foi duplicado na segunda rodada


def test_future_opportunity_becomes_invalidated_when_progress_drops_to_zero(db_session):
    """
    Seção 18 — SETUP INVALIDADO: um setup em formação que perde as
    condições do playbook precisa virar INVALIDATED, não ficar parado em
    FORMATION para sempre.
    """
    from alphaquant_core.engines.scoring import compute_score
    from alphaquant_core.playbooks.base import Direction as PBDirection
    from alphaquant_core.playbooks.base import PlaybookResult
    from alphaquant_core.playbooks.engine import build_context
    from alphaquant_core.services.opportunity_service import upsert_future_opportunity

    df = uptrend_pullback_to_ema50()
    ctx = build_context("FADEUSDT", "1h", df)

    forming = PlaybookResult(playbook="Compression Breakout", matched=False, direction=PBDirection.LONG, progress=65.0)
    score1 = compute_score(ctx, forming, None)
    created = upsert_future_opportunity(db_session, ctx, forming, score1)
    assert created is not None
    assert created.status == OpportunityStatus.FORMATION

    faded = PlaybookResult(playbook="Compression Breakout", matched=False, direction=PBDirection.LONG, progress=0.0)
    score2 = compute_score(ctx, faded, None)
    invalidated = upsert_future_opportunity(db_session, ctx, faded, score2)

    assert invalidated is not None
    assert invalidated.id == created.id  # mesma linha, não duplicou
    assert invalidated.status == OpportunityStatus.INVALIDATED
    assert invalidated.invalidated_at is not None
    assert invalidated.audit_snapshot["quality_filter"]["approved"] is False
    assert "progress" in invalidated.audit_snapshot["quality_filter"]["reasons"][0].lower() or \
           "condições" in invalidated.audit_snapshot["quality_filter"]["reasons"][0].lower()


def test_future_opportunity_invalidation_message_renders_correctly(db_session):
    """O formatador de INVALIDATION precisa funcionar também para setups que nunca passaram pelo Decision Engine."""
    from alphaquant_core.engines.scoring import compute_score
    from alphaquant_core.playbooks.base import Direction as PBDirection
    from alphaquant_core.playbooks.base import PlaybookResult
    from alphaquant_core.playbooks.engine import build_context
    from alphaquant_core.services.opportunity_service import upsert_future_opportunity
    from alphaquant_core.telegram.formatting import format_invalidation_message

    df = uptrend_pullback_to_ema50()
    ctx = build_context("FADEMSGUSDT", "1h", df)

    forming = PlaybookResult(playbook="Compression Breakout", matched=False, direction=PBDirection.LONG, progress=65.0)
    upsert_future_opportunity(db_session, ctx, forming, compute_score(ctx, forming, None))

    faded = PlaybookResult(playbook="Compression Breakout", matched=False, direction=PBDirection.LONG, progress=0.0)
    invalidated = upsert_future_opportunity(db_session, ctx, faded, compute_score(ctx, faded, None))

    text = format_invalidation_message(invalidated)
    assert "SETUP INVALIDADO" in text
    assert "REPROVADO" in text
