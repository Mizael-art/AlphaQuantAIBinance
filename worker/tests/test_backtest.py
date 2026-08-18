import pandas as pd
import pytest

from alphaquant_core.engines.backtest import (
    SimulatedTrade,
    TradeOutcome,
    compute_backtest_stats,
    run_backtest,
)
from alphaquant_core.playbooks.base import Direction
from alphaquant_core.playbooks.trend_continuation import TrendContinuationEMA50

from tests.backtest_fixtures import long_zigzag_uptrend


def test_compute_backtest_stats_math_is_correct():
    trades = [
        SimulatedTrade(0, Direction.LONG, 100, 95, 110, TradeOutcome.WIN, 2.0),
        SimulatedTrade(1, Direction.LONG, 100, 95, 110, TradeOutcome.WIN, 2.0),
        SimulatedTrade(2, Direction.LONG, 100, 95, 110, TradeOutcome.LOSS, -1.0),
        SimulatedTrade(3, Direction.LONG, 100, 95, 110, TradeOutcome.TIMEOUT, 0.0),
    ]
    stats = compute_backtest_stats(trades)

    assert stats.trades == 3  # timeout excluído — nunca fabrica um resultado desconhecido
    assert stats.win_rate == pytest.approx(2 / 3)
    assert stats.payoff == pytest.approx(2.0)
    assert stats.profit_factor == pytest.approx(4.0)
    assert stats.expectancy == pytest.approx(1.0)


def test_compute_backtest_stats_empty_when_no_decided_trades():
    trades = [SimulatedTrade(0, Direction.LONG, 100, 95, 110, TradeOutcome.TIMEOUT, 0.0)]
    stats = compute_backtest_stats(trades)
    assert stats.trades == 0
    assert stats.win_rate == 0.0
    assert stats.profit_factor == 0.0


def test_compute_backtest_stats_max_drawdown_tracks_equity_curve():
    # +2, -1, -1, +1 -> equity: 2, 1, 0, 1 -> peak sempre 2 até o fim -> max_dd = 2 (de 2 para 0)
    trades = [
        SimulatedTrade(0, Direction.LONG, 100, 95, 110, TradeOutcome.WIN, 2.0),
        SimulatedTrade(1, Direction.LONG, 100, 95, 110, TradeOutcome.LOSS, -1.0),
        SimulatedTrade(2, Direction.LONG, 100, 95, 110, TradeOutcome.LOSS, -1.0),
        SimulatedTrade(3, Direction.LONG, 100, 95, 110, TradeOutcome.WIN, 1.0),
    ]
    stats = compute_backtest_stats(trades)
    assert stats.max_drawdown == pytest.approx(2.0)


def test_run_backtest_produces_real_trades_without_lookahead():
    df = long_zigzag_uptrend()
    trades = run_backtest(df, TrendContinuationEMA50(), "BTCUSDT", "1h", lookback=80)

    assert len(trades) > 0
    for t in trades:
        assert t.direction in (Direction.LONG, Direction.SHORT)
        assert t.outcome in (TradeOutcome.WIN, TradeOutcome.LOSS, TradeOutcome.TIMEOUT)
        # a simulação forward só pode usar candles ESTRITAMENTE depois da entrada
        assert t.entry_index < len(df) - 1


def test_run_backtest_stats_are_internally_consistent():
    df = long_zigzag_uptrend()
    trades = run_backtest(df, TrendContinuationEMA50(), "BTCUSDT", "1h", lookback=80)
    stats = compute_backtest_stats(trades)

    decided = [t for t in trades if t.outcome != TradeOutcome.TIMEOUT]
    assert stats.trades == len(decided)
    assert 0.0 <= stats.win_rate <= 1.0


def test_run_backtest_returns_empty_for_flat_market():
    flat_df = pd.DataFrame(
        {"open": [100.0] * 150, "high": [100.2] * 150, "low": [99.8] * 150, "close": [100.0] * 150, "volume": [100.0] * 150},
        index=pd.date_range("2025-01-01", periods=150, freq="h"),
    )
    trades = run_backtest(flat_df, TrendContinuationEMA50(), "BTCUSDT", "1h", lookback=80)
    assert trades == []  # sem tendência, o playbook nunca deveria bater
