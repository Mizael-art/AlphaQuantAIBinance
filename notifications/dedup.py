"""
notifications/dedup.py
========================

Sistema de deduplicação e cooldown para notificações Telegram.

Regras:
  - Nunca enviar a mesma call 2x para o mesmo setup_id + signal_type
  - Cooldown de 4h entre atualizações do mesmo setup
  - Exceções: tp_hit, stop_hit, invalidated → sempre notificar
  - Dedup por setup_id + event_type (não por símbolo)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from persistence.models import TelegramSignal

logger = logging.getLogger("alphaquant.notifications.dedup")

# Tipos de sinal que SEMPRE devem ser notificados, sem cooldown
_ALWAYS_NOTIFY_TYPES = frozenset({
    "tp1_hit", "tp2_hit", "tp3_hit",
    "stop_hit", "invalidated", "completed",
    "stop_moved",
})

# Cooldown padrão entre notificações do mesmo setup (em horas)
_DEFAULT_COOLDOWN_HOURS = 4


def should_send_notification(
    session: Session,
    setup_id: int,
    signal_type: str,
    cooldown_hours: float = _DEFAULT_COOLDOWN_HOURS,
) -> bool:
    """
    Decide se uma notificação deve ser enviada ao Telegram.

    Args:
        session: sessão SQLAlchemy ativa.
        setup_id: ID persistente do setup.
        signal_type: tipo do evento (new_setup, update, tp1_hit, etc.)
        cooldown_hours: horas mínimas entre notificações do mesmo setup.

    Returns:
        True se a notificação deve ser enviada, False se deve ser suprimida.
    """
    # Eventos críticos sempre passam
    if signal_type in _ALWAYS_NOTIFY_TYPES:
        # Se for invalidação, só envia se o setup REALMENTE teve uma call prévia enviada ao grupo
        if signal_type == "invalidated":
            prev_call_stmt = select(TelegramSignal).where(
                TelegramSignal.setup_id == setup_id,
                TelegramSignal.signal_type == "new_setup",
            )
            prev_call = session.execute(prev_call_stmt).scalars().first()
            if prev_call is None:
                logger.info(f"[DEDUP] Setup #{setup_id} nunca foi enviado como call no Telegram. Invalidação suprimida.")
                return False

        # Mas verifica se já enviamos EXATAMENTE este tipo para este setup
        stmt = select(TelegramSignal).where(
            TelegramSignal.setup_id == setup_id,
            TelegramSignal.signal_type == signal_type,
        )
        existing = session.execute(stmt).scalars().first()
        if existing is not None:
            logger.info(f"[DEDUP] {signal_type} para setup #{setup_id} já foi enviado. Suprimido.")
            return False
        return True

    # Para outros tipos, verificar cooldown
    now = datetime.now(timezone.utc)
    cooldown_threshold = now - timedelta(hours=cooldown_hours)

    stmt = select(TelegramSignal).where(
        TelegramSignal.setup_id == setup_id,
    ).order_by(TelegramSignal.sent_at.desc())
    recent = session.execute(stmt).scalars().first()

    if recent is not None and recent.sent_at is not None:
        sent_at = recent.sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        hours_ago = (now - sent_at).total_seconds() / 3600
        if hours_ago < cooldown_hours:
            logger.info(
                f"[DEDUP] Setup #{setup_id} notificado há {hours_ago:.1f}h "
                f"(cooldown: {cooldown_hours}h). Suprimido."
            )
            return False

    return True


def record_signal_sent(
    session: Session,
    setup_id: int,
    signal_type: str,
    message_text: str,
    telegram_message_id: int | None = None,
    chat_id: str | None = None,
) -> TelegramSignal:
    """Registra no banco que uma notificação foi enviada (para dedup futura)."""
    record = TelegramSignal(
        setup_id=setup_id,
        signal_type=signal_type,
        message_text=message_text,
        telegram_message_id=telegram_message_id,
        chat_id=chat_id,
    )
    session.add(record)
    session.flush()
    return record
