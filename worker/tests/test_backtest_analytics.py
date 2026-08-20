"""Testes da Fase 6 — Monte Carlo, Walk Forward, Sensitivity, Grid Test, Comparison."""
from __future__ import annotations

import random

import pandas as pd
import pytest

from alphaquant_core.engines.backtest import BacktestStats
from alphaquant_core.engines.backtest_analytics import (
    CONSISTENTLY_NEGATIVE,
    FRAGILE,
    INSUFFICIENT_DATA,
    ROBUST,
    GridCell,
    assess_robustness,
    compare_strategies,
    run_grid_test,
    run_monte_carlo,
    run_sensitivity,
    run_walk_forward,
)
from alphaquant_core.strategies.strategy_parser import parse_prompt
from alphaquant_core.strategies.strategy_runner import PromptStrategy


def _long_uptrend_df(cycles: int = 40, rally_bars: int = 6, pullback_bars: int = 4) -> pd.DataFrame:
    """Zigue-zague de alta com HH/HL genuínos, longo o bastante (centenas
    de candles) para walk-forward/grid/sensitivity terem dados reais."""
    rng = random.Random(7)
    rows = []
    price = 100.0
    for c in range(cycles):
        step_up = 10.0 / rally_bars
        for _ in range(rally_bars):
            o = price
            price += step_up
            jitter = rng.uniform(0.05, 0.25)
            rows.append({"open": o, "high": max(o, price) + jitter, "low": min(o, price) - jitter * 0.3,
                         "close": price, "volume": rng.uniform(150, 250)})
        if c < cycles - 1:
            step_down = 5.0 / pullback_bars
            for _ in range(pullback_bars):
                o = price
                price -= step_down
                jitter = rng.uniform(0.05, 0.25)
                rows.append({"open": o, "high": max(o, price) + jitter * 0.3, "low": min(o, price) - jitter,
                             "close": price, "volume": rng.uniform(150, 250)})
    index = pd.date_range("2025-01-01", periods=len(rows), freq="1h")
    return pd.DataFrame(rows, index=index)[["open", "high", "low", "close", "volume"]]


PERMISSIVE_LONG_PROMPT = """
NAME: Permissive Long
CONDITIONS:
  REGIME == BULLISH
STOP: SWING_LOW
TARGETS: RR 1.5
"""


def _permissive_strategy() -> PromptStrategy:
    return PromptStrategy(parse_prompt("Permissive Long", PERMISSIVE_LONG_PROMPT))


class TestMonteCarlo:
    def test_deterministic_with_seed(self):
        r_multiples = [1.0, -1.0, 2.0, -1.0, 1.5, -1.0, 3.0]
        a = run_monte_carlo(r_multiples, simulations=200, seed=42)
        b = run_monte_carlo(r_multiples, simulations=200, seed=42)
        assert a == b

    def test_all_positive_trades_never_lose(self):
        result = run_monte_carlo([1.0, 2.0, 1.5, 3.0], simulations=200, seed=1)
        assert result.probability_of_loss == 0.0
        assert result.final_equity_r_p5 > 0

    def test_all_negative_trades_always_lose(self):
        result = run_monte_carlo([-1.0, -2.0, -1.5], simulations=200, seed=1)
        assert result.probability_of_loss == 1.0

    def test_percentiles_are_ordered(self):
        r_multiples = [1.0, -1.0, 2.0, -0.5, 1.5, -1.0, 0.5, -0.3]
        result = run_monte_carlo(r_multiples, simulations=500, trades_per_sim=50, seed=3)
        assert result.final_equity_r_p5 <= result.final_equity_r_p50 <= result.final_equity_r_p95
        assert result.max_drawdown_r_p50 <= result.max_drawdown_r_p95

    def test_rejects_empty_input(self):
        with pytest.raises(ValueError):
            run_monte_carlo([])

    def test_ruin_probability_reacts_to_threshold(self):
        r_multiples = [-1.0] * 20  # sequência de perdas constrói drawdown rápido
        lenient = run_monte_carlo(r_multiples, simulations=100, trades_per_sim=15, ruin_drawdown_r=100.0, seed=5)
        strict = run_monte_carlo(r_multiples, simulations=100, trades_per_sim=15, ruin_drawdown_r=5.0, seed=5)
        assert strict.probability_of_ruin >= lenient.probability_of_ruin


