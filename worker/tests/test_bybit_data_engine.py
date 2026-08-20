from unittest.mock import MagicMock

import pytest

from alphaquant_core.engines.bybit_data_engine import (
    BybitMarketDataClient,
    BybitRequestError,
)
from alphaquant_core.engines.data_engine import MarketDataError
from alphaquant_core.services.rate_limiter import RateLimiter


def _mock_session(json_payload, status_code=200):
    session = MagicMock()
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_payload
    response.text = str(json_payload)
    session.get.return_value = response
    return session


def _envelope(result: dict, ret_code: int = 0, ret_msg: str = "OK") -> dict:
    return {"retCode": ret_code, "retMsg": ret_msg, "result": result}


class TestKlines:
    def test_parses_and_reverses_bybit_payload_to_chronological_order(self):
        # Bybit devolve do mais recente pro mais antigo
        raw_list = [
            ["1700003600000", "100.8", "102.0", "100.5", "101.9", "987.6", "0"],
            ["1700000000000", "100.0", "101.5", "99.0", "100.8", "1234.5", "0"],
        ]
        client = BybitMarketDataClient(session=_mock_session(_envelope({"list": raw_list})))

        candles = client.get_klines("btcusdt", "15m", limit=2)

        assert len(candles) == 2
        assert candles[0].timestamp < candles[1].timestamp  # cronológico
        assert candles[0].open == 100.0
        assert candles[1].close == 101.9

        _, kwargs = client._session.get.call_args
        assert kwargs["params"]["symbol"] == "BTCUSDT"
        assert kwargs["params"]["interval"] == "15"
        assert kwargs["params"]["category"] == "linear"

    def test_supports_extended_timeframe_vocabulary(self):
        """Seção 5 — 1m..1d, não só os 4 timeframes originais da Binance."""
        client = BybitMarketDataClient(session=_mock_session(_envelope({"list": []})))
        for tf, code in [("1m", "1"), ("2h", "120"), ("6h", "360"), ("12h", "720"), ("1d", "D")]:
            client.get_klines("BTCUSDT", tf, limit=1)
            _, kwargs = client._session.get.call_args
            assert kwargs["params"]["interval"] == code

    def test_rejects_unsupported_timeframe(self):
        client = BybitMarketDataClient(session=_mock_session(_envelope({"list": []})))
        with pytest.raises(ValueError):
            client.get_klines("BTCUSDT", "7h")


class TestTickerAndDepth:
    def test_get_ticker_price(self):
        client = BybitMarketDataClient(session=_mock_session(
            _envelope({"list": [{"symbol": "BTCUSDT", "lastPrice": "65000.12"}]})
        ))
        assert client.get_ticker_price("BTCUSDT") == 65000.12

    def test_get_ticker_price_raises_when_empty(self):
        client = BybitMarketDataClient(session=_mock_session(_envelope({"list": []})))
        with pytest.raises(BybitRequestError):
            client.get_ticker_price("NOTREAL")

    def test_get_depth_snaps_to_nearest_allowed_limit(self):
        client = BybitMarketDataClient(session=_mock_session(_envelope({"a": [], "b": []})))
        client.get_depth("BTCUSDT", limit=30)
        _, kwargs = client._session.get.call_args
        assert kwargs["params"]["limit"] == 50  # 30 -> próximo permitido acima


