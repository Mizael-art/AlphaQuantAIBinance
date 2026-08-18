import random
from datetime import datetime, timedelta, timezone

from alphaquant_core.engines.data_engine import Candle


class FakeClient:
    def __init__(self, candles):
        self._candles = candles

    def get_klines(self, symbol, timeframe, limit=200):
        return self._candles[-limit:]


def _synthetic_uptrend_candles(n: int = 220) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = 100.0
    rng = random.Random(42)
    candles = []
    for i in range(n):
        price += rng.uniform(-0.5, 1.2)
        candles.append(
            Candle(
                timestamp=base + timedelta(hours=i),
                open=price,
                high=price + rng.uniform(0, 1.5),
                low=price - rng.uniform(0, 1.5),
                close=price + rng.uniform(-0.5, 0.5),
                volume=rng.uniform(100, 500),
            )
        )
    return candles


def test_analyze_asset_persists_candles_and_returns_indicators(db_session):
    from alphaquant_core.engines.orchestrator import analyze_asset

    candles = _synthetic_uptrend_candles()
    result = analyze_asset(db_session, symbol="BTCUSDT", timeframe="1h", client=FakeClient(candles), limit=200)

    assert result["asset"] == "BTCUSDT"
    assert result["candles_stored"] == 200
    assert result["indicators"]["ema200"] is not None
    assert result["structure"]["regime"] in {"BULLISH", "BEARISH", "UNDEFINED"}


def test_analyze_asset_is_idempotent_on_same_candles(db_session):
    import sqlalchemy as sa

    from alphaquant_core.db.models import Asset, Candle
    from alphaquant_core.engines.orchestrator import analyze_asset

    candles = _synthetic_uptrend_candles()
    analyze_asset(db_session, symbol="ETHUSDT", timeframe="1h", client=FakeClient(candles), limit=200)
    analyze_asset(db_session, symbol="ETHUSDT", timeframe="1h", client=FakeClient(candles), limit=200)

    count = db_session.execute(
        sa.select(sa.func.count())
        .select_from(Candle)
        .join(Asset, Asset.id == Candle.asset_id)
        .where(Asset.symbol == "ETHUSDT")
    ).scalar()
    assert count == 200  # não duplicou ao reprocessar os mesmos timestamps


def test_get_or_create_asset_does_not_duplicate(db_session):
    from alphaquant_core.services.candle_service import get_or_create_asset

    a1 = get_or_create_asset(db_session, "BTCUSDT")
    a2 = get_or_create_asset(db_session, "btcusdt")  # case-insensitive

    assert a1.id == a2.id
