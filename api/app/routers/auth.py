"""POST /auth/login — seção 24."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import create_access_token, verify_credentials

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    if not verify_credentials(payload.username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="usuário ou senha inválidos")
    token, expires_in = create_access_token(payload.username)
    return LoginResponse(access_token=token, expires_in=expires_in)
