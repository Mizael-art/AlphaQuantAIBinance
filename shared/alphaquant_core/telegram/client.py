"""
Cliente Telegram (seção 14). Wrapper fino sobre python-telegram-bot —
nunca hardcoda token/chat_id (vêm sempre de Settings/env vars).

Em TEST_MODE (seção 52), toda mensagem é prefixada com "🧪 TEST MODE" e
nenhum alerta deve ser tratado como sinal real — o prefixo é aplicado
aqui, uma única vez, para que nenhum outro ponto do sistema esqueça disso.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from telegram import Bot
from telegram.error import TelegramError

from alphaquant_core.services.rate_limiter import RateLimiter

logger = logging.getLogger("alphaquant.telegram")

# Telegram permite ~30 mensagens/segundo globais, mas é bem mais
# conservador por chat individual — este espaçamento é suficiente para
# o volume deste projeto e evita qualquer risco de 429 (seção 42).
MIN_SEND_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True)
class SendResult:
    success: bool
    message_id: str | None = None
    error: str | None = None


class TelegramClient:
    def __init__(self, bot_token: str, test_mode: bool = True, rate_limiter: RateLimiter | None = None) -> None:
        self._bot = Bot(token=bot_token)
        self.test_mode = test_mode
        self._rate_limiter = rate_limiter or RateLimiter(MIN_SEND_INTERVAL_SECONDS)

    def send_message(self, chat_id: str, text: str) -> SendResult:
        self._rate_limiter.wait()
        payload = f"🧪 TEST MODE\n\n{text}" if self.test_mode else text
        try:
            result = asyncio.run(self._bot.send_message(chat_id=chat_id, text=payload))
            return SendResult(success=True, message_id=str(result.message_id))
        except TelegramError as exc:
            logger.error("falha ao enviar mensagem Telegram para chat_id=%s: %s", chat_id, exc)
            return SendResult(success=False, error=str(exc))
