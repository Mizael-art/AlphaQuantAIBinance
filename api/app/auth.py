"""
auth — login protegido do Strategy Lab (seção 24).

Credenciais nunca hardcoded no frontend: `ALPHAQUANT_ADMIN_USER`/
`ALPHAQUANT_ADMIN_PASSWORD` vêm de `Settings` (variável de ambiente),
com os valores padrão pedidos pela própria especificação
(AlphaQuant/VIP) só para não deixar a instalação inutilizável antes de
alguém configurar o ambiente — qualquer deploy real deve sobrescrever.
"""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Header, HTTPException, status

from alphaquant_core.core.config import get_settings

ALGORITHM = "HS256"
TOKEN_TTL = timedelta(hours=24)


def verify_credentials(username: str, password: str) -> bool:
    settings = get_settings()
    # comparação em tempo constante — não vaza timing de qual caractere diverge
    user_ok = hmac.compare_digest(username, settings.ALPHAQUANT_ADMIN_USER)
    pass_ok = hmac.compare_digest(password, settings.ALPHAQUANT_ADMIN_PASSWORD)
    return user_ok and pass_ok


def create_access_token(username: str) -> tuple[str, int]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + TOKEN_TTL
    payload = {"sub": username, "iat": int(now.timestamp()), "exp": int(expires_at.timestamp())}
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)
    return token, int(TOKEN_TTL.total_seconds())


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expirado") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token inválido") from exc


def require_admin(authorization: str | None = Header(default=None)) -> str:
    """Dependency do FastAPI: protege qualquer rota do Strategy Lab
    (seção 23 — 'Essa página deve possuir autenticação')."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="credenciais ausentes")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    return payload["sub"]
