"""
Playbook 4 — FVG Retracement

Tese: o preço retorna a um Fair Value Gap ainda não preenchido e reage a
favor da direção do gap.
"""
from __future__ import annotations

from alphaquant_core.engines.liquidity import GapDirection
from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult


class FVGRetracement(Playbook):
    name = "FVG Retracement"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        close = ctx.last_close
        open_gaps = [g for g in ctx.fair_value_gaps if not g.filled]
        relevant = [g for g in open_gaps if g.low <= close <= g.high]

        if not relevant:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["preço não está dentro de nenhum FVG não preenchido"],
            )

        gap = relevant[-1]
        direction = Direction.LONG if gap.direction is GapDirection.BULLISH else Direction.SHORT

        conditions = [
            ("Preço dentro de FVG não preenchido", True),
            ("Gap alinhado com o regime de estrutura atual",
             (direction is Direction.LONG and ctx.regime != "BEARISH")
             or (direction is Direction.SHORT and ctx.regime != "BULLISH")),
        ]

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = close if matched else None
        stop = gap.low if matched and direction is Direction.LONG else (gap.high if matched else None)

        return PlaybookResult(
            self.name, matched, direction, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
            notes=f"FVG em [{gap.low:.4f}, {gap.high:.4f}]",
        )
