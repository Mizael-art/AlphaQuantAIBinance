"""
Structure Engine — detecção de swings e estrutura de mercado
(HH/HL/LH/LL, BOS, CHOCH).

Regra de swing: um ponto é swing high se for o maior high dentro da janela
[-left, +right] ao seu redor; simetricamente para swing low. BOS/CHOCH são
derivados da sequência de swings confirmados (nunca do candle ainda em
formação).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class SwingType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class StructureLabel(str, Enum):
    HH = "HH"  # Higher High
    HL = "HL"  # Higher Low
    LH = "LH"  # Lower High
    LL = "LL"  # Lower Low


class StructureEvent(str, Enum):
    BOS = "BOS"      # Break of Structure — continuação da tendência vigente
    CHOCH = "CHOCH"   # Change of Character — possível reversão


@dataclass(frozen=True)
class Swing:
    index: int
    timestamp: pd.Timestamp
    price: float
    type: SwingType
    label: StructureLabel | None = None


def find_swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> list[Swing]:
    """
    df precisa ter as colunas high, low e um índice ordenado
    cronologicamente. Os últimos `right` candles nunca formam swing
    confirmado (ainda podem ser invalidados por candles futuros).
    """
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)

    swings: list[Swing] = []
    for i in range(left, n - right):
        window_high = highs[i - left : i + right + 1]
        if highs[i] == window_high.max() and (window_high == highs[i]).sum() == 1:
            swings.append(Swing(index=i, timestamp=df.index[i], price=float(highs[i]), type=SwingType.HIGH))

        window_low = lows[i - left : i + right + 1]
        if lows[i] == window_low.min() and (window_low == lows[i]).sum() == 1:
            swings.append(Swing(index=i, timestamp=df.index[i], price=float(lows[i]), type=SwingType.LOW))

    swings.sort(key=lambda s: s.index)
    return _label_swings(swings)


def _label_swings(swings: list[Swing]) -> list[Swing]:
    labeled: list[Swing] = []
    last_high: float | None = None
    last_low: float | None = None

    for swing in swings:
        if swing.type is SwingType.HIGH:
            label = None
            if last_high is not None:
                label = StructureLabel.HH if swing.price > last_high else StructureLabel.LH
            last_high = swing.price
        else:
            label = None
            if last_low is not None:
                label = StructureLabel.HL if swing.price > last_low else StructureLabel.LL
            last_low = swing.price

        labeled.append(
            Swing(index=swing.index, timestamp=swing.timestamp, price=swing.price, type=swing.type, label=label)
        )

    return labeled


def detect_structure_events(swings: list[Swing]) -> list[dict]:
    """
    Percorre os swings rotulados e emite eventos BOS/CHOCH sempre que a
    sequência de HH/HL (alta) ou LH/LL (baixa) é quebrada.

    Regra:
    - Em tendência de ALTA (última confirmação HH+HL): um novo LL quebra a
      estrutura -> CHOCH. Um novo HH mantém -> BOS de continuação.
    - Em tendência de BAIXA (última confirmação LH+LL): um novo HH quebra
      a estrutura -> CHOCH. Um novo LL mantém -> BOS de continuação.
    - Sem tendência definida ainda: nenhum evento é emitido.
    """
    events: list[dict] = []
    regime: str | None = None  # "BULLISH" | "BEARISH"

    for swing in swings:
        if swing.label is None:
            continue

        if swing.label in (StructureLabel.HH, StructureLabel.HL):
            if regime == "BEARISH" and swing.label is StructureLabel.HH:
                events.append(_event(swing, StructureEvent.CHOCH, "BULLISH"))
                regime = "BULLISH"
            elif regime == "BULLISH":
                events.append(_event(swing, StructureEvent.BOS, "BULLISH"))
            elif regime is None and swing.label is StructureLabel.HH:
                regime = "BULLISH"

        else:  # LH ou LL
            if regime == "BULLISH" and swing.label is StructureLabel.LL:
                events.append(_event(swing, StructureEvent.CHOCH, "BEARISH"))
                regime = "BEARISH"
            elif regime == "BEARISH":
                events.append(_event(swing, StructureEvent.BOS, "BEARISH"))
            elif regime is None and swing.label is StructureLabel.LL:
                regime = "BEARISH"

    return events


def _event(swing: Swing, event: StructureEvent, regime: str) -> dict:
    return {
        "event": event.value,
        "regime": regime,
        "at_index": swing.index,
        "at_timestamp": swing.timestamp,
        "price": swing.price,
        "label": swing.label.value if swing.label else None,
    }


def current_regime(swings: list[Swing]) -> str:
    events = detect_structure_events(swings)
    if not events:
        return "UNDEFINED"
    return events[-1]["regime"]
