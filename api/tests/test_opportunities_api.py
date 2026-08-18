import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker" / "tests"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker"))


def _fake_client(df):
    from alphaquant_core.engines.data_engine import Candle

    class FakeClient:
        def get_klines(self, symbol, timeframe, limit=200):
            rows = df.reset_index()
            return [
                Candle(
                    timestamp=row["index"].to_pydatetime(), open=row["open"], high=row["high"],
                    low=row["low"], close=row["close"], volume=row["volume"],
                )
                for _, row in rows.tail(limit).iterrows()
            ]

    return FakeClient()


def _seed_opportunities(db_session, symbol: str):
    from playbook_fixtures import uptrend_pullback_to_ema50

    from alphaquant_core.playbooks.runner import scan_and_score

    df = uptrend_pullback_to_ema50()
    return scan_and_score(db_session, symbol, "1h", client=_fake_client(df), htf_regime="BULLISH")


def test_list_opportunities_empty_by_default(client):
    r = client.get("/opportunities", params={"asset": "NOPE_NOT_SEEDED"})
    assert r.status_code == 200
    assert r.json() == {"count": 0, "opportunities": []}


def test_list_and_get_opportunity_with_real_data(db_session, client):
    _ctx, _results, opportunities = _seed_opportunities(db_session, "APIUSDT")
    assert opportunities

    r = client.get("/opportunities", params={"asset": "APIUSDT"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(opportunities)
    assert all(o["asset"] == "APIUSDT" for o in body["opportunities"])

    first_id = body["opportunities"][0]["id"]
    r2 = client.get(f"/opportunities/{first_id}")
    assert r2.status_code == 200
    detail = r2.json()
    assert detail["id"] == first_id
    assert "evidence" in detail and len(detail["evidence"]) > 0
    assert "audit_snapshot" in detail


def test_get_opportunity_404_for_missing_id(client):
    r = client.get("/opportunities/999999999")
    assert r.status_code == 404


def test_list_opportunities_filters_by_status(db_session, client):
    _ctx, _results, opportunities = _seed_opportunities(db_session, "FILTERUSDT")
    statuses = {o.status.value for o in opportunities}
    assert statuses  # a fixture produz pelo menos um status

    target_status = next(iter(statuses))
    r = client.get("/opportunities", params={"asset": "FILTERUSDT", "status": target_status})
    assert r.status_code == 200
    body = r.json()
    assert all(o["status"] == target_status for o in body["opportunities"])


def test_list_playbooks_returns_all_ten(client):
    r = client.get("/playbooks")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    names = {p["name"] for p in body["playbooks"]}
    assert "Open Range Breakout" in names
    experimental = [p for p in body["playbooks"] if p["name"] == "Open Range Breakout"][0]
    assert experimental["status"] == "EXPERIMENTAL"


def test_summary_reflects_real_opportunities(db_session, client):
    _seed_opportunities(db_session, "SUMMARYUSDT")

    r = client.get("/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["window"] == "24h"
    assert body["opportunities_analyzed"] >= 1
    assert body["scanner_status"] in {"UNKNOWN", "ONLINE", "DEGRADED", "OFFLINE"}


def test_list_backtests_empty_by_default(client):
    r = client.get("/backtests", params={"asset": "NOPE_NOT_SEEDED"})
    assert r.status_code == 200
    assert r.json() == {"count": 0, "backtests": []}


def test_list_backtests_with_real_data(db_session, client):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker" / "tests"))

    from backtest_fixtures import long_zigzag_uptrend

    from alphaquant_core.playbooks.backtest_runner import run_and_save_backtest
    from alphaquant_core.playbooks.trend_continuation import TrendContinuationEMA50
    from alphaquant_core.services.candle_service import get_or_create_asset, upsert_candles
    from alphaquant_core.engines.data_engine import Candle

    df = long_zigzag_uptrend()
    candles = [
        Candle(timestamp=ts.to_pydatetime(), open=float(r.open), high=float(r.high), low=float(r.low), close=float(r.close), volume=float(r.volume))
        for ts, r in df.iterrows()
    ]
    asset = get_or_create_asset(db_session, "BACKTESTAPIUSDT")
    upsert_candles(db_session, asset.id, "1h", candles)
    run_and_save_backtest(db_session, TrendContinuationEMA50(), "BACKTESTAPIUSDT", "1h", lookback=80)

    r = client.get("/backtests", params={"asset": "BACKTESTAPIUSDT"})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["backtests"][0]["playbook"] == "Trend Continuation EMA50"
