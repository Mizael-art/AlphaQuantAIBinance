"""
Playbook 6 — Wyckoff Spring

Tese: dentro de uma faixa de compressão (volatilidade contraída), o preço
varre a liquidez abaixo do suporte da faixa (falso rompimento — "spring")
e reclama o nível, sinalizando acumulação e reversão para cima.

Diferença para o Liquidity Sweep Reversal (Playbook 2): aqui a exigência
de contexto de compressão prévia é obrigatória — sem ela, um sweep é só
um sweep, não um Spring de Wyckoff.
"""
from __future__ import annotations

from alphaquant_core.engines.liquidity import GapDirection
from alphaquant_core.playbooks.base import Direction, Playbook, PlaybookContext, PlaybookResult

CONTRACTION_THRESHOLD = 0.85  # ATR atual precisa estar abaixo de 85% da média para contar como faixa comprimida


class WyckoffSpring(Playbook):
    name = "Wyckoff Spring"
    version = "v1.0"

    def evaluate(self, ctx: PlaybookContext) -> PlaybookResult:
        sweep = ctx.liquidity_sweep
        ratio = ctx.volatility_contraction_ratio

        if sweep is None or sweep.direction is not GapDirection.BULLISH:
            return PlaybookResult(
                self.name, False, None, 0.0,
                conditions_missing=["nenhum sweep de liquidez para baixo detectado na candle atual"],
            )

        conditions = [
            ("Sweep de liquidez para baixo (varredura do suporte)", True),
            (
                "Fechamento reclama o suporte varrido",
                sweep.close_back_price > sweep.swept_price,
            ),
            (
                f"Volatilidade comprimida antes do spring (ATR < {CONTRACTION_THRESHOLD:.0%} da média)",
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
            self.name, matched, Direction.LONG, progress,
            conditions_met=met, conditions_missing=missing,
            entry=entry, stop=stop,
        )
