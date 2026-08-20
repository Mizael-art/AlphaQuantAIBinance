"""
Data Engine — coleta de dados públicos da Binance.

Fase 3, escopo conforme o [[alphaquant-engine]]: apenas endpoints públicos
(klines, ticker/price, depth), sem API key. Nunca faz scraping do
TradingView (seção 12 do master prompt) — a fonte de candles é sempre a
Binance pública.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

import requests

from alphaquant_core.services.rate_limiter import RateLimiter
from alphaquant_core.services.retry import retry_with_backoff

logger = logging.getLogger("alphaquant.data_engine")

BASE_URL = "https://api.binance.com"

# Timeframes suportados e seus equivalentes na API da Binance
TIMEFRAMES = {
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

# Espaçamento mínimo entre chamadas (seção 42 — rate limiting). A Binance
# pública permite uma taxa bem maior; este valor é conservador de propósito
# para nunca arriscar 429/ban num projeto com um único Worker.
MIN_REQUEST_INTERVAL_SECONDS = 0.25

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class MarketDataError(RuntimeError):
    """
    Erro de rede, HTTP ou payload inesperado de qualquer fonte de dados
    de mercado (Binance ou Bybit). Base comum introduzida ao adicionar o
    `BybitMarketDataClient` (seção 3) para que quem já captura erros de
    coleta (`except BinanceRequestError`/agora `except MarketDataError`)
    continue funcionando sem precisar saber qual exchange está por trás.
    """


class BinanceRequestError(MarketDataError):
    """Erro de rede, HTTP ou payload inesperado da Binance."""


class _RetryableBinanceError(BinanceRequestError):
    """Subclasse interna — sinaliza ao retry_with_backoff que vale tentar de novo."""


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataClient(Protocol):
    """
    Interface estrutural compartilhada por `BinanceMarketDataClient` e
    `BybitMarketDataClient` — quem só precisa buscar candles/preço não
    depende de qual exchange está por trás (usado nos type hints de
    `orchestrator.py`/`playbooks/runner.py`).
    """

    def get_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]: ...
    def get_ticker_price(self, symbol: str) -> float: ...
    def get_depth(self, symbol: str, limit: int = 50) -> dict: ...


class BinanceMarketDataClient:
    """
    Cliente HTTP fino para os três endpoints públicos usados pelo
    AlphaQuant X: klines, ticker/price e depth. Nenhuma credencial é
    necessária ou aceita aqui.

    Self-healing (seção 39): erros transientes (timeout, conexão, 429,
    5xx) são retentados com backoff exponencial (até 3 tentativas); erros
    do cliente (400, 404 — símbolo inválido, parâmetro errado) falham
    imediatamente, já que tentar de novo não mudaria o resultado.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 10.0,
        max_attempts: int = 3,
        rate_limiter: RateLimiter | None = None,
        retry_base_delay: float = 0.5,
        retry_sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._session = session or requests.Session()
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._rate_limiter = rate_limiter or RateLimiter(MIN_REQUEST_INTERVAL_SECONDS)
        self._retry_base_delay = retry_base_delay
        self._retry_sleep = retry_sleep or time.sleep

    def get_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"timeframe não suportado: {timeframe}")
        if not (1 <= limit <= 1000):
            raise ValueError("limit deve estar entre 1 e 1000")

        params = {
            "symbol": symbol.upper(),
            "interval": TIMEFRAMES[timeframe],
            "limit": limit,
        }
        raw = self._get("/api/v3/klines", params)

        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in raw
        ]
        return candles

    def get_ticker_price(self, symbol: str) -> float:
        raw = self._get("/api/v3/ticker/price", {"symbol": symbol.upper()})
        return float(raw["price"])

    def get_depth(self, symbol: str, limit: int = 50) -> dict:
        allowed_limits = {5, 10, 20, 50, 100, 500, 1000, 5000}
        if limit not in allowed_limits:
            raise ValueError(f"limit deve ser um de {sorted(allowed_limits)}")
        return self._get("/api/v3/depth", {"symbol": symbol.upper(), "limit": limit})

    def _get(self, path: str, params: dict) -> dict | list:
        def attempt() -> dict | list:
            self._rate_limiter.wait()
            url = f"{BASE_URL}{path}"
            try:
                response = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                raise _RetryableBinanceError(f"falha de rede ao chamar {path}: {exc}") from exc

            if response.status_code != 200:
                message = f"Binance respondeu {response.status_code} em {path}: {response.text[:300]}"
                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise _RetryableBinanceError(message)
                raise BinanceRequestError(message)

            try:
                return response.json()
            except ValueError as exc:
                raise BinanceRequestError(f"resposta não-JSON de {path}") from exc

        return retry_with_backoff(
            attempt,
            max_attempts=self._max_attempts,
            base_delay=self._retry_base_delay,
            should_retry=lambda exc: isinstance(exc, _RetryableBinanceError),
            sleep=self._retry_sleep,
        )
