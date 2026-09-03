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

# Tipos de sinal que SEMPRE devem ser notificados (somente para trades ativos com call prévia)
_ALWAYS_NOTIFY_TYPES = frozenset({
    "tp1_hit", "tp2_hit", "tp3_hit",
    "stop_hit", "completed",
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
    Regra absoluta:
    - new_setup: só envia se não foi enviado anteriormente para este setup_id.
    - tp_hit / stop_hit: só envia se o setup REALMENTE teve call prévia (signal_type == 'new_setup')
      e este evento específico ainda não foi enviado.
    - invalidated: NUNCA envia ao Telegram (evento puramente interno).
    """
    # Invalidação de setups NÃO executados é estritamente interna -- NUNCA notifica o Telegram
    if signal_type == "invalidated":
        return False

    # Eventos de trade executado (TP / STOP)
    if signal_type in _ALWAYS_NOTIFY_TYPES:
        # Só envia TP/STOP se o setup REALMENTE teve uma call prévia (em telegram_signals ou setup_record.signal_sent_at)
        prev_call_stmt = select(TelegramSignal).where(
            TelegramSignal.setup_id == setup_id,
            TelegramSignal.signal_type == "new_setup",
        )
        prev_call = session.execute(prev_call_stmt).scalars().first()
        if prev_call is None:
            from persistence.models import SetupRecord
            setup_rec = session.get(SetupRecord, setup_id)
            if setup_rec is None or setup_rec.signal_sent_at is None:
                logger.info(f"[DEDUP] Setup #{setup_id} nunca teve call publicada no Telegram. Update '{signal_type}' suprimido.")
                return False


        # Verifica se já enviamos este evento específico para este setup
        stmt = select(TelegramSignal).where(
            TelegramSignal.setup_id == setup_id,
            TelegramSignal.signal_type == signal_type,
        )
        existing = session.execute(stmt).scalars().first()
        if existing is not None:
            logger.info(f"[DEDUP] {signal_type} para setup #{setup_id} já foi enviado anteriormente. Suprimido.")
            return False
        return True

    # Para new_setup, verificar se já foi enviado para este setup_id
    if signal_type == "new_setup":
        stmt = select(TelegramSignal).where(
            TelegramSignal.setup_id == setup_id,
            TelegramSignal.signal_type == "new_setup",
        )
        existing = session.execute(stmt).scalars().first()
        if existing is not None:
            logger.info(f"[DEDUP] Setup #{setup_id} já foi publicado no Telegram. Nova call suprimida.")
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
