"""
Endpoints de Opportunities (Fase 10) — o Dashboard consome só a API,
nunca acessa o banco diretamente (ver docs/PROJECT_PLAN.md, Fase 10).
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Evidence, Opportunity
from alphaquant_core.db.session import get_db

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _opportunity_summary(opp: Opportunity) -> dict:
    return {
        "id": opp.id,
        "asset": opp.asset,
        "timeframe": opp.timeframe,
        "playbook": opp.playbook,
        "direction": opp.direction.value,
        "status": opp.status.value,
        "decision": opp.decision.value if opp.decision else None,
        "score": opp.score,
        "confidence": opp.confidence,
        "progress": opp.progress,
        "entry": opp.entry,
        "stop": opp.stop,
        "tp1": opp.tp1,
        "tp2": opp.tp2,
        "tp3": opp.tp3,
        "rr": opp.rr,
        "created_at": opp.created_at,
        "updated_at": opp.updated_at,
        "invalidated_at": opp.invalidated_at,
    }


@router.get("")
def list_opportunities(
    status: str | None = Query(default=None),
    playbook: str | None = Query(default=None),
    asset: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
) -> dict:
    stmt = select(Opportunity).order_by(Opportunity.updated_at.desc()).limit(limit)
    if status:
        stmt = stmt.where(Opportunity.status == status.upper())
    if playbook:
        stmt = stmt.where(Opportunity.playbook == playbook)
    if asset:
        stmt = stmt.where(Opportunity.asset == asset.upper())

    rows = db.execute(stmt).scalars().all()
    return {"count": len(rows), "opportunities": [_opportunity_summary(o) for o in rows]}


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: int, db: Session = Depends(get_db)) -> dict:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity não encontrada")

    evidence = (
        db.execute(select(Evidence).where(Evidence.opportunity_id == opportunity_id).order_by(Evidence.timestamp))
        .scalars()
        .all()
    )

    return {
        **_opportunity_summary(opp),
        "audit_snapshot": opp.audit_snapshot,
        "evidence": [
            {"category": e.category, "evidence": e.evidence, "score": e.score, "timestamp": e.timestamp}
            for e in evidence
        ],
    }
