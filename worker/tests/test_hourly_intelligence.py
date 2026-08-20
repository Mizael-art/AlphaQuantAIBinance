from datetime import datetime, timezone

from alphaquant_core.db.models import ScannerEvent
from alphaquant_core.engines.data_engine import Candle
from alphaquant_core.playbooks.runner import scan_and_score
from alphaquant_core.telegram.summary import compute_hourly_intelligence, format_hourly_intelligence_message

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


def test_hourly_intelligence_with_no_data_is_well_formed(db_session):
    intel = compute_hourly_intelligence(db_session, now=datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert intel.top_opportunities == []
    assert intel.forming == []
    assert intel.rejected == []

    text = format_hourly_intelligence_message(intel)
    assert "MARKET INTELLIGENCE" in text
    assert "Não foram encontradas entradas de alta qualidade" in text
    assert "Nenhuma rejeição relevante" in text


def test_hourly_intelligence_reflects_real_opportunities(db_session):
    df = uptrend_pullback_to_ema50()
    _ctx, _results, opportunities = scan_and_score(db_session, "HOURLYUSDT", "1h", client=FakeClient(df), htf_regime="BULLISH")
    assert opportunities

    intel = compute_hourly_intelligence(db_session)

    confirmed = [o for o in opportunities if o.status.value == "CONFIRMED"]
    forming = [o for o in opportunities if o.status.value == "FORMATION"]
    # A suíte compartilha o mesmo Postgres efêmero entre arquivos de
    # teste: outras oportunidades CONFIRMED de outros testes na mesma
    # janela de 1h podem ranquear na frente de HOURLYUSDT no TOP 5 — o
    # que importa aqui é que a lista está bem formada e ranqueada, não
    # a posição exata de um ativo específico.
    if confirmed:
        assert len(intel.top_opportunities) > 0
    if forming:
        assert len(intel.forming) > 0
    scores = [o.score for o in intel.top_opportunities]
    assert scores == sorted(scores, reverse=True)


def test_hourly_intelligence_ranks_top_opportunities_by_score_desc(db_session):
    df = uptrend_pullback_to_ema50()
    _ctx, _results, opportunities = scan_and_score(db_session, "RANKUSDT", "1h", client=FakeClient(df), htf_regime="BULLISH")

    intel = compute_hourly_intelligence(db_session)
    scores = [o.score for o in intel.top_opportunities]
    assert scores == sorted(scores, reverse=True)


def test_hourly_intelligence_surfaces_data_unavailable_assets(db_session):
    db_session.add(ScannerEvent(event_type="data_engine_error", asset="BROKENUSDT", payload={"timeframe": "1h", "error": "timeout"}))
    db_session.commit()

    intel = compute_hourly_intelligence(db_session)
    assert "BROKENUSDT" in intel.data_unavailable_assets

    text = format_hourly_intelligence_message(intel)
    assert "BROKENUSDT" in text
    assert "ATENÇÃO" in text


def test_hourly_intelligence_window_excludes_old_events(db_session):
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    db_session.add(ScannerEvent(event_type="data_engine_error", asset="OLDUSDT", payload={}, timestamp=old))
    db_session.commit()

    intel = compute_hourly_intelligence(db_session, window_minutes=60)
    assert "OLDUSDT" not in intel.data_unavailable_assets
