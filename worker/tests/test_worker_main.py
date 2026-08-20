from __future__ import annotations

import os

import pytest

from alphaquant_core.core.config import get_settings
from app.main import resolve_scan_universe


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """`get_settings()` é `@lru_cache` — sem isto, um teste que muda
    SCAN_ASSETS vazaria para os outros testes do módulo."""
    original = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(original)
    get_settings.cache_clear()


class _FakeClient:
    def __init__(self, symbols):
        self._symbols = symbols
        self.discover_called = False

    def discover_usdt_perpetual_symbols(self, min_symbols, max_symbols):
        self.discover_called = True
        return self._symbols[:max_symbols]


class _FailingClient:
    def discover_usdt_perpetual_symbols(self, min_symbols, max_symbols):
        from alphaquant_core.engines.bybit_data_engine import BybitRequestError
        raise BybitRequestError("boom")


def test_manual_mode_is_default_and_never_calls_discovery():
    os.environ["SCAN_ASSETS"] = "BTCUSDT,ETHUSDT,SOLUSDT"
    get_settings.cache_clear()

    client = _FakeClient(["AAAUSDT"] * 60)
    symbols = resolve_scan_universe(client)

    assert symbols == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert client.discover_called is False


def test_auto_mode_calls_dynamic_discovery():
    os.environ["SCAN_ASSETS"] = "AUTO"
    os.environ["MIN_SYMBOLS"] = "50"
    os.environ["MAX_SYMBOLS"] = "60"
    get_settings.cache_clear()

    client = _FakeClient([f"SYM{i}USDT" for i in range(80)])
    symbols = resolve_scan_universe(client)

    assert client.discover_called is True
    assert len(symbols) == 60


def test_auto_mode_never_fabricates_symbols_on_failure():
    os.environ["SCAN_ASSETS"] = "AUTO"
    get_settings.cache_clear()

    symbols = resolve_scan_universe(_FailingClient())
    assert symbols == []
