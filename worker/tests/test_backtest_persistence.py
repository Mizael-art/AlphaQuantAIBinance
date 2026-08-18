from alphaquant_core.db.models import Backtest
from alphaquant_core.engines.data_engine import Candle
from alphaquant_core.playbooks.backtest_runner import load_candles_df, run_and_save_backtest
from alphaquant_core.playbooks.trend_continuation import TrendContinuationEMA50
from alphaquant_core.services.candle_service import get_or_create_asset, upsert_candles

from tests.backtest_fixtures import long_zigzag_uptrend


def _persist_synthetic_candles(db_session, symbol: str) -> int:
    df = long_zigzag_uptrend()
    candles = [
        Candle(
            timestamp=ts.to_pydatetime(), open=float(row.open), high=float(row.high),
            low=float(row.low), close=float(row.close), volume=float(row.volume),
        )
        for ts, row in df.iterrows()
    ]
    asset = get_or_create_asset(db_session, symbol)
    return upsert_candles(db_session, asset.id, "1h", candles)


def test_load_candles_df_reads_back_persisted_candles(db_session):
    stored = _persist_synthetic_candles(db_session, "BACKTESTLOADUSDT")
    assert stored > 0

    df = load_candles_df(db_session, "BACKTESTLOADUSDT", "1h")
    assert len(df) == stored
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].dtype == float


def test_load_candles_df_empty_for_unknown_asset(db_session):
    df = load_candles_df(db_session, "NOPE_NEVER_SEEDED", "1h")
    assert len(df) == 0


def test_run_and_save_backtest_persists_real_stats(db_session):
    _persist_synthetic_candles(db_session, "BACKTESTRUNUSDT")

    stats, row = run_and_save_backtest(db_session, TrendContinuationEMA50(), "BACKTESTRUNUSDT", "1h", lookback=80)

    assert stats is not None and row is not None
    assert row.playbook == "Trend Continuation EMA50"
    assert row.asset == "BACKTESTRUNUSDT"
    assert row.timeframe == "1h"
    assert row.trades == stats.trades
    assert row.win_rate == stats.win_rate

    db_row = db_session.query(Backtest).filter_by(id=row.id).one()
    assert db_row.profit_factor == stats.profit_factor


def test_run_and_save_backtest_returns_none_without_enough_candles(db_session):
    stats, row = run_and_save_backtest(db_session, TrendContinuationEMA50(), "TOOFEWCANDLES", "1h", lookback=80)
    assert stats is None and row is None
