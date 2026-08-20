from __future__ import annotations

from datetime import datetime, timedelta, timezone

from alphaquant_core.db.models import DecisionResult as DBDecisionResult
from alphaquant_core.db.models import Direction as DBDirection
from alphaquant_core.db.models import Opportunity, OpportunityStatus, Trade
from alphaquant_core.services import trade_service

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _confirmed_opportunity(db, **overrides) -> Opportunity:
    defaults = dict(
        asset="BTCUSDT", timeframe="1h", playbook="Liquidity Sweep Reversal",
        direction=DBDirection.LONG, status=OpportunityStatus.CONFIRMED,
        score=87.0, confidence="ALTA", progress=100.0,
        entry=100.0, stop=95.0, tp1=105.0, tp2=110.0, tp3=None,
        rr=1.0, decision=DBDecisionResult.ENTRAR,
        playbook_version="v1.0", algorithm_version="v1.0",
        audit_snapshot={"regime": "BULLISH", "rsi14": 42.0},
    )
    defaults.update(overrides)
    opp = Opportunity(**defaults)
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


def test_create_trade_from_signal_persists_snapshot_and_targets(db_session):
    opp = _confirmed_opportunity(db_session)
    trade = trade_service.create_trade_from_signal(db_session, opp)

    assert trade is not None
    assert trade.opportunity_id == opp.id
    assert trade.status.value == "OPEN"
    assert trade.entry == 100.0 and trade.stop == 95.0
    assert len(trade.targets) == 2
    assert sum(t["exit_pct"] for t in trade.targets) == 100.0
    assert trade.context_snapshot == {"regime": "BULLISH", "rsi14": 42.0}  # seção 85

    events = trade.events
    assert len(events) == 1 and events[0].event_type == "TRADE_CREATED"


def test_returns_none_without_confirmed_targets(db_session):
    opp = _confirmed_opportunity(db_session, tp1=None, tp2=None, tp3=None)
    assert trade_service.create_trade_from_signal(db_session, opp) is None

    opp2 = _confirmed_opportunity(db_session, decision=DBDecisionResult.ESPERAR, status=OpportunityStatus.FORMATION)
    assert trade_service.create_trade_from_signal(db_session, opp2) is None


def test_price_update_persists_events_and_updates_trade_row(db_session):
    opp = _confirmed_opportunity(db_session)
    trade = trade_service.create_trade_from_signal(db_session, opp, move_to_breakeven_after_tp1=True)

    events = trade_service.apply_price_update(db_session, trade, 105.0, T0 + timedelta(minutes=15))
    assert [e.event_type for e in events] == ["TP1_HIT", "STOP_MOVED_TO_BREAKEVEN"]

    db_session.refresh(trade)
    assert trade.status.value == "TP1_HIT"
    assert trade.stop == 100.0  # moveu pro breakeven
    assert trade.remaining_pct == 50.0
    assert trade.realized_r > 0


def test_survives_reload_from_db_mid_lifecycle(db_session):
    """Simula reinício do processo (seção 102): recarrega a Trade do zero
    (nova instância ORM) e continua o acompanhamento a partir do estado
    persistido, sem repetir eventos já gravados."""
    opp = _confirmed_opportunity(db_session)
    trade = trade_service.create_trade_from_signal(db_session, opp, move_to_breakeven_after_tp1=True)
    trade_id = trade.id

    trade_service.apply_price_update(db_session, trade, 105.0, T0 + timedelta(minutes=15))

    reloaded = db_session.query(Trade).filter_by(id=trade_id).one()
    assert reloaded.stop == 100.0  # estado movido no ciclo anterior preservado

    events = trade_service.apply_price_update(db_session, reloaded, 99.0, T0 + timedelta(minutes=30))
    assert events[0].event_type == "STOP"
    assert reloaded.status.value == "STOP_HIT"
    assert reloaded.result.value == "PARTIAL_WIN"

    all_events = db_session.query(Trade).filter_by(id=trade_id).one().events
    assert [e.event_type for e in all_events] == [
        "TRADE_CREATED", "TP1_HIT", "STOP_MOVED_TO_BREAKEVEN", "STOP", "RESULT",
    ]


def test_closed_trade_ignores_further_price_updates(db_session):
    opp = _confirmed_opportunity(db_session, tp2=None)
    trade = trade_service.create_trade_from_signal(db_session, opp)
    trade_service.apply_price_update(db_session, trade, 105.0, T0)
    assert trade.status.value == "CLOSED"

    events = trade_service.apply_price_update(db_session, trade, 999.0, T0 + timedelta(minutes=15))
    assert events == []


def test_invalidate_and_expire(db_session):
    opp1 = _confirmed_opportunity(db_session)
    t1 = trade_service.create_trade_from_signal(db_session, opp1)
    events = trade_service.invalidate_trade(db_session, t1, price=101.0, reason="Perdeu estrutura")
    assert t1.status.value == "INVALIDATED"
    assert events[0].event_metadata["reason"] == "Perdeu estrutura"

    opp2 = _confirmed_opportunity(db_session, asset="ETHUSDT")
    t2 = trade_service.create_trade_from_signal(db_session, opp2)
    trade_service.expire_trade(db_session, t2, price=100.2)
    assert t2.status.value == "EXPIRED"


def test_performance_summary_excludes_open_trades(db_session):
    opp_open = _confirmed_opportunity(db_session, asset="SOLUSDT")
    trade_service.create_trade_from_signal(db_session, opp_open)

    opp_win = _confirmed_opportunity(db_session, asset="LINKUSDT", tp2=None)
    win = trade_service.create_trade_from_signal(db_session, opp_win)
    trade_service.apply_price_update(db_session, win, 105.0, T0)

    opp_loss = _confirmed_opportunity(db_session, asset="ADAUSDT", tp2=None)
    loss = trade_service.create_trade_from_signal(db_session, opp_loss)
    trade_service.apply_price_update(db_session, loss, 94.0, T0)

    summary = trade_service.performance_summary(db_session)
    assert summary["open_trades"] >= 1
    assert summary["closed_trades"] >= 2
    assert 0.0 <= summary["win_rate"] <= 100.0
    assert summary["profit_factor"] is None or summary["profit_factor"] >= 0
