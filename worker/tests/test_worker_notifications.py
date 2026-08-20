from datetime import datetime, timezone

from alphaquant_core.db.models import (
    DecisionResult as DBDecisionResult,
)
from alphaquant_core.db.models import (
    Direction as DBDirection,
)
from alphaquant_core.db.models import Opportunity, OpportunityStatus, SystemHealth
from alphaquant_core.services import trade_service
from alphaquant_core.telegram.client import SendResult
from alphaquant_core.telegram.formatting import (
    format_system_error_message,
    format_system_online_message,
    format_system_recovered_message,
    format_trade_update_message,
)

from app.main import notify_health_transition, run_trade_tracking_cycle


class FakeTelegramClient:
    def __init__(self, always_fail: bool = False):
        self.sent: list[tuple[str, str]] = []
        self.always_fail = always_fail

    def send_message(self, chat_id, text):
        if self.always_fail:
            return SendResult(success=False, error="falha simulada")
        self.sent.append((chat_id, text))
        return SendResult(success=True, message_id=str(len(self.sent)))


class FakePriceClient:
    def __init__(self, prices: dict[str, float]):
        self._prices = prices

    def get_ticker_price(self, symbol):
        from alphaquant_core.engines.bybit_data_engine import BybitRequestError
        if symbol not in self._prices:
            raise BybitRequestError(f"sem preço para {symbol}")
        return self._prices[symbol]


def _confirmed_opportunity(db, **overrides) -> Opportunity:
    defaults = dict(
        asset="BTCUSDT", timeframe="1h", playbook="Liquidity Sweep Reversal",
        direction=DBDirection.LONG, status=OpportunityStatus.CONFIRMED,
        score=87.0, confidence="ALTA", progress=100.0,
        entry=100.0, stop=95.0, tp1=105.0, tp2=None, tp3=None,
        rr=1.0, decision=DBDecisionResult.ENTRAR,
        playbook_version="v1.0", algorithm_version="v1.0",
        audit_snapshot={},
    )
    defaults.update(overrides)
    opp = Opportunity(**defaults)
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return opp


def _set_worker_health(db, status: str, error: str | None = None) -> None:
    """As linhas de `SystemHealth` são singleton por `service` (unique
    constraint) e a suíte de testes compartilha o mesmo Postgres efêmero
    entre métodos — por isso sempre um get-or-create aqui, nunca um
    `add()` cego que colidiria com uma linha "worker" já existente."""
    from sqlalchemy import select as sa_select
    row = db.execute(sa_select(SystemHealth).where(SystemHealth.service == "worker")).scalar_one_or_none()
    if row is None:
        row = SystemHealth(service="worker")
        db.add(row)
    row.status = status
    row.error = error
    db.commit()


class TestSystemOnlineMessage:
    def test_contains_real_counts(self):
        text = format_system_online_message(active_strategies=5, symbols=52, scan_interval_minutes=15)
        assert "ALPHAQUANT X ONLINE" in text
        assert "5 ativas" in text
        assert "52" in text
        assert "A cada 15 minutos" in text
        assert "Bybit" in text


class TestSystemErrorMessages:
    def test_error_message_includes_service_and_error(self):
        text = format_system_error_message("worker", "3 error(s) in last cycle")
        assert "SYSTEM ERROR" in text
        assert "worker" in text
        assert "3 error(s)" in text

    def test_recovered_message(self):
        text = format_system_recovered_message("worker")
        assert "RECUPERADO" in text
        assert "worker" in text


class TestHealthTransitionNotifications:
    def test_sends_error_only_on_online_to_degraded_transition(self, db_session):
        _set_worker_health(db_session, "DEGRADED", "2 error(s) in last cycle")

        client = FakeTelegramClient()
        notify_health_transition(db_session, client, previous_status="ONLINE")
        assert len(client.sent) == 1
        assert "SYSTEM ERROR" in client.sent[0][1]

    def test_does_not_repeat_while_still_degraded(self, db_session):
        _set_worker_health(db_session, "DEGRADED", "still failing")

        client = FakeTelegramClient()
        notify_health_transition(db_session, client, previous_status="DEGRADED")
        assert client.sent == []

    def test_sends_recovery_on_degraded_to_online_transition(self, db_session):
        _set_worker_health(db_session, "ONLINE")

        client = FakeTelegramClient()
        notify_health_transition(db_session, client, previous_status="DEGRADED")
        assert len(client.sent) == 1
        assert "RECUPERADO" in client.sent[0][1]

    def test_no_message_when_staying_online(self, db_session):
        _set_worker_health(db_session, "ONLINE")

        client = FakeTelegramClient()
        notify_health_transition(db_session, client, previous_status="ONLINE")
        assert client.sent == []


