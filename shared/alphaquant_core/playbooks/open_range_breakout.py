"""
Playbook 10 — Open Range Breakout (EXPERIMENTAL)

Status EXPERIMENTAL por definição da especificação original (seção 23):
permanece assim até acumular evidência estatística suficiente via
Backtest (Fase 13).

Tese: define-se um "range de abertura" com as primeiras N candles do dia
UTC corrente; um rompimento desse range com volume de confirmação sinaliza
continuação na direção do rompimento.
"""
from __future__ import annotations

from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult

OPENING_RANGE_CANDLES = 4  # ex.: com timeframe 1h, cobre as 4 primeiras horas do dia UTC
VOLUME_CONFIRMATION_MULTIPLIER = 1.2


class OpenRangeBreakout(Playbook):
    name = "Open Range Breakout"
    version = "v1.0"
    status = "EXPERIMENTAL"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        df = ctx.df
        if df.empty:
            return PlaybookResult(self.name, False, None, 0.0, conditions_missing=["sem candles"])

        last_ts = df.index[-1]
        today = df.index.normalize() == last_ts.normalize()
        today_df = df[today]

        if len(today_df) <= OPENING_RANGE_CANDLES:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=[f"ainda dentro do range de abertura (primeiras {OPENING_RANGE_CANDLES} candles do dia)"],
            )

        opening_range = today_df.iloc[:OPENING_RANGE_CANDLES]
        range_high = float(opening_range["high"].max())
        range_low = float(opening_range["low"].min())
        close = ctx.last_close

        volume_last = ctx.indicators.get("volume_last")
        volume_avg = ctx.indicators.get("volume_avg20")
        volume_confirms = (
            volume_last is not None and volume_avg is not None and volume_avg > 0
            and volume_last >= volume_avg * VOLUME_CONFIRMATION_MULTIPLIER
        )

        breaks_up = close > range_high
        breaks_down = close < range_low
        direction = Direction.LONG if breaks_up else (Direction.SHORT if breaks_down else None)

        if direction is None:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=[f"preço ainda dentro do range de abertura [{range_low:.4f}, {range_high:.4f}]"],
                notes="Playbook EXPERIMENTAL — aguardando validação estatística (ver Fase 13).",
            )

        conditions = [
            ("Rompimento do range de abertura do dia", True),
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
            notes="Playbook EXPERIMENTAL — aguardando validação estatística (ver Fase 13).",
        )
