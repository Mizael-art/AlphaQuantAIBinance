"""
Playbook 5 — Breakout + Retest

Tese: um nível de estrutura (swing HIGH/LOW) foi rompido (BOS) e o preço
voltou para testá-lo, segurando do lado certo — confirmação clássica de
rompimento antes de continuar.
"""
from __future__ import annotations

from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult
from alphaquant_core.engines.structure import detect_structure_events


class BreakoutRetest(Playbook):
    name = "Breakout + Retest"
    version = "v1.0"

    RETEST_TOLERANCE = 0.01  # 1%

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        events = detect_structure_events(ctx.swings)
        bos_events = [e for e in events if e["event"] == "BOS"]

        if not bos_events:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["nenhum BOS confirmado recentemente"],
            )

        last_bos = bos_events[-1]
        direction = Direction.LONG if last_bos["regime"] == "BULLISH" else Direction.SHORT
        level = last_bos["price"]
        close = ctx.last_close

        near_level = abs(close - level) / level <= self.RETEST_TOLERANCE
        holding = (close >= level * (1 - self.RETEST_TOLERANCE)) if direction is Direction.LONG else (
            close <= level * (1 + self.RETEST_TOLERANCE)
        )

        conditions = [
            ("BOS confirmado na direção da tendência", True),
            (f"Preço em retest do nível rompido (± {self.RETEST_TOLERANCE:.0%})", near_level),
            ("Preço segurando do lado certo do nível", holding),
        ]

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = close if matched else None
        stop = level * 0.99 if matched and direction is Direction.LONG else (level * 1.01 if matched else None)

        return PlaybookResult(
            self.name, matched, direction, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
            notes=f"Nível rompido em {level:.4f}",
        )
