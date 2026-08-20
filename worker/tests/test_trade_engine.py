"""Testes do Trade Engine (secoes 77-106 — Signal/Trade Journal)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from alphaquant_core.engines.trade_engine import (
    ExitReason,
    TargetLeg,
    TradeResult,
    TradeStatus,
    open_trade,
)
from alphaquant_core.playbooks.base import Direction

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _tick(n: int) -> datetime:
    return T0 + timedelta(minutes=15 * n)


class TestSingleTarget:
    def test_target_hit_closes_trade_win(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0, targets=[TargetLeg(price=105.0, exit_pct=100.0)],
            opened_at=T0,
        )
        events = trade.update_price(105.0, _tick(1))
        assert [e.event_type for e in events] == ["TP1_HIT", "CLOSED"]
        assert trade.status == TradeStatus.CLOSED
        assert trade.is_open is False
        assert trade.remaining_pct == 0.0
        assert trade.realized_r == pytest.approx(1.0)  # (105-100)/(100-95)
        assert trade.result == TradeResult.WIN

    def test_stop_hit_closes_trade_loss(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0, targets=[TargetLeg(price=110.0, exit_pct=100.0)],
            opened_at=T0,
        )
        events = trade.update_price(94.0, _tick(1))
        assert events[0].event_type == "STOP"
        assert events[1].event_type == "RESULT"
        assert trade.status == TradeStatus.STOP_HIT
        assert trade.is_open is False
        assert trade.realized_r == pytest.approx(-1.2)  # (94-100)/5
        assert trade.result == TradeResult.LOSS

    def test_no_event_when_price_between_stop_and_target(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0, targets=[TargetLeg(price=110.0, exit_pct=100.0)],
            opened_at=T0,
        )
        events = trade.update_price(102.0, _tick(1))
        assert events == []
        assert trade.is_open is True
        assert trade.status == TradeStatus.OPEN

    def test_short_direction_mirrors_long(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.SHORT, strategy_name="X",
            entry=100.0, stop=105.0, targets=[TargetLeg(price=90.0, exit_pct=100.0)],
            opened_at=T0,
        )
        events = trade.update_price(90.0, _tick(1))
        assert events[0].event_type == "TP1_HIT"
        assert trade.realized_r == pytest.approx(2.0)  # (100-90)/(105-100)
        assert trade.result == TradeResult.WIN


class TestMultiTargetAndBreakeven:
    def test_partial_exits_with_breakeven_then_stop(self):
        trade = open_trade(
            asset="LINKUSDT", direction=Direction.LONG, strategy_name="Liquidity Sweep",
            entry=100.0, stop=95.0,
            targets=[TargetLeg(price=105.0, exit_pct=50.0), TargetLeg(price=110.0, exit_pct=50.0)],
            opened_at=T0, move_to_breakeven_after_tp1=True,
        )

        ev1 = trade.update_price(105.0, _tick(1))
        assert [e.event_type for e in ev1] == ["TP1_HIT", "STOP_MOVED_TO_BREAKEVEN"]
        assert trade.stop == 100.0
        assert trade.remaining_pct == 50.0
        assert trade.status == TradeStatus.TP1_HIT
        assert trade.is_open is True  # partial — resto ainda aberto

        ev2 = trade.update_price(102.0, _tick(2))
        assert ev2 == []  # não toca nem o novo stop (100) nem o TP2 (110)

        ev3 = trade.update_price(99.0, _tick(3))  # cai abaixo do stop já movido para o breakeven
        assert ev3[0].event_type == "STOP"
        assert trade.status == TradeStatus.STOP_HIT
        assert trade.is_open is False
        assert trade.exit_reasons == [ExitReason.TP1, ExitReason.STOP]

        # 50% a +1R (TP1) + 50% a -0.2R (stop em 99, breakeven) = +0.4R líquido
        assert trade.realized_r == pytest.approx(0.5 * 1.0 + 0.5 * (99.0 - 100.0) / 5.0)
        assert trade.result == TradeResult.PARTIAL_WIN

    def test_all_targets_hit_sequentially_closes_full_position(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0,
            targets=[TargetLeg(price=105.0, exit_pct=50.0), TargetLeg(price=110.0, exit_pct=50.0)],
            opened_at=T0,
        )
        trade.update_price(105.0, _tick(1))
        events = trade.update_price(110.0, _tick(2))
        assert [e.event_type for e in events] == ["TP2_HIT", "CLOSED"]
        assert trade.remaining_pct == 0.0
        assert trade.status == TradeStatus.CLOSED
        assert trade.result == TradeResult.PARTIAL_WIN  # duas pernas => partial, mesmo as duas WIN

    def test_targets_are_reordered_by_distance_from_entry(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0,
            targets=[TargetLeg(price=120.0, exit_pct=50.0), TargetLeg(price=105.0, exit_pct=50.0)],
            opened_at=T0,
        )
        assert [t.price for t in trade.targets] == [105.0, 120.0]

    def test_invalid_exit_pct_sum_rejected(self):
        with pytest.raises(ValueError):
            open_trade(
                asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
                entry=100.0, stop=95.0,
                targets=[TargetLeg(price=105.0, exit_pct=60.0), TargetLeg(price=110.0, exit_pct=60.0)],
                opened_at=T0,
            )

    def test_no_targets_rejected(self):
        with pytest.raises(ValueError):
            open_trade(
                asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
                entry=100.0, stop=95.0, targets=[], opened_at=T0,
            )


class TestInvalidationAndExpiry:
    def test_invalidate_closes_remaining_at_current_price_not_stop(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0, targets=[TargetLeg(price=110.0, exit_pct=100.0)],
            opened_at=T0,
        )
        events = trade.invalidate(price=101.0, reason="Perdeu suporte / estrutura invalidada", timestamp=_tick(1))
        assert trade.status == TradeStatus.INVALIDATED
        assert trade.is_open is False
        assert events[0].metadata["reason"] == "Perdeu suporte / estrutura invalidada"
        # fechado a 101, não a 95 (stop) nem a 110 (TP) — o preço real no momento da invalidação
        assert trade.realized_r == pytest.approx((101.0 - 100.0) / 5.0)

    def test_expire_marks_status_without_pnl(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0, targets=[TargetLeg(price=110.0, exit_pct=100.0)],
            opened_at=T0,
        )
        events = trade.expire(price=100.5, timestamp=_tick(1))
        assert trade.status == TradeStatus.EXPIRED
        assert trade.is_open is False
        assert events[0].event_type == "EXPIRED"

    def test_no_op_after_already_closed(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0, targets=[TargetLeg(price=105.0, exit_pct=100.0)],
            opened_at=T0,
        )
        trade.update_price(105.0, _tick(1))
        assert trade.update_price(200.0, _tick(2)) == []
        assert trade.update_price(1.0, _tick(3)) == []
        assert trade.status == TradeStatus.CLOSED


class TestUnrealizedMetrics:
    def test_unrealized_pnl_and_r_while_open(self):
        trade = open_trade(
            asset="BTCUSDT", direction=Direction.LONG, strategy_name="X",
            entry=100.0, stop=95.0, targets=[TargetLeg(price=110.0, exit_pct=100.0)],
            opened_at=T0,
        )
        assert trade.unrealized_pnl_pct(103.0) == pytest.approx(3.0)
        assert trade.unrealized_r(103.0) == pytest.approx(0.6)  # (103-100)/5
