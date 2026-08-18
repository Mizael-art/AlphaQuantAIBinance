"""
Playbook Engine — orquestra os 10 Playbooks oficiais contra o mesmo
PlaybookContext (calculado uma única vez por ciclo).
"""
from __future__ import annotations

import pandas as pd

from alphaquant_core.engines.indicators import atr_contraction_ratio, compute_indicators
from alphaquant_core.engines.liquidity import (
    detect_fair_value_gaps,
    detect_latest_liquidity_sweep,
    detect_order_blocks,
)
from alphaquant_core.engines.structure import current_regime, find_swings
from alphaquant_core.playbooks.base import Playbook, PlaybookContext, PlaybookResult
from alphaquant_core.playbooks.breakout_retest import BreakoutRetest
from alphaquant_core.playbooks.compression_breakout import CompressionBreakout
from alphaquant_core.playbooks.fvg_retracement import FVGRetracement
from alphaquant_core.playbooks.htf_continuation import HTFContinuation
from alphaquant_core.playbooks.liquidity_sweep_reversal import LiquiditySweepReversal
from alphaquant_core.playbooks.open_range_breakout import OpenRangeBreakout
from alphaquant_core.playbooks.order_block_reaction import OrderBlockReaction
from alphaquant_core.playbooks.trend_continuation import TrendContinuationEMA50
from alphaquant_core.playbooks.wyckoff_spring import WyckoffSpring
from alphaquant_core.playbooks.wyckoff_upthrust import WyckoffUpthrust

# Ordem estável — reflete a numeração oficial da especificação (seção 23)
ALL_PLAYBOOKS: list[Playbook] = [
    TrendContinuationEMA50(),
    LiquiditySweepReversal(),
    OrderBlockReaction(),
    FVGRetracement(),
    BreakoutRetest(),
    WyckoffSpring(),
    WyckoffUpthrust(),
    HTFContinuation(),
    CompressionBreakout(),
    OpenRangeBreakout(),
]


def build_context(
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    htf_regime: str | None = None,
) -> PlaybookContext:
    """
    Calcula indicadores, estrutura e liquidez uma única vez e monta o
    PlaybookContext reaproveitado por todos os playbooks — evita
    recomputar a mesma coisa 10 vezes por ciclo.
    """
    indicators = compute_indicators(df)
    swings = find_swings(df)
    regime = current_regime(swings)
    fvgs = detect_fair_value_gaps(df)
    order_blocks = detect_order_blocks(df, swings)
    sweep = detect_latest_liquidity_sweep(df, swings)
    contraction_ratio = atr_contraction_ratio(df["high"], df["low"], df["close"])

    return PlaybookContext(
        symbol=symbol,
        timeframe=timeframe,
        df=df,
        indicators=indicators,
        swings=swings,
        regime=regime,
        fair_value_gaps=fvgs,
        order_blocks=order_blocks,
        liquidity_sweep=sweep,
        htf_regime=htf_regime,
        volatility_contraction_ratio=contraction_ratio,
    )


def evaluate_all(ctx: PlaybookContext, playbooks: list[Playbook] | None = None) -> list[PlaybookResult]:
    """
    Roda todos os playbooks (ou o subconjunto passado) contra o mesmo
    contexto. Devolve TODOS os resultados, inclusive os que não bateram
    (progress > 0 e matched=False) — são exatamente o material bruto do
    Future Opportunity Engine (Fase 11).
    """
    playbooks = playbooks if playbooks is not None else ALL_PLAYBOOKS
    return [pb.evaluate(ctx) for pb in playbooks]
