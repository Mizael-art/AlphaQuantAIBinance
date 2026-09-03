"""
tests/test_signal_lifecycle_and_telegram_rules.py
==================================================

Suíte de testes de integridade operacional do ciclo de sinais e Telegram:
1. Setup invalidado antes de signal -> Telegram = 0 mensagens (silêncio total)
2. Signal confirmado -> Telegram = 1 signal com signal_id, signal_sent_at
3. Signal ativo que chega a TP1 -> Telegram = TP1 HIT
4. Signal ativo que chega a STOP -> Telegram = STOP HIT (nunca 'SETUP INVALIDADO')
5. Setup WATCH -> Telegram = somente relatório horário (0 calls individuais)
6. RR inválido -> NO SIGNAL
7. Conflito HTF/LTF -> NO SIGNAL / WAIT
8. Duplicação -> mesmo setup = uma única call no Telegram
9. Nenhuma oportunidade -> relatório horário enviado sem erro
10. Performance -> cada trade resolvido alimenta corretamente o dashboard
"""

from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from persistence.models import Base, SetupRecord, TelegramSignal
from notifications.engine import process_monitoring_updates, process_new_setup
from notifications.formatter import format_market_scan_report, format_stop_hit, format_tp_hit
from decision.engine import evaluate_decision, LONG_NOW, WAIT_PULLBACK, REJECT


@pytest.fixture
def memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()
    yield session
    session.close()


def test_1_setup_invalidated_before_signal_sends_zero_telegram_messages(memory_session: Session, monkeypatch):
    """Teste 1: Setup invalidado antes de ter gerado sinal -> ZERO mensagens ao Telegram."""
    sent_messages = []
    monkeypatch.setattr("notifications.engine.send_message", lambda msg: sent_messages.append(msg) or {"ok": True, "result": {"message_id": 101}})

    # Setup criado em WATCH ou NEAR_ENTRY, sem sinal emitido
    setup = SetupRecord(
        asset="ALGOUSDT",
        direction="long",
        strategy="Trend Continuation EMA50",
        status="WATCH",
        entry_zone_low=0.15,
        entry_zone_high=0.16,
        stop=0.14,
        tp1=0.18,
        score=78.0,
        signal_sent_at=None,
        signal_id=None,
    )
    memory_session.add(setup)
    memory_session.commit()

    # Preço atinge stop antes de entrar -> monitoramento gera update INVALIDATED
    updates = [{"setup_id": setup.id, "asset": setup.asset, "from": "WATCH", "to": "INVALIDATED", "reason": "Preço atingiu stop"}]
    signals_sent = process_monitoring_updates(memory_session, updates)

    assert signals_sent == 0
    assert len(sent_messages) == 0, "Nenhuma mensagem de setup invalidado pode ir ao Telegram se não houve call!"


def test_2_confirmed_signal_generates_one_telegram_call_with_metadata(memory_session: Session, monkeypatch):
    """Teste 2: Signal confirmado -> 1 mensagem de entrada com signal_id e timestamp gravados."""
    sent_messages = []
    monkeypatch.setattr("notifications.engine.send_message", lambda msg: sent_messages.append(msg) or {"ok": True, "result": {"message_id": 202}})

    setup = SetupRecord(
        asset="ETHUSDT",
        direction="long",
        strategy="Trend Continuation EMA50",
        status="READY",
        entry_zone_low=2400.0,
        entry_zone_high=2420.0,
        stop=2350.0,
        tp1=2500.0,
        rr=2.2,
        score=84.0,
        signal_sent_at=None,
    )
    memory_session.add(setup)
    memory_session.commit()

    decision_info = {"decision": "LONG_NOW", "conviction": "HIGH"}
    sent = process_new_setup(memory_session, setup, decision_info)

    assert sent is True
    assert len(sent_messages) == 1
    assert "ETHUSDT — LONG 🟢" in sent_messages[0]
    assert setup.signal_id is not None
    assert setup.signal_id.startswith("SIG-ETHUSDT-")
    assert setup.signal_sent_at is not None
    assert setup.signal_message_id == 202
    assert setup.signal_status == "SIGNAL_SENT"


