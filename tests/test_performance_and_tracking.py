"""
tests/test_performance_and_tracking.py
=======================================

Testes automatizados para o Strategy Engine V2:
- Ciclo de vida do trade (open, active, TP/SL, closed)
- Cálculo determinístico de PnL % e R-múltiplo
- Endpoints de performance (open trades, trade history, global, monthly, strategy, asset, regime)
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from server import app
from persistence.db import session_scope
from persistence.models import SetupRecord
from monitoring.service import run_monitoring_cycle
from notifications.formatter import format_new_call, format_tp_hit, format_stop_hit


def test_simplified_signal_formatting():
    setup = SetupRecord(
        asset="ETHUSDT",
        direction="long",
        strategy="Trend Continuation EMA50",
        status="READY",
        entry_zone_low=2414.17,
        entry_zone_high=2414.17,
        stop=2358.00,
        tp1=2456.00,
        tp2=2490.00,
        rr=2.5,
        score=90.0,
    )
    decision = {
        "reasons": ["Pullback técnico na EMA50 em tendência 4H", "BOS confirmado no 15M com volume"]
    }
    msg = format_new_call(setup, decision)

    assert "ETHUSDT" in msg
    assert "LONG 🟢" in msg
    assert "2414.17" in msg
    assert "10x" in msg
    assert "5% da banca" in msg
    assert "TP1: 2456.00" in msg
    assert "SL: 2358.00" in msg
    assert "Com 5% da banca em margem e 10x" in msg


def test_monitoring_trade_outcome_calculation():
    with session_scope(url="sqlite:///:memory:") as session:
        # 1. Setup LONG que atinge TP1
        setup = SetupRecord(
            asset="BTCUSDT",
            direction="long",
            strategy="Liquidity Sweep Reversal",
            status="NEAR_ENTRY",
            entry_zone_low=60000.0,
            entry_zone_high=60000.0,
            stop=59000.0,
            tp1=62000.0,
            rr=2.0,
            score=92.0,
        )
        session.add(setup)
        session.flush()

        class FakeMarketData:
            def get_current_price(self, symbol: str):
                return 62000.0

        res = run_monitoring_cycle(session, market_data=FakeMarketData())
        assert len(res.updated) > 0
        assert setup.status == "COMPLETED"
        assert setup.realized_pnl_pct is not None
        assert setup.realized_pnl_pct > 0.0
        assert setup.realized_r_multiple is not None
        assert setup.realized_r_multiple >= 2.0


def test_dashboard_analytics_endpoints():
    client = TestClient(app)

    # 1. Open trades
    resp = client.get("/dashboard/open-trades")
    assert resp.status_code == 200
    assert "total_open_trades" in resp.json()

    # 2. Trade history
    resp = client.get("/dashboard/trade-history")
    assert resp.status_code == 200
    assert "total_trades" in resp.json()

    # 3. Global performance
    resp = client.get("/dashboard/performance")
    assert resp.status_code == 200
    data = resp.json()
    assert "win_rate_pct" in data or "win_rate" in data
    assert "profit_factor" in data

    # 4. Monthly performance
    resp = client.get("/dashboard/monthly")
    assert resp.status_code == 200
    assert "monthly_performance" in resp.json()

    # 5. Strategy performance
    resp = client.get("/dashboard/strategy-performance")
    assert resp.status_code == 200
    assert "strategies" in resp.json()

    # 6. Asset performance
    resp = client.get("/dashboard/asset-performance")
    assert resp.status_code == 200
    assert "assets" in resp.json()

    # 7. Regime performance
    resp = client.get("/dashboard/regime-performance")
    assert resp.status_code == 200
    assert "regimes" in resp.json()
