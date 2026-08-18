"""
Decision Engine (seção 28 do master prompt).

Resultado sempre um de três: ENTRAR / ESPERAR / REPROVAR — nunca
BUY/SELL/LONG/SHORT isolado (a direção já vem do PlaybookResult; aqui só
se decide SE agir).

Regra:
- Quality Filter reprovou -> REPROVAR (motivos do Quality Filter, sem
  reinterpretação — ele já é a fonte da verdade sobre bloqueios
  absolutos).
- Quality Filter aprovou E confidence == "ALTA" (todos os indicadores
  presentes E o HTF confirmado, ver Fase 5) -> ENTRAR.
- Quality Filter aprovou mas confidence não é "ALTA" (ex.: HTF
  indisponível neste ciclo) -> ESPERAR: a evidência já passou pelos
  bloqueios absolutos, mas ainda falta um dado que aumentaria a
  confiança da decisão — não é reprovação, é "ainda não".
"""
from __future__ import annotations

from dataclasses import dataclass, field

from alphaquant_core.engines.quality_filter import QualityFilterResult

ENTRAR = "ENTRAR"
ESPERAR = "ESPERAR"
REPROVAR = "REPROVAR"


@dataclass(frozen=True)
class DecisionResult:
    decision: str  # ENTRAR | ESPERAR | REPROVAR
    reasons: list[str] = field(default_factory=list)


def make_decision(quality_result: QualityFilterResult, confidence: str) -> DecisionResult:
    if not quality_result.approved:
        return DecisionResult(REPROVAR, list(quality_result.reasons))

    if confidence == "ALTA":
        return DecisionResult(ENTRAR, ["Quality Filter aprovado com dados de alta confiança"])

    return DecisionResult(
        ESPERAR,
        [f"Quality Filter aprovado, mas confidence={confidence} — aguardando confirmação adicional (ex.: HTF)"],
    )
