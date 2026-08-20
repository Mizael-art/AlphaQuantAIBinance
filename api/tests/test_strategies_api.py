import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))

VALID_PROMPT = """
NAME: Test Trend Long
CONDITIONS:
  REGIME == BULLISH
  RSI14 < 100
STOP: SWING_LOW
TARGETS: RR 2.0
"""

UNSUPPORTED_PROMPT = """
NAME: Uses ADX
CONDITIONS:
  ADX > 25
STOP: SWING_LOW
TARGETS: RR 2
"""


def _login(client, username="AlphaQuant", password="VIP"):
    return client.post("/auth/login", json={"username": username, "password": password})


def _auth_headers(client):
    r = _login(client)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class TestAuth:
    def test_login_with_default_credentials_succeeds(self, client):
        r = _login(client)
        assert r.status_code == 200
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0
        assert len(body["access_token"]) > 20

    def test_login_with_wrong_password_fails(self, client):
        r = _login(client, password="wrong")
        assert r.status_code == 401

    def test_strategies_endpoint_requires_auth(self, client):
        r = client.get("/strategies")
        assert r.status_code == 401

    def test_strategies_endpoint_rejects_garbage_token(self, client):
        r = client.get("/strategies", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_strategies_endpoint_works_with_valid_token(self, client):
        headers = _auth_headers(client)
        r = client.get("/strategies", headers=headers)
        assert r.status_code == 200
        assert "strategies" in r.json()


class TestStrategyCrud:
    def test_create_list_get(self, client):
        headers = _auth_headers(client)
        r = client.post("/strategies", json={"name": "X", "prompt": VALID_PROMPT}, headers=headers)
        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "ACTIVE"
        assert body["current_version"]["status"] == "VALID"
        assert body["is_runnable"] is True
        strategy_id = body["id"]

        r = client.get(f"/strategies/{strategy_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["name"] == "X"

        r = client.get("/strategies", headers=headers)
        assert any(s["id"] == strategy_id for s in r.json()["strategies"])

    def test_get_missing_strategy_404(self, client):
        headers = _auth_headers(client)
        r = client.get("/strategies/999999999", headers=headers)
        assert r.status_code == 404

    def test_unsupported_condition_never_marked_runnable(self, client):
        headers = _auth_headers(client)
        r = client.post("/strategies", json={"name": "Bad", "prompt": UNSUPPORTED_PROMPT}, headers=headers)
        assert r.status_code == 201
        body = r.json()
        assert body["current_version"]["status"] == "UNSUPPORTED_CONDITION"
        assert body["is_runnable"] is False
        assert any("ADX" in u for u in body["current_version"]["unsupported_conditions"])

    def test_update_creates_new_version_without_overwriting(self, client):
        headers = _auth_headers(client)
        created = client.post("/strategies", json={"name": "X", "prompt": VALID_PROMPT}, headers=headers).json()
        strategy_id = created["id"]

        new_prompt = VALID_PROMPT.replace("RSI14 < 100", "RSI14 < 80")
        r = client.patch(
            f"/strategies/{strategy_id}",
            json={"prompt": new_prompt, "change_note": "mais restritiva"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["current_version"]["version_label"] == "v2"

        versions = client.get(f"/strategies/{strategy_id}/versions", headers=headers).json()["versions"]
        assert len(versions) == 2
        assert versions[0]["version_label"] == "v1"
        assert versions[0]["prompt_raw"] == VALID_PROMPT
        assert versions[1]["version_label"] == "v2"
        assert versions[1]["change_note"] == "mais restritiva"
        assert versions[1]["is_current"] is True
        assert versions[0]["is_current"] is False

    def test_activate_deactivate_archive_lifecycle(self, client):
        headers = _auth_headers(client)
        strategy_id = client.post("/strategies", json={"name": "X", "prompt": VALID_PROMPT}, headers=headers).json()["id"]

        r = client.post(f"/strategies/{strategy_id}/deactivate", headers=headers)
        assert r.json()["status"] == "INACTIVE"

        r = client.post(f"/strategies/{strategy_id}/activate", headers=headers)
        assert r.json()["status"] == "ACTIVE"

        r = client.delete(f"/strategies/{strategy_id}", headers=headers)
        assert r.json()["status"] == "ARCHIVED"

        # histórico preservado após archive
        versions = client.get(f"/strategies/{strategy_id}/versions", headers=headers).json()["versions"]
        assert len(versions) == 1

    def test_duplicate_creates_independent_inactive_copy(self, client):
        headers = _auth_headers(client)
        original = client.post("/strategies", json={"name": "X", "prompt": VALID_PROMPT}, headers=headers).json()

        r = client.post(f"/strategies/{original['id']}/duplicate", headers=headers)
        assert r.status_code == 201
        dup = r.json()
        assert dup["id"] != original["id"]
        assert dup["status"] == "INACTIVE"
        assert dup["current_version"]["prompt_raw"] == VALID_PROMPT


class TestStrategyTest:
    def test_test_endpoint_runs_against_live_context(self, client, monkeypatch):
        """Injeta um client Bybit falso no orchestrator para não depender de rede real."""
        headers = _auth_headers(client)
        strategy_id = client.post("/strategies", json={"name": "X", "prompt": VALID_PROMPT}, headers=headers).json()["id"]

        from playbook_fixtures import uptrend_pullback_to_ema50

        df = uptrend_pullback_to_ema50()

        def fake_fetch_and_persist(db, symbol, timeframe, client=None, limit=200):
            from alphaquant_core.engines.orchestrator import _candles_to_dataframe
            from alphaquant_core.engines.data_engine import Candle

            rows = df.reset_index()
            candles = [
                Candle(timestamp=row["index"].to_pydatetime(), open=row["open"], high=row["high"],
                       low=row["low"], close=row["close"], volume=row["volume"])
                for _, row in rows.iterrows()
            ]
            return df, candles, len(candles)

        monkeypatch.setattr("app.routers.strategies.fetch_and_persist", fake_fetch_and_persist)

        r = client.post(f"/strategies/{strategy_id}/test", json={"asset": "BTCUSDT", "timeframe": "1h"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["runnable"] is True
        assert body["matched"] is True
        assert body["direction"] == "LONG"
        assert body["stop"] is not None

    def test_test_endpoint_reports_unsupported_without_calling_market_data(self, client, monkeypatch):
        headers = _auth_headers(client)
        strategy_id = client.post("/strategies", json={"name": "Bad", "prompt": UNSUPPORTED_PROMPT}, headers=headers).json()["id"]

        def _boom(*a, **k):
            raise AssertionError("não deveria buscar dados de mercado para estratégia UNSUPPORTED_CONDITION")

        monkeypatch.setattr("app.routers.strategies.fetch_and_persist", _boom)

        r = client.post(f"/strategies/{strategy_id}/test", json={"asset": "BTCUSDT"}, headers=headers)
        assert r.status_code == 200
        body = r.json()
        assert body["runnable"] is False
        assert body["status"] == "UNSUPPORTED_CONDITION"
