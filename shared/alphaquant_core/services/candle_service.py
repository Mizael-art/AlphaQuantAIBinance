"""
Persistência do Data Engine: upsert de assets e candles.

Nunca duplica candles (respeitando a UniqueConstraint asset_id +
timeframe + timestamp) — reaplica o mesmo candle sobrescrevendo OHLCV,
o que cobre o caso de a última candle da janela ainda estar em formação
no momento da coleta anterior.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Asset, Candle
from alphaquant_core.engines.data_engine import Candle as DataEngineCandle


def get_or_create_asset(db: Session, symbol: str, exchange: str = "BINANCE", market: str = "SPOT") -> Asset:
    asset = db.query(Asset).filter_by(symbol=symbol.upper()).one_or_none()
    if asset is not None:
        return asset

    asset = Asset(symbol=symbol.upper(), exchange=exchange, market=market, enabled=True)
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def upsert_candles(db: Session, asset_id: int, timeframe: str, candles: list[DataEngineCandle]) -> int:
    if not candles:
        return 0

    rows = [
        {
            "asset_id": asset_id,
            "timeframe": timeframe,
            "timestamp": c.timestamp,
            # float() defensivo: numpy.float64 (ex.: vindo direto de uma
            # coluna do pandas sem cast) quebra a adaptação do driver
            # psycopg2 com um erro obscuro — já vimos esse mesmo problema
            # em liquidity.py e opportunity_service.py (Fases 4 e 5).
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        }
        for c in candles
    ]

    stmt = pg_insert(Candle).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["asset_id", "timeframe", "timestamp"],
        set_={
            "open": stmt.excluded.open,
            "high": stmt.excluded.high,
            "low": stmt.excluded.low,
            "close": stmt.excluded.close,
            "volume": stmt.excluded.volume,
        },
    )
    db.execute(stmt)
    db.commit()
    return len(rows)