class TestWalkForward:
    def test_splits_are_chronological_and_non_overlapping(self):
        df = _long_uptrend_df(cycles=40)
        folds = run_walk_forward(df, _permissive_strategy(), "BTCUSDT", "1h", n_folds=3, oos_fraction=0.3, lookback=60)

        assert len(folds) == 3
        for fold in folds:
            assert fold.dev_start <= fold.dev_end < fold.oos_start <= fold.oos_end
        # fold seguinte começa depois do anterior terminar (sem sobreposição)
        for a, b in zip(folds, folds[1:]):
            assert a.oos_end < b.dev_start

    def test_produces_stats_for_dev_and_oos(self):
        df = _long_uptrend_df(cycles=40)
        folds = run_walk_forward(df, _permissive_strategy(), "BTCUSDT", "1h", n_folds=2, oos_fraction=0.25, lookback=60)
        for fold in folds:
            assert isinstance(fold.dev_stats, BacktestStats)
            assert isinstance(fold.oos_stats, BacktestStats)

    def test_rejects_insufficient_data(self):
        df = _long_uptrend_df(cycles=3)  # poucos candles
        with pytest.raises(ValueError):
            run_walk_forward(df, _permissive_strategy(), "BTCUSDT", "1h", n_folds=10, lookback=60)

    def test_rejects_invalid_oos_fraction(self):
        df = _long_uptrend_df(cycles=40)
        with pytest.raises(ValueError):
            run_walk_forward(df, _permissive_strategy(), "BTCUSDT", "1h", oos_fraction=1.5)


class TestSensitivity:
    BASE = """
NAME: Sensitivity Base
CONDITIONS:
  REGIME == BULLISH
  RSI14 < 100
STOP: SWING_LOW
TARGETS: RR 2.0
"""

    def test_runs_grid_of_parameter_values(self):
        df = _long_uptrend_df(cycles=40)
        results = run_sensitivity(
            self.BASE, {"RSI14": [50, 100]}, df, "BTCUSDT", "1h", lookback=60,
        )
        assert len(results) == 2
        thresholds = {r.param_overrides["RSI14"] for r in results}
        assert thresholds == {50, 100}

    def test_excludes_variants_that_fail_validation(self):
        """RSI14 sozinho sem timeframe é válido; mas se substituirmos por
        um valor que quebra a sintaxe do prompt, a variante é excluída,
        não contada como estratégia ruim."""
        broken_base = "NAME: x\nCONDITIONS:\n  RSI14 < 100\nSTOP: SWING_LOW\nTARGETS: RR 2\n"
        df = _long_uptrend_df(cycles=10)
        # combo vazio (nenhum param) sempre gera 1 variante idêntica ao base
        results = run_sensitivity(broken_base, {"RSI14": [30]}, df, "BTCUSDT", "1h", lookback=60)
        assert len(results) == 1  # substituição válida não deveria ser excluída

    def test_cartesian_product_of_multiple_params(self):
        multi_base = """
NAME: Multi
CONDITIONS:
  REGIME == BULLISH
  RSI14 < 100
  VOLUME > 0
STOP: SWING_LOW
TARGETS: RR 2.0
"""
        df = _long_uptrend_df(cycles=20)
        results = run_sensitivity(
            multi_base, {"RSI14": [50, 100], "VOLUME": [0, 1]}, df, "BTCUSDT", "1h", lookback=60,
        )
        assert len(results) == 4  # produto cartesiano 2x2


