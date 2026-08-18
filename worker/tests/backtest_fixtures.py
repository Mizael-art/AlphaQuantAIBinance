"""
Fixture compartilhada para testes de backtest — precisa de histórico
mais longo que os cenários de playbook isolados (worker/tests/
playbook_fixtures.py), já que o backtest reavalia candle a candle.
"""
from __future__ import annotations

import random

import pandas as pd


def long_zigzag_uptrend(
    cycles: int = 15, rally_bars: int = 8, rally_gain: float = 12.0,
    pullback_bars: int = 5, pullback_loss: float = 10.0, start: float = 100.0, seed: int = 9,
) -> pd.DataFrame:
    rng = random.Random(seed)
    rows: list[dict] = []
    price = start
    for _ in range(cycles):
        step_up = rally_gain / rally_bars
        for _ in range(rally_bars):
            o = price
            price += step_up
            jitter = rng.uniform(0.05, 0.3)
            rows.append({
                "open": o, "high": max(o, price) + jitter, "low": min(o, price) - jitter * 0.3,
                "close": price, "volume": rng.uniform(150, 250),
            })
        step_down = pullback_loss / pullback_bars
        for _ in range(pullback_bars):
            o = price
            price -= step_down
            jitter = rng.uniform(0.05, 0.3)
            rows.append({
                "open": o, "high": max(o, price) + jitter * 0.3, "low": min(o, price) - jitter,
                "close": price, "volume": rng.uniform(150, 250),
            })
    index = pd.date_range("2025-01-01", periods=len(rows), freq="h")
    return pd.DataFrame(rows, index=index)[["open", "high", "low", "close", "volume"]]
