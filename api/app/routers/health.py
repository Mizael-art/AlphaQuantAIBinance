"""
Seção 37/38 do master prompt — System Health / Heartbeat.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import SystemHealth
from alphaquant_core.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(SystemHealth)).scalars().all()
    services = {
        row.service: {
            "status": row.status,
            "last_heartbeat": row.last_heartbeat,
            "latency_ms": row.latency_ms,
        }
        for row in rows
    }
    return {
        "status": "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services": services,
    }
