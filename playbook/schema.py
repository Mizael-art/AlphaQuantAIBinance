"""
playbook/schema.py
==================

Data structures and domain types for the 76-Playbook Strategy Factory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class PlaybookState(str, Enum):
    NO_SETUP = "NO_SETUP"
    DEVELOPING = "DEVELOPING"
    WATCH = "WATCH"
    NEAR_ENTRY = "NEAR_ENTRY"
    TRIGGERED = "TRIGGERED"
    INVALIDATED = "INVALIDATED"
    COMPLETED = "COMPLETED"


class PlaybookTier(str, Enum):
    TIER_S = "S"          # Maximum Confluence
    TIER_A_PLUS = "A+"    # High Edge / Primary Playbooks
    TIER_A = "A"          # Solid Systematic Edge
    TIER_B = "B"          # Acceptable Edge
    TIER_RESEARCH = "C"   # Observation / Research Only


class Backtestability(str, Enum):
    BACKTESTABLE = "BACKTESTABLE"                       # Fully executable in Strategy DSL
    DISCOVERY_ONLY = "DISCOVERY_ONLY"                   # MTF / Pattern supported in Discovery
    REQUIRES_ENGINE_SUPPORT = "REQUIRES_ENGINE_SUPPORT" # Dependent on external unstreamed feed


@dataclass(frozen=True, slots=True)
class PlaybookEvaluation:
    """Resultado da avaliação de um playbook sobre um ativo."""
    playbook_id: str
    playbook_name: str
    matched: bool
    direction: str  # "long" | "short"
    state: PlaybookState
    setup_score: float
    entry_score: float
    trade_score: float
    entry_zone: tuple[float, float] | None
    stop: float | None
    tp1: float | None
    tp2: float | None
    tp3: float | None
    rr: float | None
    reasons: list[str] = field(default_factory=list)
    missing_conditions: list[str] = field(default_factory=list)
    invalidation: str = ""
    cooldown_hours: float = 4.0
    requires_confirmation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "playbook_name": self.playbook_name,
            "matched": self.matched,
            "direction": self.direction,
            "state": self.state.value,
            "setup_score": round(self.setup_score, 1),
            "entry_score": round(self.entry_score, 1),
            "trade_score": round(self.trade_score, 1),
            "entry_zone": {"low": self.entry_zone[0], "high": self.entry_zone[1]} if self.entry_zone else None,
            "stop": self.stop,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "rr": self.rr,
            "reasons": self.reasons,
            "missing_conditions": self.missing_conditions,
            "invalidation": self.invalidation,
            "cooldown_hours": self.cooldown_hours,
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass(frozen=True, slots=True)
class PlaybookDefinition:
    """Definição formal de um playbook cadastrado no catálogo."""
    id: str
    name: str
    category: str
    style: str  # "day_trade" | "intraday" | "swing"
    directions: frozenset[str]  # {"long"}, {"short"}, {"long", "short"}
    tier: PlaybookTier
    compatible_regimes: frozenset[str]
    incompatible_regimes: frozenset[str]
    htf_timeframe: str
    mtf_timeframe: str
    ltf_timeframe: str
    min_rr: float
    min_score: int
    description: str
    backtestability: Backtestability
    evaluator: Callable[[dict[str, Any]], PlaybookEvaluation] | None = None
    required_indicators: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "style": self.style,
            "directions": sorted(self.directions),
            "tier": self.tier.value,
            "compatible_regimes": sorted(self.compatible_regimes),
            "incompatible_regimes": sorted(self.incompatible_regimes),
            "htf_timeframe": self.htf_timeframe,
            "mtf_timeframe": self.mtf_timeframe,
            "ltf_timeframe": self.ltf_timeframe,
            "min_rr": self.min_rr,
            "min_score": self.min_score,
            "description": self.description,
            "backtestability": self.backtestability.value,
            "required_indicators": self.required_indicators,
            "notes": self.notes,
        }