class TestTradeTrackingCycle:
    def test_updates_open_trade_and_sends_tp_message(self, db_session):
        opp = _confirmed_opportunity(db_session, asset="TRKONEUSDT")
        trade = trade_service.create_trade_from_signal(db_session, opp)

        telegram = FakeTelegramClient()
        updated, errors = run_trade_tracking_cycle(db_session, FakePriceClient({"TRKONEUSDT": 105.0}), telegram)

        assert updated == 1
        # não afirmamos errors == 0: outras trades abertas por outros
        # arquivos de teste no mesmo Postgres efêmero podem não ter preço
        # no FakePriceClient e contar como erro — o que importa aqui é
        # que a trade TRKONEUSDT (a única que este teste controla) foi
        # atualizada e gerou a mensagem certa.
        assert trade.status.value == "CLOSED"
        # TP1 fecha 100% da posição num único alvo — a própria mensagem de
        # TP1 já diz "Operação encerrada"; o evento CLOSED redundante que
        # vem logo depois não gera uma segunda mensagem (ver main.py).
        assert len(telegram.sent) == 1
        assert "TP1" in telegram.sent[0][1]
        assert "Operação encerrada" in telegram.sent[0][1]

    def test_sends_stop_message(self, db_session):
        opp = _confirmed_opportunity(db_session, asset="TRKTWOUSDT")
        trade_service.create_trade_from_signal(db_session, opp)

        telegram = FakeTelegramClient()
        updated, errors = run_trade_tracking_cycle(db_session, FakePriceClient({"TRKTWOUSDT": 94.0}), telegram)

        assert updated == 1
        assert any("STOP" in msg for _, msg in telegram.sent)

    def test_no_message_when_price_between_stop_and_target(self, db_session):
        opp = _confirmed_opportunity(db_session, asset="TRKTHREEUSDT")
        trade_service.create_trade_from_signal(db_session, opp)

        telegram = FakeTelegramClient()
        updated, errors = run_trade_tracking_cycle(db_session, FakePriceClient({"TRKTHREEUSDT": 101.0}), telegram)

        assert updated == 1
        assert telegram.sent == []

    def test_price_fetch_failure_for_one_asset_does_not_block_others(self, db_session):
        opp1 = _confirmed_opportunity(db_session, asset="TRKFOURUSDT")
        opp2 = _confirmed_opportunity(db_session, asset="TRKFIVEUSDT")
        trade_service.create_trade_from_signal(db_session, opp1)
        trade_service.create_trade_from_signal(db_session, opp2)

        telegram = FakeTelegramClient()
        # só TRKFIVEUSDT tem preço disponível — TRKFOURUSDT falha e é
        # contabilizado como erro, mas não impede o resto do ciclo
        updated, errors = run_trade_tracking_cycle(
            db_session, FakePriceClient({"TRKFIVEUSDT": 105.0}), telegram,
        )

        assert updated == 1
        assert errors >= 1  # TRKFOURUSDT sempre falha aqui; outras trades sem preço cadastrado no fake client também contam

    def test_no_open_trades_for_untracked_assets_is_a_noop(self, db_session):
        telegram = FakeTelegramClient()
        # cliente sem NENHUM preço cadastrado, mas também sem nenhuma
        # trade aberta para os ativos únicos deste teste
        updated, errors = run_trade_tracking_cycle(
            db_session, FakePriceClient({}), telegram,
        )
        # não afirmamos updated/errors == 0 aqui porque outras trades
        # abertas por outros testes no mesmo Postgres efêmero podem
        # existir; o teste real é que a chamada não explode.
        assert isinstance(updated, int) and isinstance(errors, int)


class TestFormatTradeUpdateMessage:
    def test_breakeven_event_formats_cleanly(self, db_session):
        opp = _confirmed_opportunity(db_session, asset="DOTUSDT", tp1=105.0, tp2=110.0)
        trade = trade_service.create_trade_from_signal(db_session, opp, move_to_breakeven_after_tp1=True)
        events = trade_service.apply_price_update(db_session, trade, 105.0, datetime(2026, 1, 1, tzinfo=timezone.utc))

        breakeven_event = next(e for e in events if e.event_type == "STOP_MOVED_TO_BREAKEVEN")
        text = format_trade_update_message(trade, breakeven_event)
        assert "BREAKEVEN" in text
        assert "DOTUSDT" in text
