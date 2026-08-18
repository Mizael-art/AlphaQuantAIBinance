"""
Playbook 9 — Compression Breakout

Tese: volatilidade contraída (squeeze) seguida de rompimento do range
recente com confirmação de volume acima da média.
"""
from __future__ import annotations

from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult

CONTRACTION_THRESHOLD = 0.75
RANGE_LOOKBACK = 20
VOLUME_CONFIRMATION_MULTIPLIER = 1.2


class CompressionBreakout(Playbook):
    name = "Compression Breakout"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        ratio = ctx.volatility_contraction_ratio
        volume_last = ctx.indicators.get("volume_last")
        volume_avg = ctx.indicators.get("volume_avg20")
        close = ctx.last_close

        if len(ctx.df) < RANGE_LOOKBACK + 1:
            return PlaybookResult(self.name, False, None, 0.0, conditions_missing=["histórico insuficiente"])

        # range recente EXCLUINDO a candle atual (o range que está sendo rompido)
        prior = ctx.df.iloc[-(RANGE_LOOKBACK + 1) : -1]
        range_high = float(prior["high"].max())
        range_low = float(prior["low"].min())

        breaks_up = close > range_high
        breaks_down = close < range_low
        direction = Direction.LONG if breaks_up else (Direction.SHORT if breaks_down else None)

        was_compressed = ratio is not None and ratio < CONTRACTION_THRESHOLD
        volume_confirms = (
            volume_last is not None and volume_avg is not None and volume_avg > 0
            and volume_last >= volume_avg * VOLUME_CONFIRMATION_MULTIPLIER
        )

        if direction is None:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=[f"preço ainda dentro do range recente [{range_low:.4f}, {range_high:.4f}]"],
            )

        conditions = [
            (f"Volatilidade estava comprimida (ATR < {CONTRACTION_THRESHOLD:.0%} da média)", was_compressed),
            (f"Rompimento do range de {RANGE_LOOKBACK} candles", True),
            (f"Volume de confirmação (≥ {VOLUME_CONFIRMATION_MULTIPLIER:.1f}x a média)", volume_confirms),
        ]

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = close if matched else None
        stop = range_low if matched and direction is Direction.LONG else (range_high if matched else None)

        return PlaybookResult(
            self.name, matched, direction, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
            notes=f"Range rompido: [{range_low:.4f}, {range_high:.4f}]",
        )
