"""
Persistência das Fases 5-7: a partir de um PlaybookResult + TargetResult
+ ScoreResult + QualityFilterResult (Fase 6) + DecisionResult (Fase 7),
cria ou atualiza a `Opportunity` correspondente e grava uma linha em
`evidence` por critério pontuado (seção 57 — Auditoria: "por que esse
trade foi classificado como 84?" precisa ter resposta exata).

Chave natural da Opportunity: asset+timeframe+playbook+direction — o
mesmo registro é atualizado em cada ciclo em que esse playbook continuar
batendo para esse ativo/timeframe/direção, independente do status atual
(inclusive já REPROVADO/INVALIDATED anteriormente: uma condição de
mercado pode melhorar entre ciclos e um REPROVAR virar ENTRAR sem gerar
uma linha nova). Isso significa que o rastreamento por OCORRÊNCIA
histórica (duas Springs distintas no mesmo ativo/timeframe em datas
diferentes) ainda não é distinguido — fica para a Fase 11/12 (Future
Opportunity Engine / Analytics), que vão precisar de uma chave mais fina
que inclua o timestamp do evento estrutural que originou o sinal.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from alphaquant_core.db.models import Direction as DBDirection
from alphaquant_core.db.models import DecisionResult as DBDecisionResult
from alphaquant_core.db.models import Evidence, Opportunity, OpportunityStatus
from alphaquant_core.engines.decision import ENTRAR, ESPERAR, REPROVAR, DecisionResult
from alphaquant_core.engines.quality_filter import QualityFilterResult
from alphaquant_core.engines.scoring import ScoreResult
from alphaquant_core.engines.targets import TargetResult
from alphaquant_core.playbooks.base import PlaybookContext, PlaybookResult

ALGORITHM_VERSION = "v1.0"

_STATUS_BY_DECISION = {
    ENTRAR: OpportunityStatus.CONFIRMED,
    ESPERAR: OpportunityStatus.FORMATION,
    REPROVAR: OpportunityStatus.INVALIDATED,
}


def compute_confidence(ctx: PlaybookContext) -> str:
    """
    CONFIDENCE mede qualidade/completude dos DADOS disponíveis (seção
    25) — nunca depende de `target_result`: se o playbook ainda não
    bateu (Future Opportunity, Fase 11), naturalmente não há entry/stop/
    RR ainda, mas isso não significa que os DADOS sejam de baixa
    qualidade. Ausência de RR é assunto de Score/Execução, não de
    Confidence — cada um dos três precisa continuar independente.
    """
    indicators_complete = all(
        ctx.indicators.get(k) is not None
        for k in ("ema20", "ema50", "ema100", "ema200", "rsi14", "atr14")
    )
    if not indicators_complete:
        return "BAIXA"
    if ctx.htf_regime is None:
        return "MODERADA"
    return "ALTA"


def _as_float(value: float | None) -> float | None:
    """Garante Python float nativo — numpy.float64 quebra a adaptação do driver psycopg2."""
    return None if value is None else float(value)


def upsert_opportunity(
    db: Session,
    ctx: PlaybookContext,
    playbook_result: PlaybookResult,
    target_result: TargetResult | None,
    score_result: ScoreResult,
    quality_result: QualityFilterResult,
    decision_result: DecisionResult,
    playbook_version: str = "v1.0",
) -> Opportunity:
    direction = DBDirection(playbook_result.direction.value)

    existing = (
        db.query(Opportunity)
        .filter_by(asset=ctx.symbol.upper(), timeframe=ctx.timeframe, playbook=playbook_result.playbook, direction=direction)
        .order_by(Opportunity.created_at.desc())
        .first()
    )

    is_new = existing is None
    if is_new:
        existing = Opportunity(
            asset=ctx.symbol.upper(), timeframe=ctx.timeframe,
            playbook=playbook_result.playbook, direction=direction,
            status=OpportunityStatus.FORMATION,
        )
        db.add(existing)

    previous_status = None if is_new else existing.status

    existing.score = _as_float(score_result.total)
    existing.confidence = compute_confidence(ctx)
    existing.progress = _as_float(playbook_result.progress)
    existing.entry = _as_float(playbook_result.entry)
    existing.stop = _as_float(playbook_result.stop)
    existing.tp1 = _as_float(target_result.tp1) if target_result else None
    existing.tp2 = _as_float(target_result.tp2) if target_result else None
    existing.tp3 = _as_float(target_result.tp3) if target_result else None
    existing.rr = _as_float(target_result.rr) if target_result else None
    existing.playbook_version = playbook_version
    existing.algorithm_version = ALGORITHM_VERSION
    existing.decision = DBDecisionResult(decision_result.decision)
    existing.status = _STATUS_BY_DECISION[decision_result.decision]
    if decision_result.decision == REPROVAR and previous_status != OpportunityStatus.INVALIDATED:
        existing.invalidated_at = datetime.now(timezone.utc)
    elif decision_result.decision != REPROVAR:
        existing.invalidated_at = None  # reaprovado num ciclo seguinte — não é mais uma invalidação

    existing.audit_snapshot = {
        "conditions_met": playbook_result.conditions_met,
        "conditions_missing": playbook_result.conditions_missing,
        "score_breakdown": [
            {"category": c.category, "name": c.name, "points": _as_float(c.points), "max_points": _as_float(c.max_points)}
            for c in score_result.criteria
        ],
        "targets": (
            [{"price": _as_float(t.price), "source": t.source} for t in target_result.targets]
            if target_result else []
        ),
        "regime": ctx.regime,
        "htf_regime": ctx.htf_regime,
        "quality_filter": {
            "approved": quality_result.approved,
            "reasons": quality_result.reasons,
        },
        "decision": {
            "decision": decision_result.decision,
            "reasons": decision_result.reasons,
        },
    }

    db.flush()  # garante existing.id para as linhas de evidence

    db.query(Evidence).filter_by(opportunity_id=existing.id).delete()
    for c in score_result.criteria:
        db.add(Evidence(
            opportunity_id=existing.id,
            category=c.category,
            evidence=c.name,
            score=_as_float(c.points),
        ))
    db.add(Evidence(
        opportunity_id=existing.id,
        category="QUALITY_FILTER",
        evidence="APROVADO" if quality_result.approved else "REPROVADO: " + "; ".join(quality_result.reasons),
        score=100.0 if quality_result.approved else 0.0,
    ))
    db.add(Evidence(
        opportunity_id=existing.id,
        category="DECISION_ENGINE",
        evidence=f"{decision_result.decision}: " + "; ".join(decision_result.reasons),
        score=100.0 if decision_result.decision == ENTRAR else (50.0 if decision_result.decision == ESPERAR else 0.0),
    ))

    db.commit()
    db.refresh(existing)
    return existing


def upsert_future_opportunity(
    db: Session,
    ctx: PlaybookContext,
    playbook_result: PlaybookResult,
    score_result: ScoreResult,
    playbook_version: str = "v1.0",
) -> Opportunity | None:
    """
    Fase 11 — Future Opportunity Engine (seção 24). Para um playbook que
    ainda NÃO bateu (`matched=False`) mas já tem direção e progresso
    (`progress>0`), registra um setup "em formação": `status=FORMATION`,
    `decision=None` (nunca passa pelo Quality Filter/Decision Engine —
    esses são exclusivos de playbooks confirmados), sem entry/stop/RR
    (ainda não existem de verdade).

    Se um setup que estava em formação perder as condições (progress
    volta a 0 no mesmo asset+timeframe+playbook+direction), a
    Opportunity correspondente é movida para `INVALIDATED` (seção 18 —
    "SETUP INVALIDADO") em vez de ficar parada para sempre em
    `FORMATION`. **Limitação conhecida**: se a direção do viés mudar
    entre ciclos (ex.: o mesmo playbook passa a apontar SHORT em vez de
    LONG), a Opportunity antiga do lado oposto não é localizada aqui
    (a direção faz parte da chave de busca) e fica órfã em `FORMATION`
    até expirar por outra via — cenário raro, aceito por ora.

    Nunca sobrescreve uma Opportunity que já foi totalmente avaliada
    (`CONFIRMED`/`INVALIDATED` por um ciclo anterior do pipeline
    completo) — só `upsert_opportunity` pode mexer nessas. Isso evita
    que uma leitura parcial "rebaixe" por engano um sinal que já virou
    ENTRAR/REPROVAR de verdade.

    Devolve `None` (não persiste/altera nada) se não há direção definida
    — sem direção não há nem como localizar um setup pra invalidar.
    """
    if playbook_result.direction is None:
        return None

    direction = DBDirection(playbook_result.direction.value)

    existing = (
        db.query(Opportunity)
        .filter_by(asset=ctx.symbol.upper(), timeframe=ctx.timeframe, playbook=playbook_result.playbook, direction=direction)
        .order_by(Opportunity.created_at.desc())
        .first()
    )

    if playbook_result.progress <= 0:
        if existing is not None and existing.status == OpportunityStatus.FORMATION:
            existing.status = OpportunityStatus.INVALIDATED
            existing.invalidated_at = datetime.now(timezone.utc)
            existing.progress = 0.0
            existing.audit_snapshot = {
                **(existing.audit_snapshot or {}),
                "quality_filter": {
                    "approved": False,
                    "reasons": ["Setup em formação perdeu as condições do playbook (progress voltou a 0%)"],
                },
                "decision": None,
            }
            db.commit()
            db.refresh(existing)
            return existing
        return None  # nunca existiu — nada a invalidar

    if existing is not None and existing.status != OpportunityStatus.FORMATION:
        return None  # já CONFIRMED/INVALIDATED por um ciclo completo — só ele mexe nisso

    is_new = existing is None
    if is_new:
        existing = Opportunity(
            asset=ctx.symbol.upper(), timeframe=ctx.timeframe,
            playbook=playbook_result.playbook, direction=direction,
            status=OpportunityStatus.FORMATION,
        )
        db.add(existing)

    existing.score = _as_float(score_result.total)
    existing.confidence = compute_confidence(ctx)
    existing.progress = _as_float(playbook_result.progress)
    existing.entry = None
    existing.stop = None
    existing.tp1 = None
    existing.tp2 = None
    existing.tp3 = None
    existing.rr = None
    existing.playbook_version = playbook_version
    existing.algorithm_version = ALGORITHM_VERSION
    existing.decision = None
    existing.invalidated_at = None

    existing.audit_snapshot = {
        "conditions_met": playbook_result.conditions_met,
        "conditions_missing": playbook_result.conditions_missing,
        "score_breakdown": [
            {"category": c.category, "name": c.name, "points": _as_float(c.points), "max_points": _as_float(c.max_points)}
            for c in score_result.criteria
        ],
        "targets": [],
        "regime": ctx.regime,
        "htf_regime": ctx.htf_regime,
        "quality_filter": None,  # Future Opportunities não passam pelo Quality Filter
        "decision": None,        # nem pelo Decision Engine — só quando o playbook confirmar de verdade
    }

    db.flush()

    db.query(Evidence).filter_by(opportunity_id=existing.id).delete()
    for c in score_result.criteria:
        db.add(Evidence(
            opportunity_id=existing.id,
            category=c.category,
            evidence=c.name,
            score=_as_float(c.points),
        ))

    db.commit()
    db.refresh(existing)
    return existing
