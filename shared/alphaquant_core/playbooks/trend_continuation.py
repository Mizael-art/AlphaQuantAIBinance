"""
Playbook 1 — Trend Continuation EMA50

Tese: em tendência confirmada, o preço faz pullback até a EMA50 e reage,
sem estar esticado (RSI fora de zona extrema).
"""
from __future__ import annotations

from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult


class TrendContinuationEMA50(Playbook):
    name = "Trend Continuation EMA50"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        ema20 = ctx.indicators.get("ema20")
        ema50 = ctx.indicators.get("ema50")
        ema100 = ctx.indicators.get("ema100")
        rsi = ctx.indicators.get("rsi14")
        close = ctx.last_close

        if None in (ema20, ema50, ema100, rsi):
            return PlaybookResult(self.name, False, None, 0.0, conditions_missing=["indicadores insuficientes"])

        bullish_alignment = ema20 > ema50 > ema100
        bearish_alignment = ema20 < ema50 < ema100
        direction = Direction.LONG if bullish_alignment else Direction.SHORT if bearish_alignment else None

        conditions: list[tuple[str, bool]] = []

        if direction is Direction.LONG:
            conditions = [
                ("Alinhamento de EMAs em alta (EMA20>EMA50>EMA100)", bullish_alignment),
                ("Regime de estrutura BULLISH", ctx.regime == "BULLISH"),
                ("Preço em pullback próximo à EMA50 (até 1.5%)", abs(close - ema50) / ema50 <= 0.015),
                ("RSI sem sobrecompra/sobrevenda extrema (35-70)", 35 <= rsi <= 70),
            ]
        elif direction is Direction.SHORT:
            conditions = [
                ("Alinhamento de EMAs em baixa (EMA20<EMA50<EMA100)", bearish_alignment),
                ("Regime de estrutura BEARISH", ctx.regime == "BEARISH"),
                ("Preço em pullback próximo à EMA50 (até 1.5%)", abs(close - ema50) / ema50 <= 0.015),
                ("RSI sem sobrecompra/sobrevenda extrema (30-65)", 30 <= rsi <= 65),
            ]
        else:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["EMAs sem alinhamento direcional claro"],
                notes="Sem tendência definida pelas EMAs.",
            )

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = close if matched else None
        stop = round(ema100, 8) if matched and direction is Direction.LONG else (
            round(ema100, 8) if matched else None
        )

        return PlaybookResult(
            self.name, matched, direction, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
        )
