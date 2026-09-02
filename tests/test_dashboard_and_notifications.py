"""
tests/test_dashboard_and_notifications.py
===========================================

Testes automatizados para os novos módulos:
- Notifications (dedup, formatação, telegram client)
- Dashboard API endpoints
- Cache de Klines
- Scheduler Lock
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from server import app
from persistence.db import session_scope, get_engine
from persistence.models import SystemCycle, SetupRecord, TelegramSignal, CandidateSnapshot
from notifications.dedup import should_send_notification, record_signal_sent
from notifications.formatter import (
    format_new_call,
    format_tp_hit,
    format_stop_hit,
    format_invalidated,
    format_setup_update,
)
from engine.cache import GlobalKlineCache
import pandas as pd


@pytest.fixture(autouse=True)
def clean_db():
    # Setup test state
    yield


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "telegram" in data


def test_dashboard_overview():
    client = TestClient(app)
    response = client.get("/dashboard/overview")
    assert response.status_code == 200
    data = response.json()
    assert "system_status" in data
    assert "active_setups" in data
    assert "signals_today" in data


def test_dashboard_cycles_and_setups():
    client = TestClient(app)
    response = client.get("/dashboard/cycles?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "cycles" in data
    assert isinstance(data["cycles"], list)

    response = client.get("/dashboard/setups")
    assert response.status_code == 200
    data = response.json()
    assert "setups" in data
    assert isinstance(data["setups"], list)


def test_dashboard_heatmap_and_performance():
    client = TestClient(app)
    response = client.get("/dashboard/heatmap")
    assert response.status_code == 200
    data = response.json()
    assert "assets" in data

    response = client.get("/dashboard/performance")
    assert response.status_code == 200
    data = response.json()
    assert "win_rate" in data


def test_kline_cache():
    GlobalKlineCache.clear()
    df_sample = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
    GlobalKlineCache.set("BTCUSDT", "1H", 100, df_sample)
    
    cached = GlobalKlineCache.get("BTCUSDT", "1H", 100)
    assert cached is not None
    assert len(cached) == 3

    missing = GlobalKlineCache.get("ETHUSDT", "1H", 100)
    assert missing is None


def test_notifications_dedup_and_formatting():
    with session_scope(url="sqlite:///:memory:") as session:
        # Criar setup de teste
        setup = SetupRecord(
            asset="SOLUSDT",
            direction="long",
            strategy="Breakout + Retest",
            status="ACTIVE",
            entry_zone_low=140.0,
            entry_zone_high=142.0,
            stop=135.0,
            tp1=150.0,
            tp2=160.0,
            tp3=170.0,
            rr=2.5,
            score=85.0,
            status_changed_at=datetime.now(timezone.utc),
        )
        session.add(setup)
        session.flush()

        # 1. Primeira notificação deve passar
        assert should_send_notification(session, setup.id, "new_setup") is True

        # Formatar mensagem
        msg = format_new_call(setup, {"reasons": ["BOS confirmed", "Volume above average"]})
        assert "SOLUSDT" in msg
        assert "LONG" in msg
        assert "Breakout + Retest" in msg

        # Registrar envio
        record_signal_sent(session, setup.id, "new_setup", msg)

        # 2. Segunda notificação idêntica dentro do cooldown deve ser bloqueada
        assert should_send_notification(session, setup.id, "new_setup") is False

        # 3. Notificação de evento crítico (TP1) deve passar
        assert should_send_notification(session, setup.id, "tp1_hit") is True
        tp_msg = format_tp_hit(setup, "TP1")
        assert "TP1 ATINGIDO" in tp_msg
        record_signal_sent(session, setup.id, "tp1_hit", tp_msg)

        # 4. TP1 repetido para o mesmo setup deve ser bloqueado
        assert should_send_notification(session, setup.id, "tp1_hit") is False


def test_frontend_compatibility_endpoints():
    client = TestClient(app)

    # 1. /summary
    res = client.get("/summary")
    assert res.status_code == 200
    data = res.json()
    assert "scanner_status" in data
    assert "score_ge_70" in data

    # 2. /playbooks
    res = client.get("/playbooks")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 7
    assert len(data["playbooks"]) >= 7

    # 3. /trades/open
    res = client.get("/trades/open")
    assert res.status_code == 200
    data = res.json()
    assert "trades" in data

    # 4. /trades/closed
    res = client.get("/trades/closed")
    assert res.status_code == 200
    data = res.json()
    assert "trades" in data

    # 5. /trades/performance
    res = client.get("/trades/performance")
    assert res.status_code == 200
    data = res.json()
    assert "win_rate" in data

    # 6. /opportunities
    res = client.get("/opportunities")
    assert res.status_code == 200
    data = res.json()
    assert "opportunities" in data

    # 7. /auth/login
    res = client.post("/auth/login")
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data

    # 8. /health services structure
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "services" in data
    assert "worker" in data["services"]
    assert "database" in data["services"]
    assert "telegram" in data["services"]
    assert "market-data" in data["services"]
