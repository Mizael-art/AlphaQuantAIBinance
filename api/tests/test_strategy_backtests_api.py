import random
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))

VALID_PROMPT = """
NAME: Permissive Long
CONDITIONS:
  REGIME == BULLISH
STOP: SWING_LOW
TARGETS: RR 1.5
"""


def _login_headers(client):
    r = client.post("/auth/login", json={"username": "AlphaQuant", "password": "VIP"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _long_uptrend_candles(cycles: int = 40):
    from alphaquant_core.engines.data_engine import Candle

    rng = random.Random(11)
    rows = []
    price = 100.0
    for c in range(cycles):
        step_up = 10.0 / 6
        for _ in range(6):
            o = price
            price += step_up
            jitter = rng.uniform(0.05, 0.25)
            rows.append((max(o, price) + jitter, min(o, price) - jitter * 0.3, o, price, rng.uniform(150, 250)))
        if c < cycles - 1:
            step_down = 5.0 / 4
            for _ in range(4):
                o = price
                price -= step_down
                jitter = rng.uniform(0.05, 0.25)
                rows.append((max(o, price) + jitter * 0.3, min(o, price) - jitter, o, price, rng.uniform(150, 250)))

    index = pd.date_range("2025-01-01", periods=len(rows), freq="1h")
    return [
        Candle(timestamp=ts.to_pydatetime(), open=o, high=h, low=l, close=c, volume=v)
        for ts, (h, l, o, c, v) in zip(index, rows)
    ]


def _seed_candles(db_session, symbol: str, timeframe: str, cycles: int = 40):
    from alphaquant_core.services.candle_service import get_or_create_asset, upsert_candles

    asset = get_or_create_asset(db_session, symbol)
    candles = _long_uptrend_candles(cycles=cycles)
    upsert_candles(db_session, asset.id, timeframe, candles)
    return candles


def _create_strategy(client, headers, prompt=VALID_PROMPT):
    r = client.post("/strategies", json={"name": "X", "prompt": prompt}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestBacktestEndpoint:
    def test_runs_and_persists(self, client, db_session):
        headers = _login_headers(client)
        _seed_candles(db_session, "BTCUSDT", "1h", cycles=40)
        strategy_id = _create_strategy(client, headers)

        r = client.post(f"/strategies/{strategy_id}/backtest", json={"asset": "BTCUSDT", "timeframe": "1h", "lookback": 60}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["period"]["candles"] > 0
        assert "trades" in body["stats"]

        persisted = client.get("/backtests", params={"asset": "BTCUSDT"}, headers=headers)
        assert persisted.status_code == 200
        assert persisted.json()["count"] >= 1

    def test_rejects_insufficient_candles(self, client, db_session):
        headers = _login_headers(client)
        _seed_candles(db_session, "SOLUSDT", "1h", cycles=2)  # poucos candles
        strategy_id = _create_strategy(client, headers)

        r = client.post(f"/strategies/{strategy_id}/backtest", json={"asset": "SOLUSDT", "timeframe": "1h", "lookback": 60}, headers=headers)
        assert r.status_code == 422

    def test_rejects_non_runnable_strategy(self, client, db_session):
        headers = _login_headers(client)
        _seed_candles(db_session, "ETHUSDT", "1h", cycles=40)
        bad_prompt = "NAME: x\nCONDITIONS:\n  ADX > 25\nSTOP: SWING_LOW\nTARGETS: RR 2\n"
        strategy_id = _create_strategy(client, headers, prompt=bad_prompt)

        r = client.post(f"/strategies/{strategy_id}/backtest", json={"asset": "ETHUSDT", "timeframe": "1h"}, headers=headers)
        assert r.status_code == 422

    def test_requires_auth(self, client):
        r = client.post("/strategies/1/backtest", json={"asset": "BTCUSDT"})
        assert r.status_code == 401


class TestMonteCarloEndpoint:
    def test_runs_after_backtest(self, client, db_session):
        headers = _login_headers(client)
        _seed_candles(db_session, "LINKUSDT", "1h", cycles=40)
        strategy_id = _create_strategy(client, headers)

        r = client.post(
            f"/strategies/{strategy_id}/backtest/monte-carlo",
            json={"asset": "LINKUSDT", "timeframe": "1h", "lookback": 60, "simulations": 200, "seed": 1},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["simulations"] == 200
        assert body["final_equity_r"]["p5"] <= body["final_equity_r"]["p50"] <= body["final_equity_r"]["p95"]
        assert 0.0 <= body["probability_of_loss"] <= 1.0


class TestWalkForwardEndpoint:
    def test_returns_dev_and_oos_per_fold(self, client, db_session):
        headers = _login_headers(client)
        _seed_candles(db_session, "ADAUSDT", "1h", cycles=40)
        strategy_id = _create_strategy(client, headers)

        r = client.post(
            f"/strategies/{strategy_id}/backtest/walk-forward",
            json={"asset": "ADAUSDT", "timeframe": "1h", "lookback": 60, "n_folds": 2, "oos_fraction": 0.3},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        folds = r.json()["folds"]
        assert len(folds) == 2
        for f in folds:
            assert "dev_stats" in f and "oos_stats" in f
            assert f["dev_period"]["end"] < f["oos_period"]["start"]


class TestSensitivityEndpoint:
    def test_classifies_robustness(self, client, db_session):
        headers = _login_headers(client)
        _seed_candles(db_session, "DOTUSDT", "1h", cycles=40)
        prompt = "NAME: x\nCONDITIONS:\n  REGIME == BULLISH\n  RSI14 < 100\nSTOP: SWING_LOW\nTARGETS: RR 2\n"
        strategy_id = _create_strategy(client, headers, prompt=prompt)

        r = client.post(
            f"/strategies/{strategy_id}/backtest/sensitivity",
            json={"asset": "DOTUSDT", "timeframe": "1h", "lookback": 60, "param_grid": {"RSI14": [50, 100]}},
            headers=headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["robustness"] in ("ROBUST", "FRAGILE", "CONSISTENTLY_NEGATIVE", "INSUFFICIENT_DATA")
        assert len(body["variants"]) == 2

    def test_rejects_empty_param_grid(self, client, db_session):
        headers = _login_headers(client)
        _seed_candles(db_session, "AVAXUSDT", "1h", cycles=40)
        strategy_id = _create_strategy(client, headers)

        r = client.post(
            f"/strategies/{strategy_id}/backtest/sensitivity",
            json={"asset": "AVAXUSDT", "timeframe": "1h", "param_grid": {}},
            headers=headers,
        )
        assert r.status_code == 422
