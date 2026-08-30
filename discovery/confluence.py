"""
discovery/confluence.py
=======================

Strategy Confluence & Conflict Resolution Engine for AlphaQuant X.

Consolidates multiple playbook detections on the same asset into a single
high-conviction opportunity (preventing duplicate trades/spam) and detects
opposing directional conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from playbook.schema import PlaybookEvaluation, PlaybookState


@dataclass(frozen=True, slots=True)
class ConsolidatedOpportunity:
    """Oportunidade única consolidada com confluências e resolução de conflitos."""
    asset: str
    direction: str  # "long" | "short"
    primary_playbook_id: str
    primary_playbook_name: str
    secondary_playbooks: list[str]
    confluence_count: int
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
    invalidation: str = ""
    conflict_detected: bool = False
    conflict_details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset": self.asset,
            "direction": self.direction,
            "primary_playbook_id": self.primary_playbook_id,
            "primary_playbook_name": self.primary_playbook_name,
            "secondary_playbooks": self.secondary_playbooks,
            "confluence_count": self.confluence_count,
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
            "invalidation": self.invalidation,
            "conflict_detected": self.conflict_detected,
            "conflict_details": self.conflict_details,
        }


def consolidate_evaluations(
    asset: str,
    evaluations: list[PlaybookEvaluation],
) -> list[ConsolidatedOpportunity]:
    """
    Consolida todas as avaliações de playbooks de um ativo, agrupando por
    direção dominante e calculando confluência real.
    """
    if not evaluations:
        return []

    matched_evals = [e for e in evaluations if e.matched]
    if not matched_evals:
        return []

    long_evals = [e for e in matched_evals if e.direction == "long"]
    short_evals = [e for e in matched_evals if e.direction == "short"]

    results: list[ConsolidatedOpportunity] = []

    # Determinar se há conflito direcional relevante
    has_conflict = bool(long_evals and short_evals)
    conflict_msg = f"Conflito: {len(long_evals)} Playbooks de LONG vs {len(short_evals)} Playbooks de SHORT" if has_conflict else ""

    # Processar lado dominante ou ambos se sem conflito severo
    for evals_group, direction in [(long_evals, "long"), (short_evals, "short")]:
        if not evals_group:
            continue

        # Ordenar pelo maior trade_score
        sorted_evals = sorted(evals_group, key=lambda e: e.trade_score, reverse=True)
        primary = sorted_evals[0]
        secondary_names = [e.playbook_name for e in sorted_evals[1:]]

        confluence_count = len(evals_group)
        # Bônus de confluência (+3 pontos por playbook adicional independente)
        bonus = min((confluence_count - 1) * 3.0, 10.0)
        penalty = 15.0 if has_conflict else 0.0

        setup_score = min(max(primary.setup_score + bonus - penalty, 0.0), 100.0)
        entry_score = min(max(primary.entry_score - (penalty * 0.5), 0.0), 100.0)
        trade_score = (0.60 * setup_score) + (0.40 * entry_score)

        # Se houver conflito forte, rebaixa o estado para WATCH para evitar entrada precipitada
        state = primary.state
        if has_conflict and state == PlaybookState.TRIGGERED:
            state = PlaybookState.WATCH

        all_reasons = list(primary.reasons)
        for e in sorted_evals[1:3]:
            all_reasons.extend(e.reasons)

        consolidated = ConsolidatedOpportunity(
            asset=asset,
            direction=direction,
            primary_playbook_id=primary.playbook_id,
            primary_playbook_name=primary.playbook_name,
            secondary_playbooks=secondary_names,
            confluence_count=confluence_count,
            state=state,
            setup_score=setup_score,
            entry_score=entry_score,
            trade_score=trade_score,
            entry_zone=primary.entry_zone,
            stop=primary.stop,
            tp1=primary.tp1,
            tp2=primary.tp2,
            tp3=primary.tp3,
            rr=primary.rr,
            reasons=all_reasons,
            invalidation=primary.invalidation,
            conflict_detected=has_conflict,
            conflict_details=conflict_msg,
        )
        results.append(consolidated)

    return results
