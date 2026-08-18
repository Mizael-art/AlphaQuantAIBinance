"""
Scoring Engine (seção 26 do master prompt).

Contexto (35) + Estrutura (35) + Execução (30) = 100, bônus de até +5,
nunca ultrapassa 100. O Score mede qualidade da evidência disponível,
NUNCA probabilidade de lucro — cada ponto vem de um critério nomeado e
auditável (nunca um número mágico), porque é isso que alimenta a tabela
`evidence` e responde "por que o sistema classificou esse trade como 84?"
(seção 57 — Auditoria).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from alphaquant_core.engines.targets import TargetResult
from alphaquant_core.playbooks.base import Direction, PlaybookContext, PlaybookResult

CONTEXTO_MAX = 35.0
ESTRUTURA_MAX = 35.0
EXECUCAO_MAX = 30.0
BONUS_MAX = 5.0
SCORE_MAX = 100.0


@dataclass(frozen=True)
class ScoreCriterion:
    category: str  # "CONTEXTO" | "ESTRUTURA" | "EXECUCAO" | "BONUS"
    name: str
    points: float
    max_points: float


@dataclass(frozen=True)
class ScoreResult:
    total: float  # 0-100, já com o cap aplicado
    criteria: list[ScoreCriterion] = field(default_factory=list)

    def breakdown_by_category(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for c in self.criteria:
            totals[c.category] = totals.get(c.category, 0.0) + c.points
        return totals


def _contexto(ctx: PlaybookContext, direction: Direction) -> list[ScoreCriterion]:
    criteria: list[ScoreCriterion] = []

    # Regime de estrutura definido e alinhado com a direção do playbook (15)
    aligned = (direction is Direction.LONG and ctx.regime == "BULLISH") or (
        direction is Direction.SHORT and ctx.regime == "BEARISH"
    )
    regime_defined = ctx.regime != "UNDEFINED"
    pts = 15.0 if aligned else (7.5 if regime_defined else 0.0)
    criteria.append(ScoreCriterion(
        "CONTEXTO",
        "Regime de estrutura definido e alinhado com a direção" if aligned else
        "Regime de estrutura definido mas não totalmente alinhado" if regime_defined else
        "Regime de estrutura indefinido",
        pts, 15.0,
    ))

    # HTF confirma o mesmo regime (10) — 0 se HTF não disponível neste ciclo
    if ctx.htf_regime is not None:
        htf_aligned = ctx.htf_regime == ctx.regime or ctx.regime == "UNDEFINED"
        pts = 10.0 if (ctx.htf_regime != "UNDEFINED" and htf_aligned) else 0.0
        criteria.append(ScoreCriterion(
            "CONTEXTO",
            "Timeframe maior (HTF) confirma o mesmo regime" if pts else "HTF não confirma o regime atual",
            pts, 10.0,
        ))
    else:
        criteria.append(ScoreCriterion("CONTEXTO", "HTF não disponível neste ciclo", 0.0, 10.0))

    # RSI não esticado contra a direção do trade (10)
    rsi = ctx.indicators.get("rsi14")
    if rsi is not None:
        not_stretched = (rsi <= 80) if direction is Direction.LONG else (rsi >= 20)
        pts = 10.0 if not_stretched else 0.0
        criteria.append(ScoreCriterion(
            "CONTEXTO",
            "RSI não esticado contra a direção do trade" if pts else "RSI esticado no lado contrário",
            pts, 10.0,
        ))
    else:
        criteria.append(ScoreCriterion("CONTEXTO", "RSI indisponível", 0.0, 10.0))

    return criteria


def _estrutura(ctx: PlaybookContext, playbook_result: PlaybookResult) -> list[ScoreCriterion]:
    criteria: list[ScoreCriterion] = []

    # Playbook confirmado por completo (20)
    pts = 20.0 if playbook_result.matched else 20.0 * (playbook_result.progress / 100.0) * 0.5
    criteria.append(ScoreCriterion(
        "ESTRUTURA",
        f"Playbook '{playbook_result.playbook}' confirmado" if playbook_result.matched else
        f"Playbook '{playbook_result.playbook}' parcialmente confirmado ({playbook_result.progress:.0f}%)",
        round(pts, 2), 20.0,
    ))

    # Order Blocks e/ou FVGs não preenchidos dão suporte à estrutura (15)
    supporting_zones = len(ctx.order_blocks) + len([g for g in ctx.fair_value_gaps if not g.filled])
    pts = min(15.0, supporting_zones * 5.0)
    criteria.append(ScoreCriterion(
        "ESTRUTURA",
        f"{supporting_zones} zona(s) de suporte estrutural ativa(s) (Order Blocks/FVGs)",
        pts, 15.0,
    ))

    return criteria


def _execucao(target_result: TargetResult | None) -> list[ScoreCriterion]:
    criteria: list[ScoreCriterion] = []

    if target_result is None:
        criteria.append(ScoreCriterion("EXECUCAO", "Stop inválido — RR não pôde ser calculado", 0.0, EXECUCAO_MAX))
        return criteria

    rr = target_result.rr
    if rr < 2:
        pts, label = 0.0, f"RR {rr:.2f} abaixo do mínimo (< 2) — reprovaria no Quality Filter"
    elif rr < 3:
        pts, label = 15.0, f"RR {rr:.2f} aceitável (2-3)"
    elif rr <= 5:
        pts, label = 22.5, f"RR {rr:.2f} excelente (3-5)"
    else:
        pts, label = 25.0, f"RR {rr:.2f} excepcional (>5)"
    criteria.append(ScoreCriterion("EXECUCAO", label, pts, 25.0))

    structural_targets = sum(1 for t in target_result.targets if t.source == "structural")
    pts = min(5.0, structural_targets * 2.5)
    criteria.append(ScoreCriterion(
        "EXECUCAO",
        f"{structural_targets} alvo(s) estrutural(is) real(is) (não apenas múltiplos de R)",
        pts, 5.0,
    ))

    return criteria


def compute_score(
    ctx: PlaybookContext,
    playbook_result: PlaybookResult,
    target_result: TargetResult | None,
) -> ScoreResult:
    if playbook_result.direction is None:
        return ScoreResult(total=0.0, criteria=[
            ScoreCriterion("CONTEXTO", "Sem direção definida pelo playbook", 0.0, CONTEXTO_MAX),
            ScoreCriterion("ESTRUTURA", "Sem direção definida pelo playbook", 0.0, ESTRUTURA_MAX),
            ScoreCriterion("EXECUCAO", "Sem direção definida pelo playbook", 0.0, EXECUCAO_MAX),
        ])

    criteria = [
        *_contexto(ctx, playbook_result.direction),
        *_estrutura(ctx, playbook_result),
        *_execucao(target_result),
    ]

    # Bônus (+5): playbook confirmado E RR excepcional (>5) ao mesmo tempo
    bonus = 0.0
    if playbook_result.matched and target_result is not None and target_result.rr > 5:
        bonus = 5.0
    criteria.append(ScoreCriterion("BONUS", "Playbook confirmado + RR excepcional", bonus, BONUS_MAX))

    raw_total = sum(c.points for c in criteria)
    total = min(SCORE_MAX, raw_total)  # nunca ultrapassa 100 (seção 26)

    return ScoreResult(total=round(total, 2), criteria=criteria)
