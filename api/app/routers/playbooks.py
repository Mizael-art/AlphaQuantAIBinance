"""Endpoint de Playbooks (Fase 10) — lista os playbooks cadastrados e seus limiares/status."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from alphaquant_core.db.models import Playbook
from alphaquant_core.db.session import get_db

router = APIRouter(prefix="/playbooks", tags=["playbooks"])


@router.get("")
def list_playbooks(db: Session = Depends(get_db)) -> dict:
    rows = db.execute(select(Playbook).order_by(Playbook.id)).scalars().all()
    return {
        "count": len(rows),
        "playbooks": [
            {
                "id": p.id,
                "name": p.name,
                "version": p.version,
                "tier": p.tier,
                "minimum_score": p.minimum_score,
                "minimum_rr": p.minimum_rr,
                "status": p.status.value,
            }
            for p in rows
        ],
    }
