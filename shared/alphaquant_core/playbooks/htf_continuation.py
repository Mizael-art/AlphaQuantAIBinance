"""
Playbook 8 — HTF Continuation

Tese: o timeframe de execução está em pullback saudável na direção da
tendência confirmada num timeframe maior (HTF) — ex.: 4H em alta, 15M
fazendo pullback até a EMA50 antes de continuar.

Requer que o Worker calcule o regime também no HTF e o passe via
ctx.htf_regime (ver docs/PROJECT_PLAN.md, seção 5 — "Fase 8: Worker 24/7 completo" para como o Worker calcula o HTF em paralelo).
"""
from __future__ import annotations

from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult


class HTFContinuation(Playbook):
    name = "HTF Continuation"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        ema20 = ctx.indicators.get("ema20")
        ema50 = ctx.indicators.get("ema50")
        close = ctx.last_close

        if ctx.htf_regime is None:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["regime do timeframe maior (HTF) não disponível neste ciclo"],
            )
        if None in (ema20, ema50):
            return PlaybookResult(self.name, False, None, 0.0, conditions_missing=["indicadores insuficientes"])

        direction = Direction.LONG if ctx.htf_regime == "BULLISH" else (
            Direction.SHORT if ctx.htf_regime == "BEARISH" else None
        )
        if direction is None:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["HTF sem regime definido (UNDEFINED)"],
            )

        ltf_aligned = (ctx.regime == ctx.htf_regime) or ctx.regime == "UNDEFINED"
        pullback_to_ema50 = abs(close - ema50) / ema50 <= 0.015
        ema_alignment = (ema20 >= ema50) if direction is Direction.LONG else (ema20 <= ema50)

        conditions = [
            (f"HTF em tendência confirmada ({ctx.htf_regime})", True),
            ("Timeframe de execução não contradiz o HTF", ltf_aligned),
            ("Pullback até a EMA50 no timeframe de execução (até 1.5%)", pullback_to_ema50),
            ("EMA20 alinhada com a direção do HTF", ema_alignment),
        ]

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = close if matched else None
        stop = ctx.indicators.get("ema100") if matched else None

        return PlaybookResult(
            self.name, matched, direction, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
        )
