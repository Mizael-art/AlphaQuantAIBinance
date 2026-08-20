"""
POST /webhooks/tradingview

Regras da seção 12/13 do master prompt:
- autenticar a origem (HMAC do TRADINGVIEW_WEBHOOK_SECRET);
- validar payload;
- validar timestamp / evitar replay;
- registrar evento (scanner_events);
- responder rapidamente — o processamento pesado é do Worker, não da API.

Nunca aceitar payload sem assinatura válida. Nunca aceitar credenciais
dentro do corpo do webhook.
"""
import asyncio
import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.models import ScannerEvent
from alphaquant_core.db.session import get_db
from alphaquant_core.services.manual_scan_service import request_manual_scan
from alphaquant_core.telegram.client import TelegramClient

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("alphaquant.webhooks.telegram")

MAX_CLOCK_SKEW_SECONDS = 60

# Comandos que disparam uma análise manual imediata (aceita com ou sem
# "/" e ignora o sufixo "@NomeDoBot" que o Telegram anexa em grupos).
MANUAL_SCAN_COMMANDS = {"/analisar", "/scan", "/analyze"}


def _verify_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/tradingview", status_code=status.HTTP_202_ACCEPTED)
async def tradingview_webhook(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()
    raw_body = await request.body()

    if not _verify_signature(raw_body, x_signature, settings.TRADINGVIEW_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")

    payload = await request.json()

    event_timestamp = payload.get("timestamp")
    if event_timestamp is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing timestamp")
    if abs(time.time() - float(event_timestamp)) > MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="stale or replayed event")

    asset = payload.get("asset")
    if not asset:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="missing asset")

    # Apenas registra o evento — o Worker é quem processa o scan pesado.
    event = ScannerEvent(event_type="tradingview_alert", asset=asset, payload=payload)
    db.add(event)
    db.commit()

    return {"accepted": True, "event_id": event.id}


def _is_authorized_chat(chat_id: str, settings) -> bool:
    """
    Só reage a comandos vindos do grupo/chat já configurado no sistema
    (TELEGRAM_SIGNALS_CHAT_ID ou TELEGRAM_FUTURE_CHAT_ID) — evita que
    qualquer pessoa que descubra o bot no Telegram dispare scans.
    """
    return chat_id in {str(settings.TELEGRAM_SIGNALS_CHAT_ID), str(settings.TELEGRAM_FUTURE_CHAT_ID)}


@router.post("/telegram", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Recebe os `updates` do Telegram (configurado via `setWebhook`, ver
    docs/DEPLOY.md). Hoje só entende o comando manual de análise
    (`/analisar`, `/scan` ou `/analyze`), enviado no grupo do bot:
    grava um `ManualScanRequest` que o Worker/scanner embutido consome
    no próximo poll (`wait_for_next_cycle`), interrompendo a espera do
    ciclo agendado e rodando a análise na hora.

    Sempre responde 200 rapidamente (mesmo para updates que ignora) —
    é o que o Telegram espera para não ficar reentregando o update.
    """
    settings = get_settings()

    if settings.TELEGRAM_WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid secret token")

    update = await request.json()
    message = update.get("message") or update.get("channel_post") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id")) if chat.get("id") is not None else None
    username = (message.get("from") or {}).get("username")

    if not text or chat_id is None:
        return {"ok": True}

    command = text.split()[0].split("@")[0].lower()
    if command not in MANUAL_SCAN_COMMANDS:
        return {"ok": True}

    if not _is_authorized_chat(chat_id, settings):
        logger.warning("comando /analisar recebido de chat não autorizado chat_id=%s", chat_id)
        client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)
        # send_message é síncrono e usa asyncio.run() por baixo — rodar
        # direto aqui quebraria com "cannot be called from a running
        # event loop" (este endpoint já roda dentro do loop do Uvicorn).
        await asyncio.to_thread(
            client.send_message, chat_id, "⚠️ Este chat não está autorizado a disparar análises do ALPHAQUANT X.",
        )
        return {"ok": True}

    request_manual_scan(db, chat_id=chat_id, username=username)
    logger.info("análise manual enfileirada por chat_id=%s username=%s", chat_id, username)

    client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)
    ack_result = await asyncio.to_thread(
        client.send_message, chat_id, "🔍 Pedido recebido. Iniciando análise do mercado...",
    )
    if not ack_result.success:
        logger.error("falha ao enviar confirmação de /analisar: %s", ack_result.error)

    return {"ok": True}
