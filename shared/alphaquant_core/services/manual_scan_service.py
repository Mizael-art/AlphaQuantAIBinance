"""
Serviço da fila de pedidos de análise manual (comando /analisar do bot
no Telegram — ver `api/app/routers/webhooks.py::telegram_webhook`).

O fluxo é deliberadamente simples porque só precisa responder uma
pergunta ao Worker: "alguém pediu uma análise fora do horário agendado
desde a última vez que eu chequei?". Nenhuma fila com prioridade,
nenhum retry — se dois pedidos chegarem no mesmo intervalo curto de
polling, `claim_pending_manual_scan` já marca os dois como processados
de uma vez (um único ciclo de scan responde por todos).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from alphaquant_core.db.models import ManualScanRequest


@dataclass(frozen=True)
class ManualScanClaim:
    """
    Cópia simples (não presa à Session) dos dados do pedido manual mais
    recente — devolvida por `claim_pending_manual_scan` já depois do
    commit que fecha a fila, para que o chamador possa ler os campos
    mesmo depois de fechar a sessão (o objeto ORM original expiraria).
    """
    id: int
    requested_by_chat_id: str
    requested_by_username: str | None
    requested_at: datetime


def request_manual_scan(db: Session, chat_id: str, username: str | None = None) -> ManualScanRequest:
    request = ManualScanRequest(requested_by_chat_id=chat_id, requested_by_username=username)
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def has_pending_manual_scan(db: Session) -> bool:
    return db.execute(
        select(ManualScanRequest.id).where(ManualScanRequest.processed_at.is_(None)).limit(1)
    ).scalar_one_or_none() is not None


def claim_pending_manual_scan(db: Session) -> ManualScanClaim | None:
    """
    Marca TODOS os pedidos pendentes como processados (mesmo ciclo de
    scan cobre qualquer um que tenha chegado enquanto o worker ainda
    não tinha reagido) e devolve o mais recente, para uso em mensagens
    ("análise pedida por @fulano"). None se não havia nenhum pendente.

    Devolve um `ManualScanClaim` (dataclass simples) em vez do objeto
    ORM: o chamador tipicamente fecha a Session logo em seguida (ver
    `worker/app/main.py::wait_for_next_cycle`), e um `ManualScanRequest`
    expirado por `db.commit()` levantaria `DetachedInstanceError` ao ler
    qualquer atributo depois disso.
    """
    latest_row = db.execute(
        select(ManualScanRequest)
        .where(ManualScanRequest.processed_at.is_(None))
        .order_by(ManualScanRequest.requested_at.desc())
    ).scalars().first()

    if latest_row is None:
        return None

    claim = ManualScanClaim(
        id=latest_row.id,
        requested_by_chat_id=latest_row.requested_by_chat_id,
        requested_by_username=latest_row.requested_by_username,
        requested_at=latest_row.requested_at,
    )

    now = datetime.now(timezone.utc)
    db.execute(
        update(ManualScanRequest).where(ManualScanRequest.processed_at.is_(None)).values(processed_at=now)
    )
    db.commit()
    return claim
