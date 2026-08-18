"""
Endpoint de resumo (Fase 10, reaproveitado pela Fase 12 — Analytics) —
os cards do Dashboard principal (seção 31): Score>=80, Score>=90, status
do scanner, etc.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Opportunity, OpportunityStatus, SystemHealth
from alphaquant_core.db.session import get_db

router = APIRouter(prefix="/summary", tags=["summary"])


@router.get("")
def get_summary(db: Session = Depends(get_db)) -> dict:
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    total_24h = db.execute(
        select(func.count()).select_from(Opportunity).where(Opportunity.updated_at >= since)
    ).scalar()
    score_70 = db.execute(
        select(func.count()).select_from(Opportunity).where(Opportunity.updated_at >= since, Opportunity.score >= 70)
    ).scalar()
    score_80 = db.execute(
        select(func.count()).select_from(Opportunity).where(Opportunity.updated_at >= since, Opportunity.score >= 80)
    ).scalar()
    score_90 = db.execute(
        select(func.count()).select_from(Opportunity).where(Opportunity.updated_at >= since, Opportunity.score >= 90)
    ).scalar()
    confirmed = db.execute(
        select(func.count()).select_from(Opportunity)
        .where(Opportunity.updated_at >= since, Opportunity.status == OpportunityStatus.CONFIRMED)
    ).scalar()
    formation = db.execute(
        select(func.count()).select_from(Opportunity)
        .where(Opportunity.updated_at >= since, Opportunity.status == OpportunityStatus.FORMATION)
    ).scalar()
    invalidated = db.execute(
        select(func.count()).select_from(Opportunity)
        .where(Opportunity.updated_at >= since, Opportunity.status == OpportunityStatus.INVALIDATED)
    ).scalar()

    health_rows = db.execute(select(SystemHealth)).scalars().all()
    scanner = next((h for h in health_rows if h.service == "worker"), None)

    return {
        "window": "24h",
        "opportunities_analyzed": total_24h,
        "score_ge_70": score_70,
        "score_ge_80": score_80,
        "score_ge_90": score_90,
        "confirmed": confirmed,
        "future_formation": formation,
        "invalidated": invalidated,
        "scanner_status": scanner.status if scanner else "UNKNOWN",
        "scanner_last_heartbeat": scanner.last_heartbeat if scanner else None,
    }