class TestAssessRobustness:
    def test_robust_when_all_variants_profitable(self):
        stats_positive = BacktestStats(trades=10, win_rate=0.6, payoff=1.5, profit_factor=2.0, expectancy=0.3, max_drawdown=2.0)
        results = [
            type("R", (), {"param_overrides": {"a": 1}, "stats": stats_positive})(),
            type("R", (), {"param_overrides": {"a": 2}, "stats": stats_positive})(),
        ]
        assert assess_robustness(results) == ROBUST

    def test_fragile_when_sign_flips(self):
        pos = BacktestStats(trades=10, win_rate=0.6, payoff=1.5, profit_factor=2.0, expectancy=0.3, max_drawdown=2.0)
        neg = BacktestStats(trades=10, win_rate=0.3, payoff=0.8, profit_factor=0.5, expectancy=-0.2, max_drawdown=5.0)
        results = [
            type("R", (), {"param_overrides": {"a": 1}, "stats": pos})(),
            type("R", (), {"param_overrides": {"a": 2}, "stats": neg})(),
        ]
        assert assess_robustness(results) == FRAGILE

    def test_consistently_negative(self):
        neg = BacktestStats(trades=10, win_rate=0.3, payoff=0.8, profit_factor=0.5, expectancy=-0.2, max_drawdown=5.0)
        results = [
            type("R", (), {"param_overrides": {"a": 1}, "stats": neg})(),
            type("R", (), {"param_overrides": {"a": 2}, "stats": neg})(),
        ]
        assert assess_robustness(results) == CONSISTENTLY_NEGATIVE

    def test_insufficient_data_with_fewer_than_two_results(self):
        assert assess_robustness([]) == INSUFFICIENT_DATA


class TestGridTest:
    def test_runs_each_cell_and_skips_missing_data(self):
        df = _long_uptrend_df(cycles=40)

        def data_provider(symbol, timeframe):
            if symbol == "BTCUSDT":
                return df
            return None  # ETHUSDT sem dado suficiente

        cells = [
            GridCell("Permissive Long", _permissive_strategy(), "BTCUSDT", "1h"),
            GridCell("Permissive Long", _permissive_strategy(), "ETHUSDT", "1h"),
        ]
        results = run_grid_test(cells, data_provider, lookback=60)

        assert len(results) == 2
        btc = next(r for r in results if r.symbol == "BTCUSDT")
        eth = next(r for r in results if r.symbol == "ETHUSDT")
        assert btc.skipped_reason is None
        assert eth.skipped_reason is not None
        assert eth.stats.trades == 0

    def test_never_fabricates_trades_for_skipped_cell(self):
        results = run_grid_test(
            [GridCell("X", _permissive_strategy(), "NODATA", "1h")],
            data_provider=lambda s, t: None,
        )
        assert results[0].stats.trades == 0
        assert results[0].stats.expectancy == 0.0


class TestCompareStrategies:
    def test_sorts_by_expectancy_descending_by_default(self):
        a = BacktestStats(trades=10, win_rate=0.5, payoff=1.0, profit_factor=1.0, expectancy=0.1, max_drawdown=3.0)
        b = BacktestStats(trades=10, win_rate=0.6, payoff=2.0, profit_factor=3.0, expectancy=0.5, max_drawdown=1.0)
        rows = compare_strategies({"A": a, "B": b})
        assert [r.name for r in rows] == ["B", "A"]

    def test_sorts_drawdown_ascending(self):
        a = BacktestStats(trades=10, win_rate=0.5, payoff=1.0, profit_factor=1.0, expectancy=0.1, max_drawdown=5.0)
        b = BacktestStats(trades=10, win_rate=0.5, payoff=1.0, profit_factor=1.0, expectancy=0.1, max_drawdown=1.0)
        rows = compare_strategies({"A": a, "B": b}, sort_by="max_drawdown")
        assert [r.name for r in rows] == ["B", "A"]  # menor drawdown primeiro

    def test_rejects_invalid_sort_field(self):
        with pytest.raises(ValueError):
            compare_strategies({"A": BacktestStats(0, 0, 0, 0, 0, 0)}, sort_by="not_a_field")
