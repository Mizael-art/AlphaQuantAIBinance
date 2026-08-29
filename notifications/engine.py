"""
notifications/engine.py
=========================

Motor de notificações que conecta o pipeline ao Telegram.

Regras (conforme especificação):
  - WATCH → sem Telegram
  - NEAR_ENTRY → normalmente sem Telegram
  - LONG_NOW/SHORT_NOW + Risk Approved → Telegram (new_setup)
  - TP1/TP2/TP3 → Telegram (tp_hit)
  - STOP → Telegram (stop_hit)
  - INVALIDATED → Telegram quando aplicável
  - Mesma call a cada ciclo → SUPRIMIDA pelo dedup

Este módulo é chamado pelo autonomous_cycle APÓS criar/atualizar setups.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from notifications.dedup import record_signal_sent, should_send_notification
from notifications.formatter import (
    format_invalidated,
    format_new_call,
    format_stop_hit,
    format_tp_hit,
)
from notifications.telegram import send_message
from persistence.models import SetupRecord

logger = logging.getLogger("alphaquant.notifications.engine")


def process_new_setup(
    session: Session,
    record: SetupRecord,
    decision_info: dict | None = None,
) -> bool:
    """
    Processa notificação para um setup recém-criado.
    Retorna True se a notificação foi enviada.
    """
    if not should_send_notification(session, record.id, "new_setup"):
        return False

    message = format_new_call(record, decision_info)
    result = send_message(message)

    telegram_msg_id = None
    if result and result.get("ok"):
        telegram_msg_id = result.get("result", {}).get("message_id")

    record_signal_sent(
        session,
        setup_id=record.id,
        signal_type="new_setup",
        message_text=message,
        telegram_message_id=telegram_msg_id,
    )
    return True


def process_setup_event(
    session: Session,
    record: SetupRecord,
    event_type: str,
    reason: str = "",
) -> bool:
    """
    Processa notificações para eventos de setup (TP, stop, invalidação).

    Args:
        event_type: "tp1_hit" | "tp2_hit" | "tp3_hit" | "stop_hit" | "invalidated" | "completed"
        reason: motivo do evento (para invalidação).

    Returns True se a notificação foi enviada.
    """
    if not should_send_notification(session, record.id, event_type):
        return False

    # Formatar mensagem baseada no tipo de evento
    if event_type.startswith("tp"):
        tp_map = {"tp1_hit": "TP1", "tp2_hit": "TP2", "tp3_hit": "TP3"}
        message = format_tp_hit(record, tp_map.get(event_type, "TP"))
    elif event_type == "stop_hit":
        message = format_stop_hit(record)
    elif event_type == "invalidated":
        message = format_invalidated(record, reason)
    else:
        logger.info(f"[NOTIFY] Evento '{event_type}' para setup #{record.id} não tem template. Suprimido.")
        return False

    result = send_message(message)

    telegram_msg_id = None
    if result and result.get("ok"):
        telegram_msg_id = result.get("result", {}).get("message_id")

    record_signal_sent(
        session,
        setup_id=record.id,
        signal_type=event_type,
        message_text=message,
        telegram_message_id=telegram_msg_id,
    )
    return True


def process_monitoring_updates(
    session: Session,
    updates: list[dict],
) -> int:
    """
    Processa notificações baseadas nos updates do monitoring cycle.
    Retorna a quantidade de sinais enviados.

    Args:
        updates: lista de dicts do MonitoringCycleResult.updated
                 ex: [{"setup_id": 42, "asset": "BTCUSDT", "from": "ACTIVE", "to": "TP1", "reason": "..."}]
    """
    signals_sent = 0

    # Mapeamento de transições para tipos de evento notificáveis
    _NOTIFY_TRANSITIONS = {
        "TP1": "tp1_hit",
        "TP2": "tp2_hit",
        "TP3": "tp3_hit",
        "COMPLETED": "completed",
        "INVALIDATED": "invalidated",
    }

    for update in updates:
        new_status = update.get("to", "")
        event_type = _NOTIFY_TRANSITIONS.get(new_status)

        if event_type is None:
            continue  # Transição não gera notificação

        setup_id = update.get("setup_id")
        if setup_id is None:
            continue

        record = session.get(SetupRecord, setup_id)
        if record is None:
            continue

        reason = update.get("reason", "")
        sent = process_setup_event(session, record, event_type, reason)
        if sent:
            signals_sent += 1

    return signals_sent
