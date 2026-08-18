"""
Playbook 2 — Liquidity Sweep Reversal

Tese: o preço varre a liquidez abaixo de um swing low (ou acima de um
swing high) e fecha de volta do lado certo — clássica caça de stops
seguida de reversão.
"""
from __future__ import annotations

from alphaquant_core.engines.liquidity import GapDirection
from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult


class LiquiditySweepReversal(Playbook):
    name = "Liquidity Sweep Reversal"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        sweep = ctx.liquidity_sweep
        rsi = ctx.indicators.get("rsi14")

        if sweep is None:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["nenhum sweep de liquidez detectado na candle mais recente"],
            )

        direction = Direction.LONG if sweep.direction is GapDirection.BULLISH else Direction.SHORT

        conditions = [
            ("Sweep de liquidez confirmado na candle atual", True),
            (
                "Fechamento reclama o nível varrido (reversão real, não só wick)",
                (sweep.close_back_price > sweep.swept_price)
                if direction is Direction.LONG
                else (sweep.close_back_price < sweep.swept_price),
            ),
        ]
        if rsi is not None:
            # RSI é lido na própria candle de reclamação (que já embute o
            # movimento do sweep) — por isso a checagem é "ainda há espaço
            # para continuar" (não está do lado oposto esticado), não
            # "estava profundamente oversold/overbought", que exigiria o
            # RSI da candle anterior ao sweep.
            conditions.append((
                "RSI não esticado no lado oposto ao sweep",
                rsi <= 85 if direction is Direction.LONG else rsi >= 15,
            ))

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = ctx.last_close if matched else None
        stop = sweep.swept_price if matched else None

        return PlaybookResult(
            self.name, matched, direction, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
        )
