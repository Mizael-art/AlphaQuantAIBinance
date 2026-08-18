from alphaquant_core.engines.data_engine import Candle
from alphaquant_core.playbooks.runner import compute_htf_regime, htf_timeframe_for

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


def test_htf_timeframe_mapping():
    assert htf_timeframe_for("15m") == "4h"
    assert htf_timeframe_for("1h") == "4h"
    assert htf_timeframe_for("4h") == "1d"
    assert htf_timeframe_for("1d") is None
    assert htf_timeframe_for("unknown") is None


def test_compute_htf_regime_returns_none_when_no_htf_configured(db_session):
    result = compute_htf_regime(db_session, "BTCUSDT", None)
    assert result is None


def test_compute_htf_regime_computes_real_regime(db_session):
    df = uptrend_pullback_to_ema50()
    regime = compute_htf_regime(db_session, "BTCUSDT", "4h", client=FakeClient(df))
    assert regime in {"BULLISH", "BEARISH", "UNDEFINED"}


def test_compute_htf_regime_persists_candles_for_the_htf_timeframe(db_session):
    import sqlalchemy as sa

    from alphaquant_core.db.models import Asset, Candle as CandleModel

    df = uptrend_pullback_to_ema50()
    compute_htf_regime(db_session, "MATICUSDT", "4h", client=FakeClient(df))

    count = db_session.execute(
        sa.select(sa.func.count())
        .select_from(CandleModel)
        .join(Asset, Asset.id == CandleModel.asset_id)
        .where(Asset.symbol == "MATICUSDT", CandleModel.timeframe == "4h")
    ).scalar()
    assert count > 0
