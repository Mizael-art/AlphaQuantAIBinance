"""
Playbook 7 — Wyckoff Upthrust

Espelho do Wyckoff Spring: dentro de uma faixa de compressão, o preço
varre a liquidez acima da resistência da faixa (falso rompimento —
"upthrust") e é rejeitado de volta, sinalizando distribuição e reversão
para baixo.
"""
from __future__ import annotations

from alphaquant_core.engines.liquidity import GapDirection
from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult

CONTRACTION_THRESHOLD = 0.85


class WyckoffUpthrust(Playbook):
    name = "Wyckoff Upthrust"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        sweep = ctx.liquidity_sweep
        ratio = ctx.volatility_contraction_ratio

        if sweep is None or sweep.direction is not GapDirection.BEARISH:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["nenhum sweep de liquidez para cima detectado na candle atual"],
            )

        conditions = [
            ("Sweep de liquidez para cima (varredura da resistência)", True),
            (
                "Fechamento rejeita a resistência varrida",
                sweep.close_back_price < sweep.swept_price,
            ),
            (
                f"Volatilidade comprimida antes do upthrust (ATR < {CONTRACTION_THRESHOLD:.0%} da média)",
                ratio is not None and ratio < CONTRACTION_THRESHOLD,
            ),
        ]

        met = [c for c, ok in conditions if ok]
        missing = [c for c, ok in conditions if not ok]
        progress = 100.0 * len(met) / len(conditions)
        matched = len(missing) == 0

        entry = ctx.last_close if matched else None
        stop = sweep.swept_price if matched else None

        return PlaybookResult(
            self.name, matched, Direction.SHORT, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
        )
