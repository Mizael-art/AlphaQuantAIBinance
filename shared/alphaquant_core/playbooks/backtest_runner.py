"""
Runner do Backtest Engine — reaproveita os candles já persistidos pelo
Data Engine (tabela `candles`, coletados organicamente pelo Worker ao
longo do tempo) em vez de buscar dados novos na Binance.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Asset, Candle
from alphaquant_core.engines.backtest import compute_backtest_stats, run_backtest
from alphaquant_core.playbooks.base import Playbook
from alphaquant_core.services.backtest_service import save_backtest_result


def load_candles_df(db: Session, symbol: str, timeframe: str) -> pd.DataFrame:
    rows = db.execute(
        select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
        .join(Asset, Asset.id == Candle.asset_id)
        .where(Asset.symbol == symbol.upper(), Candle.timeframe == timeframe)
        .order_by(Candle.timestamp)
    ).all()

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.set_index("timestamp")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    return df


def run_and_save_backtest(
    db: Session,
    playbook: Playbook,
    symbol: str,
    timeframe: str,
    lookback: int = 200,
):
    """
    Devolve (BacktestStats, Backtest persistido) ou (None, None) se não
    houver candles suficientes no banco para esse asset/timeframe.
    """
    df = load_candles_df(db, symbol, timeframe)
    if len(df) < lookback + 50:  # margem mínima para produzir pelo menos algumas avaliações
        return None, None

    trades = run_backtest(df, playbook, symbol, timeframe, lookback=lookback)
    stats = compute_backtest_stats(trades)
    row = save_backtest_result(db, playbook.name, symbol.upper(), timeframe, stats)
    return stats, row