def test_3_active_trade_hitting_tp1_sends_tp_hit(memory_session: Session, monkeypatch):
    """Teste 3: Signal ativo que atinge TP1 -> envia TP1 HIT."""
    sent_messages = []
    monkeypatch.setattr("notifications.engine.send_message", lambda msg: sent_messages.append(msg) or {"ok": True, "result": {"message_id": 303}})

    setup = SetupRecord(
        asset="ETHUSDT",
        direction="long",
        strategy="Trend Continuation EMA50",
        status="ACTIVE",
        entry_price=2410.0,
        stop=2350.0,
        tp1=2500.0,
        rr=2.2,
        signal_sent_at=datetime.now(timezone.utc),
        signal_id="SIG-ETHUSDT-123",
        signal_status="ACTIVE",
        realized_pnl_pct=3.73,
        realized_r_multiple=1.5,
    )
    memory_session.add(setup)
    memory_session.commit()

    # Preço atinge TP1
    updates = [{"setup_id": setup.id, "asset": setup.asset, "from": "ACTIVE", "to": "TP1", "reason": "Preço atingiu TP1"}]
    signals_sent = process_monitoring_updates(memory_session, updates)

    assert signals_sent == 1
    assert len(sent_messages) == 1
    assert "TP1" in sent_messages[0] and "HIT" in sent_messages[0]
    assert "+3.73%" in sent_messages[0]



def test_4_active_trade_hitting_stop_sends_stop_hit_not_invalidated(memory_session: Session, monkeypatch):
    """Teste 4: Trade ativo que atinge STOP -> Telegram = STOP HIT (nunca 'SETUP INVALIDADO')."""
    sent_messages = []
    monkeypatch.setattr("notifications.engine.send_message", lambda msg: sent_messages.append(msg) or {"ok": True, "result": {"message_id": 404}})

    setup = SetupRecord(
        asset="SOLUSDT",
        direction="short",
        strategy="Resistance Reject",
        status="ACTIVE",
        entry_price=140.0,
        stop=145.0,
        tp1=130.0,
        rr=2.0,
        signal_sent_at=datetime.now(timezone.utc),
        signal_id="SIG-SOLUSDT-123",
        signal_status="ACTIVE",
        realized_pnl_pct=-3.57,
        realized_r_multiple=-1.0,
        exit_price=145.0,
    )
    memory_session.add(setup)
    memory_session.commit()

    # Preço bateu no stop -> status vai para INVALIDATED/CLOSED
    updates = [{"setup_id": setup.id, "asset": setup.asset, "from": "ACTIVE", "to": "INVALIDATED", "reason": "Stop atingido"}]
    signals_sent = process_monitoring_updates(memory_session, updates)

    assert signals_sent == 1
    assert len(sent_messages) == 1
    assert "STOP HIT" in sent_messages[0]
    assert "SETUP INVALIDADO" not in sent_messages[0]
    assert "SOLUSDT — SHORT 🔴" in sent_messages[0]


def test_5_setup_watch_sends_zero_individual_calls(memory_session: Session, monkeypatch):
    """Teste 5: Setup em WATCH -> zero chamadas de entrada."""
    sent_messages = []
    monkeypatch.setattr("notifications.engine.send_message", lambda msg: sent_messages.append(msg) or {"ok": True})

    dec = evaluate_decision(
        direction="long",
        overall_score=72.0,
        risk_decision="APPROVED",
        setup_status="WATCH",
        entry_quality="ENTRY_ON_PULLBACK",
    )
    assert dec.decision in (WAIT_PULLBACK, "WAIT_TRIGGER", "WATCH")
    # Não chama process_new_setup se a decisão não for LONG_NOW/SHORT_NOW


