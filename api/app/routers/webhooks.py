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
import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.models import ScannerEvent
from alphaquant_core.db.session import get_db

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

MAX_CLOCK_SKEW_SECONDS = 60


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
