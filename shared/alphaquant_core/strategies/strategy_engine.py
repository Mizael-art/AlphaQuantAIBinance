"""
strategy_engine — roda todas as estrategias ATIVAS e executaveis contra
o mesmo StrategyContext (secao 17: cada estrategia roda independente,
nenhum resultado e' apagado) e devolve tambem o que NAO pode rodar
(UNSUPPORTED_CONDITION) para o Strategy Lab mostrar claramente (secao 15).

Tambem detecta STRATEGY_CONFLICT (secao 18): quando duas estrategias
ativas divergem de direcao para o MESMO ativo no MESMO ciclo, nenhuma
e' descartada — o conflito e' reportado para o Quality Filter/Ranking
reduzirem a confianca, se apropriado.
"""
from __future__ import annotations

from dataclasses import dataclass

from alphaquant_core.playbooks.base import PlaybookContext, PlaybookResult
from alphaquant_core.strategies.strategy_registry import StrategyDefinition, StrategyRegistry
from alphaquant_core.strategies.strategy_runner import PromptStrategy


@dataclass
class StrategyEngineResult:
    strategy_id: str
    strategy_name: str
    version_label: str
    result: PlaybookResult | None       # None quando status != RUNNABLE
    status: str                          # RUNNABLE | UNSUPPORTED_CONDITION | INVALID | INACTIVE


def evaluate_active_strategies(
    ctx: PlaybookContext, registry: StrategyRegistry,
) -> list[StrategyEngineResult]:
    out: list[StrategyEngineResult] = []
    for strategy in registry.list():
        version = strategy.current_version
        if strategy.status.value != "ACTIVE":
            out.append(StrategyEngineResult(
                strategy_id=strategy.strategy_id, strategy_name=strategy.name,
                version_label=version.version_label, result=None, status="INACTIVE",
            ))
            continue
        if version.validation.unsupported_conditions:
            out.append(StrategyEngineResult(
                strategy_id=strategy.strategy_id, strategy_name=strategy.name,
                version_label=version.version_label, result=None, status="UNSUPPORTED_CONDITION",
            ))
            continue
        if not version.validation.valid or version.parsed is None:
            out.append(StrategyEngineResult(
                strategy_id=strategy.strategy_id, strategy_name=strategy.name,
                version_label=version.version_label, result=None, status="INVALID",
            ))
            continue

        runner = PromptStrategy(version.parsed, version=version.version_label)
        result = runner.evaluate(ctx)
        out.append(StrategyEngineResult(
            strategy_id=strategy.strategy_id, strategy_name=strategy.name,
            version_label=version.version_label, result=result, status="RUNNABLE",
        ))
    return out


def detect_conflicts(results: list[StrategyEngineResult]) -> bool:
    """True se, entre as estrategias RUNNABLE que bateram (matched=True)
    para este ativo/ciclo, houver LONG e SHORT simultaneos."""
    directions = {
        r.result.direction for r in results
        if r.status == "RUNNABLE" and r.result and r.result.matched and r.result.direction
    }
    return len(directions) > 1