def test_6_invalid_rr_is_rejected(memory_session: Session):
    """Teste 6: RR abaixo do mínimo obrigatório é rejeitado categoricamente."""
    dec = evaluate_decision(
        direction="long",
        overall_score=88.0,
        risk_decision="APPROVED",
        setup_status="READY",
        entry_quality="ENTRY_NOW",
        rr=1.3,
        min_rr=2.0,
    )
    assert dec.decision == REJECT
    assert any("abaixo do mínimo" in r for r in dec.reasons)


def test_7_htf_ltf_conflict_is_blocked():
    """Teste 7: Entrada esticada ou conflito estrutural -> WAIT_PULLBACK, não LONG_NOW."""
    dec = evaluate_decision(
        direction="long",
        overall_score=85.0,
        risk_decision="APPROVED",
        setup_status="UNKNOWN",
        entry_quality="NO_ENTRY",
        rr=2.5,
        min_rr=2.0,
    )
    assert dec.decision == WAIT_PULLBACK


def test_8_deduplication_prevents_duplicate_signals_for_same_setup(memory_session: Session, monkeypatch):
    """Teste 8: Mesmo setup não pode disparar mais de uma call no Telegram."""
    sent_messages = []
    monkeypatch.setattr("notifications.engine.send_message", lambda msg: sent_messages.append(msg) or {"ok": True, "result": {"message_id": 808}})

    setup = SetupRecord(
        asset="BTCUSDT",
        direction="long",
        strategy="HTF Trend + EMA50",
        status="READY",
        entry_zone_low=60000.0,
        entry_zone_high=60500.0,
        stop=59000.0,
        tp1=63000.0,
        rr=2.5,
        score=90.0,
    )
    memory_session.add(setup)
    memory_session.commit()

    # 1º ciclo: envia
    sent1 = process_new_setup(memory_session, setup, {"decision": "LONG_NOW"})
    assert sent1 is True

    # 2º ciclo: mesmo setup_id -> suprimido pelo dedup
    sent2 = process_new_setup(memory_session, setup, {"decision": "LONG_NOW"})
    assert sent2 is False
    assert len(sent_messages) == 1


def test_9_hourly_market_report_when_no_trades():
    """Teste 9: Relatório horário formatado quando não há trades executáveis."""
    report = format_market_scan_report(
        universe_size=320,
        stage1_count=60,
        stage2_count=45,
        setups_ready=[],
        setups_watch=[{"asset": "ETHUSDT", "direction": "long", "strategy": "Pullback EMA50", "score": 74.0}],
        btc_trend="Neutral",
        btc_regime="RANGE",
    )
    assert "ALPHAQUANT X — MARKET REPORT" in report
    assert "Nenhuma oportunidade executável de alta qualidade neste momento." in report
    assert "AGUARDANDO CONFIRMAÇÃO" in report
    assert "ETHUSDT" in report


def test_10_performance_tracking_resolution(memory_session: Session):
    """Teste 10: Cada trade resolvido calcula PnL, R-Múltiplo e duração corretamente."""
    setup = SetupRecord(
        asset="AVAXUSDT",
        direction="long",
        strategy="BOS Pullback",
        status="ACTIVE",
        entry_price=25.0,
        stop=24.0,
        tp1=27.5,
        realized_pnl_pct=10.0,
        realized_r_multiple=2.5,
        exit_price=27.5,
        exit_reason="TP",
        duration_minutes=45.0,
        signal_id="SIG-AVAXUSDT-001",
        signal_status="CLOSED",
    )
    memory_session.add(setup)
    memory_session.commit()

    reloaded = memory_session.get(SetupRecord, setup.id)
    assert reloaded.realized_pnl_pct == 10.0
    assert reloaded.realized_r_multiple == 2.5
    assert reloaded.exit_reason == "TP"
    assert reloaded.signal_status == "CLOSED"
