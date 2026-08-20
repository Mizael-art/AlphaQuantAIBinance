"""
Endpoint de inspeção manual do Data Engine (Fase 3).

Não faz parte do fluxo automático do Worker — serve para validar em
produção que a coleta Bybit + indicadores + estrutura está funcionando,
antes do Dashboard (Fase 10) existir.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from alphaquant_core.db.session import get_db
from alphaquant_core.engines.data_engine import MarketDataError
from alphaquant_core.engines.orchestrator import analyze_asset

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/{symbol}")
def get_market_data(
    symbol: str,
    timeframe: str = Query(default="1h", pattern="^(15m|1h|4h|1d)$"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return analyze_asset(db, symbol=symbol, timeframe=timeframe)
    except MarketDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
