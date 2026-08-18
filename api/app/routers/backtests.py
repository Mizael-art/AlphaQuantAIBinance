"""Endpoint de Backtests (Fase 13) — lista os resultados já persistidos."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Backtest
from alphaquant_core.db.session import get_db

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("")
def list_backtests(
    playbook: str | None = Query(default=None),
    asset: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Backtest).order_by(Backtest.created_at.desc()).limit(limit)
    if playbook:
        stmt = stmt.where(Backtest.playbook == playbook)
    if asset:
        stmt = stmt.where(Backtest.asset == asset.upper())

    rows = db.execute(stmt).scalars().all()
    return {
        "count": len(rows),
        "backtests": [
            {
                "id": b.id,
                "playbook": b.playbook,
                "asset": b.asset,
                "timeframe": b.timeframe,
                "trades": b.trades,
                "win_rate": b.win_rate,
                "payoff": b.payoff,
                "profit_factor": b.profit_factor,
                "expectancy": b.expectancy,
                "max_drawdown": b.max_drawdown,
                "created_at": b.created_at,
            }
            for b in rows
        ],
    }
