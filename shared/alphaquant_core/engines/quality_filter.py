"""
Quality Filter (seção 27 do master prompt).

Mesmo um Score 95+ deve ser REPROVADO se: não houver Playbook confirmado,
RR abaixo do mínimo, stop não representar uma invalidação real, ou dados
insuficientes. Os limiares de Score/RR mínimos vêm da própria tabela
`playbooks` (colunas `minimum_score`/`minimum_rr`, já existentes desde a
Fase 1) — trocar o rigor de um playbook específico é uma linha no banco,
não uma mudança de código.

Não decide ENTRAR/ESPERAR/REPROVAR (isso é do Decision Engine — Fase 7);
apenas responde APROVADO/REPROVADO + motivos explícitos, sempre.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from alphaquant_core.engines.scoring import ScoreResult
from alphaquant_core.engines.targets import TargetResult
from alphaquant_core.playbooks.base import PlaybookResult

DEFAULT_MINIMUM_SCORE = 70.0
DEFAULT_MINIMUM_RR = 2.0


@dataclass(frozen=True)
class QualityFilterResult:
    approved: bool
    reasons: list[str] = field(default_factory=list)  # vazio quando aprovado


def evaluate_quality(
    playbook_result: PlaybookResult,
    target_result: TargetResult | None,
    score_result: ScoreResult,
    confidence: str,
    minimum_score: float = DEFAULT_MINIMUM_SCORE,
    minimum_rr: float = DEFAULT_MINIMUM_RR,
) -> QualityFilterResult:
    reasons: list[str] = []

    if not playbook_result.matched:
        reasons.append("Nenhum Playbook confirmado")

    if target_result is None:
        reasons.append("Stop não representa uma invalidação real — RR não pôde ser calculado")
    elif target_result.rr < minimum_rr:
        reasons.append(f"RR {target_result.rr:.2f} abaixo do mínimo exigido pelo playbook ({minimum_rr:.2f})")

    if score_result.total < minimum_score:
        reasons.append(f"Score {score_result.total:.1f} abaixo do mínimo exigido pelo playbook ({minimum_score:.1f})")

    if confidence == "BAIXA":
        reasons.append("Dados insuficientes para avaliação confiável (confidence BAIXA)")

    return QualityFilterResult(approved=len(reasons) == 0, reasons=reasons)
