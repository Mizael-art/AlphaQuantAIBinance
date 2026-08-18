"""
Playbook 3 — Order Block Reaction

Tese: o preço retorna a um Order Block (última candle de sinal oposto
antes de um movimento impulsivo) e reage a favor da direção original do
movimento.
"""
from __future__ import annotations

from alphaquant_core.engines.liquidity import GapDirection
from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult


class OrderBlockReaction(Playbook):
    name = "Order Block Reaction"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        close = ctx.last_close
        relevant = [ob for ob in ctx.order_blocks if ob.low <= close <= ob.high]

        if not relevant:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["preço não está dentro de nenhum Order Block ativo"],
            )

        ob = relevant[-1]
        direction = Direction.LONG if ob.direction is GapDirection.BULLISH else Direction.SHORT

        conditions = [
            ("Preço dentro da zona do Order Block", True),
            ("Order Block alinhado com o regime de estrutura atual",
             (direction is Direction.LONG and ctx.regime != "BEARISH")
             or (direction is Direction.SHORT and ctx.regime != "BULLISH")),
        ]

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = close if matched else None
        stop = ob.low if matched and direction is Direction.LONG else (ob.high if matched else None)

        return PlaybookResult(
            self.name, matched, direction, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
            notes=f"Order Block em [{ob.low:.4f}, {ob.high:.4f}]",
        )
