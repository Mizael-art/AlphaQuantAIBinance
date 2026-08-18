"""
Contrato comum dos 10 Playbooks oficiais do AlphaQuant X.

Cada Playbook recebe o mesmo PlaybookContext (candles + indicadores +
estrutura + liquidez, já calculados uma única vez pelo Data/Structure/
Liquidity Engine) e devolve um PlaybookResult — nunca decide sozinho se
deve virar um sinal: isso é responsabilidade do Quality Filter e do
Decision Engine (Fases 6 e 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from alphaquant_core.engines.liquidity import FairValueGap, LiquiditySweep, OrderBlock
from alphaquant_core.engines.structure import Swing


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(frozen=True)
class PlaybookContext:
    symbol: str
    timeframe: str
    df: pd.DataFrame                 # OHLCV, index = timestamp, ordenado
    indicators: dict                 # saída de indicators.compute_indicators
    swings: list[Swing]
    regime: str                      # "BULLISH" | "BEARISH" | "UNDEFINED"
    fair_value_gaps: list[FairValueGap]
    order_blocks: list[OrderBlock]
    liquidity_sweep: LiquiditySweep | None
    htf_regime: str | None = None                    # regime calculado num timeframe maior (Fase 4.8 — HTF Continuation)
    volatility_contraction_ratio: float | None = None  # < 1 = squeeze (Wyckoff Spring/Upthrust, Compression Breakout)

    @property
    def last_close(self) -> float:
        return float(self.df["close"].iloc[-1])


@dataclass(frozen=True)
class PlaybookResult:
    playbook: str
    matched: bool                    # True = todas as condições atendidas agora
    direction: Direction | None
    progress: float                  # 0-100, % de condições atendidas
    conditions_met: list[str] = field(default_factory=list)
    conditions_missing: list[str] = field(default_factory=list)
    entry: float | None = None
    stop: float | None = None
    notes: str = ""


class Playbook:
    """Interface que todo playbook concreto implementa."""

    name: str = "BASE"
    version: str = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        raise NotImplementedError
