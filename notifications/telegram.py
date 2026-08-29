"""
notifications/telegram.py
============================

Cliente Telegram Bot API para envio de notificações.

Usa httpx para comunicação síncrona com a API do Telegram Bot.

Variáveis de ambiente (lidas dinamicamente a cada envio):
  TELEGRAM_BOT_TOKEN  — token do bot criado via @BotFather
  TELEGRAM_CHAT_ID    — ID do grupo/canal/usuário de destino
  TELEGRAM_ENABLED    — "true" para ativar envio real

Sem parse_mode frágil: mensagens com '<', '>', '&' de indicadores
e scores são entregues 100% sem erros de parsing de entidades.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("alphaquant.notifications.telegram")

_API_BASE = "https://api.telegram.org/bot{token}"
_SEND_TIMEOUT = 15  # segundos


def get_telegram_config() -> tuple[bool, str, str]:
    """Lê as variáveis de ambiente dinamicamente."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    enabled = os.environ.get("TELEGRAM_ENABLED", "false").strip().lower() == "true"
    return enabled, token, chat_id


def is_telegram_configured() -> bool:
    """Retorna True se o Telegram está habilitado e configurado."""
    enabled, token, chat_id = get_telegram_config()
    return enabled and bool(token) and bool(chat_id)


def send_message(text: str, chat_id: str | None = None) -> dict | None:
    """
    Envia uma mensagem ao Telegram.

    Args:
        text: conteúdo da mensagem (texto puro com emojis).
        chat_id: sobrescreve o TELEGRAM_CHAT_ID padrão se informado.

    Returns:
        dict com a resposta da API Telegram, ou None se em dry-run / falha.
    """
    enabled, bot_token, default_chat = get_telegram_config()
    target_chat = (chat_id or default_chat).strip()

    if not enabled:
        logger.info(f"[TELEGRAM DRY-RUN] TELEGRAM_ENABLED não está ativo (false). Mensagem não enviada.")
        return None

    if not bot_token:
        logger.warning("[TELEGRAM] TELEGRAM_BOT_TOKEN não configurado nas variáveis de ambiente.")
        return None

    if not target_chat:
        logger.warning("[TELEGRAM] TELEGRAM_CHAT_ID não configurado nas variáveis de ambiente.")
        return None

    url = f"{_API_BASE.format(token=bot_token)}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": target_chat,
        "text": text,
        "disable_web_page_preview": True,
    }

    try:
        with httpx.Client(timeout=_SEND_TIMEOUT) as client:
            response = client.post(url, json=payload)
            result = response.json()

            if response.is_success and result.get("ok"):
                msg_id = result.get("result", {}).get("message_id")
                logger.info(f"[TELEGRAM] Mensagem enviada com sucesso para {target_chat} (message_id={msg_id}).")
                return result
            else:
                logger.error(f"[TELEGRAM] Erro da API Telegram: {result}")
                return result

    except httpx.TimeoutException:
        logger.error(f"[TELEGRAM] Timeout ao enviar mensagem para chat {target_chat}.")
        return None
    except Exception as exc:
        logger.error(f"[TELEGRAM] Erro ao enviar mensagem Telegram: {exc}")
        return None


def check_connection() -> str:
    """Verifica se o bot está conectado. Retorna status string."""
    enabled, bot_token, _ = get_telegram_config()
    if not enabled:
        return "disabled"
    if not bot_token:
        return "not_configured"

    url = f"{_API_BASE.format(token=bot_token)}/getMe"
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(url)
            result = response.json()
            if response.is_success and result.get("ok"):
                bot_name = result.get("result", {}).get("username", "unknown")
                return f"connected (@{bot_name})"
            return f"error: {result.get('description', 'invalid token')}"
    except Exception as exc:
        return f"unreachable ({exc})"
