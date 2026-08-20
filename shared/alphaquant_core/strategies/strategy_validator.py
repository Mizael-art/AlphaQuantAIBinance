"""
strategy_validator — valida uma StrategyPrompt ja parseada contra o
vocabulario que o MarketContext atual sabe calcular.

Regra de ouro (secao 15): se o prompt usar um campo que o sistema nao
suporta, a estrategia NUNCA e' silenciosamente aceita com esse campo
ignorado ou trocado por outro. Ela fica bloqueada com
UNSUPPORTED_CONDITION ate o prompt ser corrigido ou o campo ganhar
suporte — e isso deve aparecer claramente no painel (Strategy Lab).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from alphaquant_core.strategies.strategy_context import (
    KNOWN_BUT_UNSUPPORTED_FIELDS,
    SUPPORTED_FIELDS,
)
from alphaquant_core.strategies.strategy_parser import Condition, StrategyPrompt

_VALID_OPS_NUMERIC = {">", "<", ">=", "<="}
_VALID_OPS_ANY = {"==", "!="}


@dataclass
class ValidationResult:
    valid: bool
    unsupported_conditions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.unsupported_conditions:
            return "UNSUPPORTED_CONDITION"
        if not self.valid:
            return "INVALID"
        return "VALID"


def _validate_condition(cond: Condition, errors: list[str], unsupported: list[str]) -> None:
    if cond.field in KNOWN_BUT_UNSUPPORTED_FIELDS:
        unsupported.append(
            f"{cond.raw!r}: campo {cond.field} reconhecido no vocabulario mas ainda "
            "sem suporte de dado no MarketContext"
        )
        return
    if cond.field not in SUPPORTED_FIELDS:
        unsupported.append(f"{cond.raw!r}: campo {cond.field} desconhecido")
        return

    if cond.op in _VALID_OPS_NUMERIC:
        try:
            float(cond.value)
        except ValueError:
            errors.append(f"{cond.raw!r}: operador {cond.op} exige valor numerico, recebeu {cond.value!r}")
    # operadores == / != aceitam tanto numero quanto rotulo (ex.: BULLISH, ABOVE, BELOW)


def validate_prompt(prompt: StrategyPrompt) -> ValidationResult:
    errors: list[str] = []
    unsupported: list[str] = []

    for cond in prompt.conditions:
        _validate_condition(cond, errors, unsupported)
    for cond in prompt.invalidation:
        _validate_condition(cond, errors, unsupported)

    if prompt.stop.kind == "UNSUPPORTED":
        errors.append(
            "STOP nao reconhecido ou ausente — nunca inventamos stop "
            "(secoes 15 e 35); use SWING_LOW, SWING_HIGH, ATR(mult) ou FIXED_PCT(pct)"
        )
    if not prompt.targets:
        errors.append("TARGETS ausente — defina ao menos um alvo (RR <numero> ou PRICE <numero>)")

    valid = not errors and not unsupported
    return ValidationResult(valid=valid, unsupported_conditions=unsupported, errors=errors)
