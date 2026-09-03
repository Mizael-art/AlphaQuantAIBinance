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

from datetime import datetime, timezone

logger = logging.getLogger("alphaquant.notifications.engine")


def process_new_setup(
    session: Session,
    record: SetupRecord,
    decision_info: dict | None = None,
) -> bool:
    """
    Processa notificação para um setup confirmado que passou pelo Final Trade Quality Gate.
    Registra signal_id, signal_sent_at, signal_message_id e signal_status.
    Retorna True se a notificação foi enviada com sucesso.
    """
    if not should_send_notification(session, record.id, "new_setup"):
        return False

    message = format_new_call(record, decision_info)
    result = send_message(message)

    telegram_msg_id = None
    if result and result.get("ok"):
        telegram_msg_id = result.get("result", {}).get("message_id")

    now_utc = datetime.now(timezone.utc)
    record.signal_id = f"SIG-{record.asset}-{now_utc.strftime('%Y%m%d%H%M%S')}-{record.id}"
    record.signal_sent_at = now_utc
    record.signal_message_id = telegram_msg_id
    record.signal_status = "SIGNAL_SENT"
    record.trade_opened_at = record.trade_opened_at or now_utc

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
    Processa notificações para eventos de trades ativos (TP1/2/3, STOP).
    Regra absoluta: NUNCA envia 'invalidated' para setups que não foram trades reais.

    Args:
        event_type: "tp1_hit" | "tp2_hit" | "tp3_hit" | "stop_hit" | "completed"
        reason: motivo do evento.

    Returns True se a notificação foi enviada.
    """
    # Se o setup nunca foi publicado como sinal no Telegram, NUNCA notificar eventos
    if record.signal_sent_at is None:
        return False

    if not should_send_notification(session, record.id, event_type):
        return False

    # Formatar mensagem baseada no tipo de evento
    if event_type.startswith("tp"):
        tp_map = {"tp1_hit": "TP1", "tp2_hit": "TP2", "tp3_hit": "TP3"}
        message = format_tp_hit(record, tp_map.get(event_type, "TP"))
    elif event_type in ("stop_hit", "invalidated"):
        message = format_stop_hit(record)
    elif event_type == "completed":
        message = format_tp_hit(record, "TP3")
    else:
        logger.info(f"[NOTIFY] Evento '{event_type}' para setup #{record.id} suprimido.")
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
    Regra de Ouro:
    - Se o setup nunca teve call enviada (signal_sent_at == None) -> SILÊNCIO TOTAL no Telegram.
    - Se o setup estava ativo com call e bateu no stop -> STOP HIT (nunca 'setup invalidado').
    - Se atingiu TP1/TP2/TP3 -> TP HIT.
    Retorna a quantidade de sinais enviados.
    """
    signals_sent = 0

    _NOTIFY_TRANSITIONS = {
        "TP1": "tp1_hit",
        "TP2": "tp2_hit",
        "TP3": "tp3_hit",
        "COMPLETED": "completed",
        "INVALIDATED": "stop_hit",  # Trade ativo que atinge stop deve virar STOP HIT, nunca mensagem de invalidado
    }

    for update in updates:
        new_status = update.get("to", "")
        event_type = _NOTIFY_TRANSITIONS.get(new_status)

        if event_type is None:
            continue

        setup_id = update.get("setup_id")
        if setup_id is None:
            continue

        record = session.get(SetupRecord, setup_id)
        if record is None:
            continue

        # REGRA ABSOLUTA: Se este setup nunca teve call enviada ao Telegram,
        # NUNCA enviar TP, STOP ou INVALIDADO ao grupo! Registrar apenas no banco.
        if record.signal_sent_at is None:
            logger.debug(f"[MONITOR] Setup #{setup_id} ({record.asset}) sem call enviada. Evento {new_status} mantido apenas interno.")
            continue

        reason = update.get("reason", "")
        sent = process_setup_event(session, record, event_type, reason)
        if sent:
            signals_sent += 1

    return signals_sent

