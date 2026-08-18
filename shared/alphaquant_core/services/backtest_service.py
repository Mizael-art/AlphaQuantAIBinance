"""Persistência da Fase 13 — grava BacktestStats na tabela `backtests`."""
from __future__ import annotations

from sqlalchemy.orm import Session

from alphaquant_core.db.models import Backtest
from alphaquant_core.engines.backtest import BacktestStats


def save_backtest_result(
    db: Session,
    playbook: str,
    asset: str,
    timeframe: str,
    stats: BacktestStats,
) -> Backtest:
    row = Backtest(
        playbook=playbook, asset=asset, timeframe=timeframe,
        trades=stats.trades, win_rate=float(stats.win_rate), payoff=float(stats.payoff),
        profit_factor=float(stats.profit_factor), expectancy=float(stats.expectancy),
        max_drawdown=float(stats.max_drawdown),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
