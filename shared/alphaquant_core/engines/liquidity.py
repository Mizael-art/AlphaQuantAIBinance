"""
Liquidity Engine + Smart Money Engine (suporte aos Playbooks).

Implementações deliberadamente simples e auditáveis — cada função
devolve estruturas de dados explícitas (nunca um "score" opaco), para que
o Evidence Panel (seção 36) possa mostrar exatamente o que foi observado.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from alphaquant_core.engines.structure import Swing, SwingType


class GapDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


@dataclass(frozen=True)
class FairValueGap:
    index: int
    timestamp: pd.Timestamp
    direction: GapDirection
    low: float
    high: float
    filled: bool = False


@dataclass(frozen=True)
class OrderBlock:
    index: int
    timestamp: pd.Timestamp
    direction: GapDirection
    low: float
    high: float


@dataclass(frozen=True)
class LiquiditySweep:
    index: int
    timestamp: pd.Timestamp
    direction: GapDirection  # BULLISH = sweep de venda (varre low e reverte pra cima)
    swept_price: float
    close_back_price: float


def detect_fair_value_gaps(df: pd.DataFrame, max_lookback: int = 100) -> list[FairValueGap]:
    """
    FVG clássico de 3 candles:
    - Bullish: high da candle[i-2] < low da candle[i]  (gap entre elas)
    - Bearish: low da candle[i-2] > high da candle[i]

    `filled` marca se o preço já ATRAVESSOU o gap inteiro (fechamento do
    outro lado) em alguma candle posterior — um simples toque/retração
    parcial para dentro do gap NÃO conta como preenchido, já que é
    exatamente esse toque que o Playbook FVG Retracement precisa
    enxergar como oportunidade ainda válida.
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    n = len(df)
    start = max(2, n - max_lookback)

    gaps: list[FairValueGap] = []
    for i in range(start, n):
        if highs[i - 2] < lows[i]:
            gap_low, gap_high = float(highs[i - 2]), float(lows[i])
            filled = bool((closes[i + 1 :] <= gap_low).any()) if i + 1 < n else False
            gaps.append(FairValueGap(i, df.index[i], GapDirection.BULLISH, gap_low, gap_high, filled))
        elif lows[i - 2] > highs[i]:
            gap_low, gap_high = float(highs[i]), float(lows[i - 2])
            filled = bool((closes[i + 1 :] >= gap_high).any()) if i + 1 < n else False
            gaps.append(FairValueGap(i, df.index[i], GapDirection.BEARISH, gap_low, gap_high, filled))

    return gaps


def detect_order_blocks(df: pd.DataFrame, swings: list[Swing], max_blocks: int = 10) -> list[OrderBlock]:
    """
    Order Block simplificado: para cada swing HIGH confirmado que antecede
    um movimento de alta subsequente (ruptura do swing), a última candle de
    baixa antes da alta é o OB de venda; simetricamente para swing LOW.
    """
    blocks: list[OrderBlock] = []
    close = df["close"]
    open_ = df["open"]

    for swing in swings:
        if swing.type is SwingType.LOW:
            # procura a última candle de baixa (close < open) antes do swing low
            j = swing.index
            while j >= 0 and close.iloc[j] >= open_.iloc[j]:
                j -= 1
            if j >= 0:
                blocks.append(
                    OrderBlock(
                        index=j,
                        timestamp=df.index[j],
                        direction=GapDirection.BULLISH,
                        low=float(df["low"].iloc[j]),
                        high=float(df["high"].iloc[j]),
                    )
                )
        else:  # HIGH
            j = swing.index
            while j >= 0 and close.iloc[j] <= open_.iloc[j]:
                j -= 1
            if j >= 0:
                blocks.append(
                    OrderBlock(
                        index=j,
                        timestamp=df.index[j],
                        direction=GapDirection.BEARISH,
                        low=float(df["low"].iloc[j]),
                        high=float(df["high"].iloc[j]),
                    )
                )

    blocks.sort(key=lambda b: b.index)
    return blocks[-max_blocks:]


def detect_latest_liquidity_sweep(df: pd.DataFrame, swings: list[Swing]) -> LiquiditySweep | None:
    """
    Sweep de liquidez: a candle mais recente perfura (wick) um swing
    confirmado anterior e fecha de volta do lado "certo" — clássico
    padrão de caça de stops antes da reversão.
    """
    if not swings or len(df) == 0:
        return None

    last_idx = len(df) - 1
    last_low = float(df["low"].iloc[last_idx])
    last_high = float(df["high"].iloc[last_idx])
    last_close = float(df["close"].iloc[last_idx])

    prior_lows = [s for s in swings if s.type is SwingType.LOW and s.index < last_idx]
    prior_highs = [s for s in swings if s.type is SwingType.HIGH and s.index < last_idx]

    if prior_lows:
        reference = prior_lows[-1]
        if last_low < reference.price < last_close:
            return LiquiditySweep(
                index=last_idx, timestamp=df.index[last_idx], direction=GapDirection.BULLISH,
                swept_price=reference.price, close_back_price=last_close,
            )

    if prior_highs:
        reference = prior_highs[-1]
        if last_high > reference.price > last_close:
            return LiquiditySweep(
                index=last_idx, timestamp=df.index[last_idx], direction=GapDirection.BEARISH,
                swept_price=reference.price, close_back_price=last_close,
            )

    return None
