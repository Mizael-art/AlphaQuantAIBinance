"""
Orquestrador do Data Engine (Fase 3).

Elimina a necessidade de screenshots: para cada ativo/timeframe, coleta
candles públicos da Binance, persiste no banco, calcula indicadores e
estrutura de mercado, e devolve um JSON padronizado — a mesma finalidade
do [[alphaquant-engine]], agora alimentando o Worker 24/7 do AlphaQuant X.
"""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy.orm import Session

from alphaquant_core.engines.data_engine import BinanceMarketDataClient, BinanceRequestError
from alphaquant_core.engines.indicators import compute_indicators
from alphaquant_core.engines.structure import current_regime, detect_structure_events, find_swings
from alphaquant_core.services.candle_service import get_or_create_asset, upsert_candles

logger = logging.getLogger("alphaquant.data_engine.orchestrator")


def _candles_to_dataframe(candles) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
    )
    df = df.set_index("timestamp").sort_index()
    return df


def fetch_and_persist(
    db: Session,
    symbol: str,
    timeframe: str,
    client: BinanceMarketDataClient | None = None,
    limit: int = 200,
) -> tuple[pd.DataFrame, list, int]:
    """
    Etapa DATA compartilhada: busca candles na Binance, persiste no banco
    (idempotente) e devolve o DataFrame pronto para qualquer consumidor
    (Data Engine/`analyze_asset` ou o Playbook Engine) — evita buscar os
    mesmos candles duas vezes no mesmo ciclo do Worker.

    Levanta BinanceRequestError se a coleta falhar.
    """
    client = client or BinanceMarketDataClient()

    candles = client.get_klines(symbol=symbol, timeframe=timeframe, limit=limit)
    if not candles:
        raise BinanceRequestError(f"nenhuma candle retornada para {symbol} {timeframe}")

    asset = get_or_create_asset(db, symbol)
    stored = upsert_candles(db, asset.id, timeframe, candles)

    df = _candles_to_dataframe(candles)
    return df, candles, stored


def analyze_asset(
    db: Session,
    symbol: str,
    timeframe: str,
    client: BinanceMarketDataClient | None = None,
    limit: int = 200,
) -> dict:
    """
    Ciclo completo do Data Engine para um asset/timeframe:
    DATA -> persistência -> indicadores -> estrutura -> JSON padronizado.

    Levanta BinanceRequestError se a coleta falhar — quem chama decide
    se registra em scanner_events e tenta novamente no próximo ciclo
    (nunca fabricar dados no lugar de uma falha de rede).
    """
    df, candles, stored = fetch_and_persist(db, symbol, timeframe, client=client, limit=limit)

    indicators = compute_indicators(df)
    swings = find_swings(df)
    structure_events = detect_structure_events(swings)
    regime = current_regime(swings)

    logger.info(
        "data_engine cycle symbol=%s timeframe=%s candles=%s stored=%s regime=%s",
        symbol, timeframe, len(candles), stored, regime,
    )

    return {
        "asset": symbol.upper(),
        "timeframe": timeframe,
        "candles_analyzed": len(candles),
        "candles_stored": stored,
        "last_close": candles[-1].close,
        "last_timestamp": candles[-1].timestamp.isoformat(),
        "indicators": indicators,
        "structure": {
            "regime": regime,
            "swings": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "price": s.price,
                    "type": s.type.value,
                    "label": s.label.value if s.label else None,
                }
                for s in swings[-10:]  # apenas os swings mais recentes
            ],
            "events": [
                {**e, "at_timestamp": e["at_timestamp"].isoformat()}
                for e in structure_events[-5:]
            ],
        },
    }
