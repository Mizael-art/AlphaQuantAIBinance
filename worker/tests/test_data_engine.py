from unittest.mock import MagicMock

import pytest

from alphaquant_core.engines.data_engine import (
    BinanceMarketDataClient,
    BinanceRequestError,
)
from alphaquant_core.services.rate_limiter import RateLimiter


def _mock_session(json_payload, status_code=200):
    session = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_payload
    response.text = str(json_payload)
    session.get.return_value = response
    return session


def test_get_klines_parses_binance_payload():
    raw_klines = [
        [1700000000000, "100.0", "101.5", "99.0", "100.8", "1234.5", 0, 0, 0, 0, 0, 0],
        [1700003600000, "100.8", "102.0", "100.5", "101.9", "987.6", 0, 0, 0, 0, 0, 0],
    ]
    client = BinanceMarketDataClient(session=_mock_session(raw_klines))

    candles = client.get_klines("btcusdt", "1h", limit=2)

    assert len(candles) == 2
    assert candles[0].open == 100.0
    assert candles[1].close == 101.9
    # symbol enviado em maiúsculas
    _, kwargs = client._session.get.call_args
    assert kwargs["params"]["symbol"] == "BTCUSDT"
    assert kwargs["params"]["interval"] == "1h"


def test_get_klines_rejects_invalid_timeframe():
    client = BinanceMarketDataClient(session=_mock_session([]))
    with pytest.raises(ValueError):
        client.get_klines("BTCUSDT", "3m")


def test_get_ticker_price_parses_price():
    client = BinanceMarketDataClient(session=_mock_session({"symbol": "BTCUSDT", "price": "65000.12"}))
    assert client.get_ticker_price("BTCUSDT") == 65000.12


def test_non_200_response_raises_binance_error():
    client = BinanceMarketDataClient(
        session=_mock_session({"msg": "invalid symbol"}, status_code=400),
        rate_limiter=RateLimiter(0.0),
    )
    with pytest.raises(BinanceRequestError):
        client.get_klines("NOTREAL", "1h")


def test_network_exception_is_wrapped():
    import requests

    session = MagicMock()
    session.get.side_effect = requests.ConnectionError("boom")
    client = BinanceMarketDataClient(
        session=session, rate_limiter=RateLimiter(0.0), retry_sleep=lambda seconds: None,
    )

    with pytest.raises(BinanceRequestError):
        client.get_klines("BTCUSDT", "1h")
    assert session.get.call_count == 3  # retry com backoff — 3 tentativas antes de desistir


def test_retryable_status_code_retries_then_succeeds():
    """429/5xx são transientes — deve tentar de novo e conseguir se a próxima tentativa funcionar."""
    session = MagicMock()
    fail_response = MagicMock(status_code=503, text="service unavailable")
    ok_response = MagicMock(status_code=200)
    ok_response.json.return_value = [[1700000000000, "1", "2", "0.5", "1.5", "10", 0, 0, 0, 0, 0, 0]]
    session.get.side_effect = [fail_response, ok_response]

    client = BinanceMarketDataClient(session=session, rate_limiter=RateLimiter(0.0), retry_sleep=lambda seconds: None)
    candles = client.get_klines("BTCUSDT", "1h", limit=1)

    assert len(candles) == 1
    assert session.get.call_count == 2


def test_non_retryable_status_code_fails_immediately():
    """400/404 (erro do cliente) não deve tentar de novo — o resultado nunca mudaria."""
    session = MagicMock()
    response = MagicMock(status_code=400, text="bad request")
    session.get.return_value = response

    client = BinanceMarketDataClient(session=session, rate_limiter=RateLimiter(0.0), retry_sleep=lambda seconds: None)
    with pytest.raises(BinanceRequestError):
        client.get_klines("BTCUSDT", "1h")
    assert session.get.call_count == 1  # nenhuma tentativa extra
