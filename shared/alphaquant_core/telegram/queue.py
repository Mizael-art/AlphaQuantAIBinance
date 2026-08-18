"""
Fila de mensagens Telegram (seções 43-44): a tabela `alerts` É a fila —
`enqueue_alert` grava um evento `PENDING`; `process_pending_alerts` (o
"Telegram Worker" da seção 43) processa a fila, chama a API real e
atualiza `telegram_status`/`message_id`/`retry_count`/`error`.

Retry: até 3 tentativas (seção 44); depois disso, `FAILED` definitivo —
nunca reenviar uma mensagem já `SENT` (idempotência de entrega).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.models import Alert, AlertType, Opportunity, TelegramStatus
from alphaquant_core.telegram.client import TelegramClient
from alphaquant_core.telegram.formatting import (
    format_future_message,
    format_invalidation_message,
    format_signal_message,
)

logger = logging.getLogger("alphaquant.telegram.queue")

MAX_RETRIES = 3

_FORMATTERS = {
    AlertType.SIGNAL: format_signal_message,
    AlertType.FUTURE: format_future_message,
    AlertType.INVALIDATION: format_invalidation_message,
}


def enqueue_alert(db: Session, opportunity: Opportunity, alert_type: AlertType) -> Alert:
    settings = get_settings()
    chat_id = settings.TELEGRAM_SIGNALS_CHAT_ID if alert_type == AlertType.SIGNAL else settings.TELEGRAM_FUTURE_CHAT_ID

    alert = Alert(
        opportunity_id=opportunity.id,
        alert_type=alert_type,
        telegram_status=TelegramStatus.PENDING,
        chat_id=chat_id,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def process_pending_alerts(db: Session, client: TelegramClient) -> tuple[int, int]:
    """Devolve (enviados, falhados) neste lote."""
    sent = 0
    failed = 0

    pending = db.query(Alert).filter_by(telegram_status=TelegramStatus.PENDING).all()
    for alert in pending:
        opportunity = db.query(Opportunity).filter_by(id=alert.opportunity_id).one_or_none()
        if opportunity is None:
            alert.telegram_status = TelegramStatus.FAILED
            alert.error = "Opportunity associada não existe mais"
            db.commit()
            failed += 1
            continue

        formatter = _FORMATTERS[alert.alert_type]
        text = formatter(opportunity)
        result = client.send_message(alert.chat_id, text)

        if result.success:
            alert.telegram_status = TelegramStatus.SENT
            alert.message_id = result.message_id
            alert.sent_at = datetime.now(timezone.utc)
            sent += 1
        else:
            alert.retry_count += 1
            alert.error = result.error
            if alert.retry_count >= MAX_RETRIES:
                alert.telegram_status = TelegramStatus.FAILED
                logger.error(
                    "alerta id=%s esgotou %s tentativas, marcado FAILED: %s",
                    alert.id, MAX_RETRIES, result.error,
                )
                failed += 1
            # abaixo de MAX_RETRIES: continua PENDING, tenta de novo no próximo ciclo

        db.commit()

    return sent, failed
