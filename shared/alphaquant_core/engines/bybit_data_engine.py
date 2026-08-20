"""
Bybit Data Engine — fonte PRINCIPAL de dados de mercado do AlphaQuant X
(seção 3 da especificação: "A FONTE PRINCIPAL deve ser a BYBIT").

Usa exclusivamente os endpoints públicos V5 (category=linear, USDT
Perpetual) — nenhuma API key é necessária ou aceita aqui, igual ao
`BinanceMarketDataClient` que ele substitui como cliente padrão nos
pontos de entrada do Worker (`orchestrator.fetch_and_persist`,
`worker/app/main.py`). O `BinanceMarketDataClient` original permanece no
código (não foi apagado — pode servir de fallback manual/comparação),
mas deixa de ser o cliente construído por padrão.

Nunca inventa dado (seção 3/15): se a Bybit não devolver candles
suficientes ou o símbolo não existir mais, o erro sobe como
`BybitRequestError` — quem chama decide marcar DATA_UNAVAILABLE, nunca
cair silenciosamente para um candle antigo.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

import requests

from alphaquant_core.engines.data_engine import Candle, MarketDataError
from alphaquant_core.services.rate_limiter import RateLimiter
from alphaquant_core.services.retry import retry_with_backoff

logger = logging.getLogger("alphaquant.bybit_data_engine")

BASE_URL = "https://api.bybit.com"

# Seção 5 — a Bybit V5 usa códigos de intervalo próprios (minutos, ou
# D/W/M). Mapeamos o vocabulário interno do AlphaQuant X (o mesmo usado
# em `SCAN_TIMEFRAMES`/`Strategy.timeframes`) para o código Bybit.
TIMEFRAMES: dict[str, str] = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "1w": "W",
}

MIN_REQUEST_INTERVAL_SECONDS = 0.15  # Bybit público permite bem mais; mantemos conservador (seção 58)
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
CATEGORY = "linear"  # USDT Perpetual (seção 4, prioridade 1)


class BybitRequestError(MarketDataError):
    """Erro de rede, HTTP, retCode de negócio ou payload inesperado da Bybit."""


class _RetryableBybitError(BybitRequestError):
    pass


class BybitMarketDataClient:
    """Cliente HTTP fino para os endpoints públicos V5 da Bybit usados
    pelo AlphaQuant X: kline, tickers, orderbook e instruments-info."""

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

    # ------------------------------------------------------------------
    def get_klines(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"timeframe não suportado: {timeframe}")
        if not (1 <= limit <= 1000):
            raise ValueError("limit deve estar entre 1 e 1000")

        raw = self._get("/v5/market/kline", {
            "category": CATEGORY, "symbol": symbol.upper(),
            "interval": TIMEFRAMES[timeframe], "limit": limit,
        })
        rows = raw.get("list", [])
        # Bybit devolve do mais recente para o mais antigo — invertemos
        # para manter a mesma ordem cronológica que o resto do sistema
        # espera (igual ao BinanceMarketDataClient).
        candles = [
            Candle(
                timestamp=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
                open=float(row[1]), high=float(row[2]), low=float(row[3]),
                close=float(row[4]), volume=float(row[5]),
            )
            for row in reversed(rows)
        ]
        return candles

    def get_ticker_price(self, symbol: str) -> float:
        raw = self._get("/v5/market/tickers", {"category": CATEGORY, "symbol": symbol.upper()})
        tickers = raw.get("list", [])
        if not tickers:
            raise BybitRequestError(f"nenhum ticker retornado para {symbol}")
        return float(tickers[0]["lastPrice"])

    def get_depth(self, symbol: str, limit: int = 50) -> dict:
        allowed_limits = {1, 25, 50, 100, 200}  # limites válidos para category=linear
        eff_limit = min((l for l in allowed_limits if l >= limit), default=200)
        return self._get("/v5/market/orderbook", {"category": CATEGORY, "symbol": symbol.upper(), "limit": eff_limit})

    def get_tickers(self) -> list[dict]:
        """Todos os tickers USDT Perpetual (preço, volume 24h, open
        interest) — usado por `discover_usdt_perpetual_symbols` para
        ranquear por liquidez (seção 4/51/58)."""
        raw = self._get("/v5/market/tickers", {"category": CATEGORY})
        return raw.get("list", [])

    def discover_usdt_perpetual_symbols(
        self, min_symbols: int = 50, max_symbols: int = 100,
    ) -> list[str]:
        """
        Descobre os contratos USDT Perpetual elegíveis na Bybit (seção
        4): status=Trading, quoteCoin=USDT, contrato linear, ranqueados
        por turnover de 24h (liquidez) — nunca uma lista fixa no código.

        Nunca falha silenciosamente: se, após os filtros, sobrarem menos
        símbolos que `min_symbols`, levanta `BybitRequestError` em vez de
        devolver uma lista curta demais sem avisar quem chamou.
        """
        instruments = self._get("/v5/market/instruments-info", {"category": CATEGORY, "status": "Trading"})
        eligible: set[str] = set()
        for row in instruments.get("list", []):
            if row.get("quoteCoin") != "USDT":
                continue
            if row.get("contractType") not in ("LinearPerpetual",):
                continue
            if row.get("status") != "Trading":
                continue
            eligible.add(row["symbol"])

        tickers = self.get_tickers()
        ranked = sorted(
            (t for t in tickers if t["symbol"] in eligible),
            key=lambda t: float(t.get("turnover24h") or 0.0),
            reverse=True,
        )
        # símbolos duplicados são impossíveis aqui (chave é o próprio
        # `symbol`, já deduplicado pelo `set` acima), mas preservamos a
        # checagem explícita pedida na seção 4 por segurança.
        seen: set[str] = set()
        ordered_unique: list[str] = []
        for t in ranked:
            sym = t["symbol"]
            if sym in seen:
                continue
            seen.add(sym)
            ordered_unique.append(sym)

        selected = ordered_unique[:max_symbols]
        if len(selected) < min_symbols:
            raise BybitRequestError(
                f"apenas {len(selected)} símbolos USDT Perpetual elegíveis na Bybit "
                f"(mínimo exigido: {min_symbols}) — não gerando lista incompleta silenciosamente"
            )
        return selected

    # ------------------------------------------------------------------
    def _get(self, path: str, params: dict) -> dict:
        def attempt() -> dict:
            self._rate_limiter.wait()
            url = f"{BASE_URL}{path}"
            try:
                response = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                raise _RetryableBybitError(f"falha de rede ao chamar {path}: {exc}") from exc

            if response.status_code != 200:
                message = f"Bybit respondeu {response.status_code} em {path}: {response.text[:300]}"
                if response.status_code in RETRYABLE_STATUS_CODES:
                    raise _RetryableBybitError(message)
                raise BybitRequestError(message)

            try:
                payload = response.json()
            except ValueError as exc:
                raise BybitRequestError(f"resposta não-JSON de {path}") from exc

            ret_code = payload.get("retCode")
            if ret_code != 0:
                message = f"Bybit retCode={ret_code} em {path}: {payload.get('retMsg')}"
                # retCode 10006 = rate limit; 10002/10016 = erro transiente de servidor
                if ret_code in (10006, 10002, 10016):
                    raise _RetryableBybitError(message)
                raise BybitRequestError(message)

            return payload.get("result", {})

        return retry_with_backoff(
            attempt,
            max_attempts=self._max_attempts,
            base_delay=self._retry_base_delay,
            should_retry=lambda exc: isinstance(exc, _RetryableBybitError),
            sleep=self._retry_sleep,
        )