class TestErrorHandling:
    def test_non_200_raises_bybit_error_which_is_a_market_data_error(self):
        client = BybitMarketDataClient(
            session=_mock_session({"retMsg": "bad"}, status_code=400),
            rate_limiter=RateLimiter(0.0),
        )
        with pytest.raises(BybitRequestError):
            client.get_klines("NOTREAL", "1h")
        # base comum — quem captura MarketDataError também pega isto (seção 3)
        with pytest.raises(MarketDataError):
            client.get_klines("NOTREAL", "1h")

    def test_business_ret_code_error_raises_without_retry(self):
        """retCode != 0 e não-transiente (ex.: símbolo inválido) — falha imediata."""
        session = MagicMock()
        response = MagicMock(status_code=200)
        response.json.return_value = _envelope({}, ret_code=10001, ret_msg="symbol invalid")
        session.get.return_value = response

        client = BybitMarketDataClient(session=session, rate_limiter=RateLimiter(0.0), retry_sleep=lambda s: None)
        with pytest.raises(BybitRequestError):
            client.get_klines("NOTREAL", "1h")
        assert session.get.call_count == 1

    def test_rate_limit_ret_code_retries_then_succeeds(self):
        session = MagicMock()
        limited = MagicMock(status_code=200)
        limited.json.return_value = _envelope({}, ret_code=10006, ret_msg="rate limit")
        ok = MagicMock(status_code=200)
        ok.json.return_value = _envelope({"list": [["1700000000000", "1", "2", "0.5", "1.5", "10", "0"]]})
        session.get.side_effect = [limited, ok]

        client = BybitMarketDataClient(session=session, rate_limiter=RateLimiter(0.0), retry_sleep=lambda s: None)
        candles = client.get_klines("BTCUSDT", "1h", limit=1)
        assert len(candles) == 1
        assert session.get.call_count == 2

    def test_network_exception_is_wrapped_and_retried(self):
        import requests

        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("boom")
        client = BybitMarketDataClient(session=session, rate_limiter=RateLimiter(0.0), retry_sleep=lambda s: None)

        with pytest.raises(BybitRequestError):
            client.get_klines("BTCUSDT", "1h")
        assert session.get.call_count == 3


class TestSymbolDiscovery:
    def _client_with_universe(self, n_eligible: int, extra_non_eligible: int = 0):
        instruments = [
            {"symbol": f"SYM{i}USDT", "quoteCoin": "USDT", "contractType": "LinearPerpetual", "status": "Trading"}
            for i in range(n_eligible)
        ]
        instruments += [
            {"symbol": f"INV{i}USDC", "quoteCoin": "USDC", "contractType": "LinearPerpetual", "status": "Trading"}
            for i in range(extra_non_eligible)
        ]
        tickers = [
            {"symbol": f"SYM{i}USDT", "turnover24h": str(1000 - i), "lastPrice": "1.0"}
            for i in range(n_eligible)
        ]

        session = MagicMock()

        def side_effect(url, params=None, timeout=None):
            resp = MagicMock(status_code=200)
            if "instruments-info" in url:
                resp.json.return_value = _envelope({"list": instruments})
            else:  # tickers
                resp.json.return_value = _envelope({"list": tickers})
            return resp

        session.get.side_effect = side_effect
        return BybitMarketDataClient(session=session, rate_limiter=RateLimiter(0.0))

    def test_discovers_and_ranks_by_turnover_desc(self):
        client = self._client_with_universe(n_eligible=60)
        symbols = client.discover_usdt_perpetual_symbols(min_symbols=50, max_symbols=55)
        assert len(symbols) == 55
        assert symbols[0] == "SYM0USDT"  # maior turnover24h (1000)
        assert symbols == sorted(symbols, key=lambda s: -(1000 - int(s.replace("SYM", "").replace("USDT", ""))))

    def test_excludes_non_usdt_and_non_trading_contracts(self):
        client = self._client_with_universe(n_eligible=52, extra_non_eligible=10)
        symbols = client.discover_usdt_perpetual_symbols(min_symbols=50, max_symbols=100)
        assert all(s.endswith("USDT") for s in symbols)
        assert all(not s.startswith("INV") for s in symbols)

    def test_raises_instead_of_returning_incomplete_universe(self):
        """Seção 4 — nunca devolve uma lista mais curta que o mínimo sem avisar."""
        client = self._client_with_universe(n_eligible=10)
        with pytest.raises(BybitRequestError):
            client.discover_usdt_perpetual_symbols(min_symbols=50, max_symbols=100)
