"""
Strategy Engine — infraestrutura para estrategias definidas por PROMPT,
sem precisar alterar o core do scanner (Playbook Engine) para adicionar
uma estrategia nova.

Uma StrategyDefinition (nome + prompt em texto) e' parseada em uma
arvore de Condition (strategy_parser), validada contra o vocabulario
suportado pelo MarketContext atual (strategy_validator) e transformada
em um PromptStrategy que implementa a MESMA interface Playbook usada
pelos 10 playbooks hardcoded (strategy_runner) — ou seja, o Playbook
Engine existente (playbooks/engine.py) roda estrategias de prompt e
estrategias hardcoded lado a lado sem saber a diferenca.

Modulos:
    strategy_context   -> alias/helpers sobre PlaybookContext (MarketContext)
    strategy_parser     -> prompt (texto) -> arvore de Condition
    strategy_validator   -> valida a arvore contra o vocabulario suportado
    strategy_runner      -> PromptStrategy(Playbook): avalia a arvore contra o contexto
    strategy_registry    -> CRUD + versionamento de StrategyDefinition (em memoria,
                            com adaptador para persistencia via api/app depois)
    strategy_engine       -> orquestra: roda todas as estrategias ativas contra o
                            mesmo contexto, detecta STRATEGY_CONFLICT e UNSUPPORTED_CONDITION
"""
from alphaquant_core.strategies.strategy_context import StrategyContext, get_field
from alphaquant_core.strategies.strategy_parser import ParseError, StrategyPrompt, parse_prompt
from alphaquant_core.strategies.strategy_validator import ValidationResult, validate_prompt
from alphaquant_core.strategies.strategy_registry import (
    StrategyDefinition,
    StrategyRegistry,
    StrategyStatus,
    StrategyVersion,
)
from alphaquant_core.strategies.strategy_runner import PromptStrategy
from alphaquant_core.strategies.strategy_engine import (
    StrategyEngineResult,
    detect_conflicts,
    evaluate_active_strategies,
)

__all__ = [
    "StrategyContext",
    "get_field",
    "ParseError",
    "StrategyPrompt",
    "parse_prompt",
    "ValidationResult",
    "validate_prompt",
    "StrategyDefinition",
    "StrategyRegistry",
    "StrategyStatus",
    "StrategyVersion",
    "PromptStrategy",
    "StrategyEngineResult",
    "detect_conflicts",
    "evaluate_active_strategies",
]
