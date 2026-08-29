"""
notifications/telegram.py
============================

Cliente Telegram Bot API para envio de notificações.

Usa httpx (síncrono) para simplicidade — o volume de mensagens é
baixo (poucas calls por ciclo) e não justifica complexidade async.

Variáveis de ambiente:
  TELEGRAM_BOT_TOKEN  — token do bot criado via @BotFather
  TELEGRAM_CHAT_ID    — ID do grupo/canal de destino
  TELEGRAM_ENABLED    — "true" para ativar envio real

Nunca hardcode secrets. Se as variáveis não existirem, o módulo
opera em modo dry-run (loga mas não envia).
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("alphaquant.notifications.telegram")

_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
_ENABLED = os.environ.get("TELEGRAM_ENABLED", "false").lower() == "true"

_API_BASE = "https://api.telegram.org/bot{token}"
_SEND_TIMEOUT = 15  # segundos


def is_telegram_configured() -> bool:
    """Retorna True se o Telegram está habilitado e configurado."""
    return _ENABLED and bool(_BOT_TOKEN) and bool(_CHAT_ID)


def send_message(text: str, chat_id: str | None = None) -> dict | None:
    """
    Envia uma mensagem ao Telegram.

    Args:
        text: conteúdo da mensagem (plain text).
        chat_id: sobrescreve o TELEGRAM_CHAT_ID padrão.

    Returns:
        dict com a resposta da API Telegram, ou None se em dry-run / falha.
    """
    target_chat = chat_id or _CHAT_ID

    if not _ENABLED:
        logger.info(f"[TELEGRAM DRY-RUN] Telegram desabilitado. Mensagem suprimida ({len(text)} chars).")
        return None

    if not _BOT_TOKEN or not target_chat:
        logger.warning("[TELEGRAM] BOT_TOKEN ou CHAT_ID não configurados. Mensagem não enviada.")
        return None

    url = f"{_API_BASE.format(token=_BOT_TOKEN)}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        with httpx.Client(timeout=_SEND_TIMEOUT) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            result = response.json()

            if result.get("ok"):
                msg_id = result.get("result", {}).get("message_id")
                logger.info(f"[TELEGRAM] Mensagem enviada com sucesso (message_id={msg_id}).")
                return result
            else:
                logger.error(f"[TELEGRAM] API retornou erro: {result}")
                return None

    except httpx.TimeoutException:
        logger.error(f"[TELEGRAM] Timeout ao enviar mensagem para chat {target_chat}.")
        return None
    except httpx.HTTPStatusError as exc:
        logger.error(f"[TELEGRAM] HTTP {exc.response.status_code}: {exc.response.text}")
        return None
    except Exception as exc:
        logger.error(f"[TELEGRAM] Erro inesperado: {exc}")
        return None


def check_connection() -> str:
    """Verifica se o bot está conectado. Retorna status string."""
    if not _ENABLED:
        return "disabled"
    if not _BOT_TOKEN:
        return "not_configured"

    url = f"{_API_BASE.format(token=_BOT_TOKEN)}/getMe"
    try:
        with httpx.Client(timeout=5) as client:
            response = client.get(url)
            response.raise_for_status()
            result = response.json()
            if result.get("ok"):
                bot_name = result.get("result", {}).get("username", "unknown")
                return f"connected ({bot_name})"
            return "error"
    except Exception:
        return "unreachable"
