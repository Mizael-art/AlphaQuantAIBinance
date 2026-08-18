from datetime import datetime, timedelta, timezone

from alphaquant_core.db.models import Alert, AlertType, DecisionResult, TelegramStatus
from alphaquant_core.engines.alert_engine import decide_alert
from alphaquant_core.engines.data_engine import Candle
from alphaquant_core.playbooks.runner import scan_and_score
from alphaquant_core.telegram.client import SendResult
from alphaquant_core.telegram.queue import enqueue_alert, process_pending_alerts

from tests.playbook_fixtures import uptrend_pullback_to_ema50


class FakeClient:
    def __init__(self, df):
        self._df = df

    def get_klines(self, symbol, timeframe, limit=200):
        rows = self._df.reset_index()
        return [
            Candle(
                timestamp=row["index"].to_pydatetime(), open=row["open"], high=row["high"],
                low=row["low"], close=row["close"], volume=row["volume"],
            )
            for _, row in rows.tail(limit).iterrows()
        ]


class FakeTelegramClient:
    def __init__(self, always_fail: bool = False):
        self.sent: list[tuple[str, str]] = []
        self.always_fail = always_fail

    def send_message(self, chat_id, text):
        if self.always_fail:
            return SendResult(success=False, error="falha simulada")
        self.sent.append((chat_id, text))
        return SendResult(success=True, message_id=str(len(self.sent)))


def _entrar_opportunity(db_session, symbol: str):
    df = uptrend_pullback_to_ema50()
    _ctx, _results, opportunities = scan_and_score(db_session, symbol, "1h", client=FakeClient(df), htf_regime="BULLISH")
    entrar = [o for o in opportunities if o.decision == DecisionResult.ENTRAR]
    assert entrar, "fixture deveria produzir pelo menos um ENTRAR com HTF disponível"
    return entrar[0]


def test_decide_alert_reprovar_without_prior_alert_is_silent(db_session):
    """Seção 69: reprovar algo que nunca foi anunciado não deve virar mensagem."""
    df = uptrend_pullback_to_ema50()
    _ctx, results, opportunities = scan_and_score(db_session, "SILENTUSDT", "1h", client=FakeClient(df))
    reprovados = [o for o in opportunities if o.decision == DecisionResult.REPROVAR]
    assert reprovados

    alert_type = decide_alert(db_session, reprovados[0])
    assert alert_type is None


def test_decide_alert_entrar_produces_signal(db_session):
    opp = _entrar_opportunity(db_session, "ALERTUSDT")
    alert_type = decide_alert(db_session, opp)
    assert alert_type == AlertType.SIGNAL


def test_full_pipeline_enqueue_and_send(db_session):
    opp = _entrar_opportunity(db_session, "PIPEUSDT")
    alert_type = decide_alert(db_session, opp)
    enqueue_alert(db_session, opp, alert_type)

    client = FakeTelegramClient()
    sent, failed = process_pending_alerts(db_session, client)

    assert sent == 1
    assert failed == 0
    assert len(client.sent) == 1
    chat_id, text = client.sent[0]
    assert chat_id == "test"  # TELEGRAM_SIGNALS_CHAT_ID padrão do conftest de testes
    assert "PIPEUSDT" in text

    alert = db_session.query(Alert).filter_by(opportunity_id=opp.id).one()
    assert alert.telegram_status == TelegramStatus.SENT
    assert alert.message_id is not None
    assert alert.sent_at is not None


def test_cooldown_prevents_duplicate_alert_for_same_decision(db_session):
    opp = _entrar_opportunity(db_session, "COOLDOWNUSDT")
    first = decide_alert(db_session, opp)
    enqueue_alert(db_session, opp, first)
    process_pending_alerts(db_session, FakeTelegramClient())

    second = decide_alert(db_session, opp)  # mesma decisão, ainda dentro do cooldown
    assert second is None

    total_alerts = db_session.query(Alert).filter_by(opportunity_id=opp.id).count()
    assert total_alerts == 1


def test_reprovar_after_signal_produces_invalidation(db_session):
    opp = _entrar_opportunity(db_session, "INVALUSDT")
    alert_type = decide_alert(db_session, opp)
    enqueue_alert(db_session, opp, alert_type)
    process_pending_alerts(db_session, FakeTelegramClient())

    # expira o cooldown manualmente e simula o setup virando REPROVAR
    last_alert = db_session.query(Alert).filter_by(opportunity_id=opp.id).order_by(Alert.created_at.desc()).first()
    last_alert.created_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    db_session.commit()

    opp.decision = DecisionResult.REPROVAR
    db_session.commit()

    new_alert_type = decide_alert(db_session, opp)
    assert new_alert_type == AlertType.INVALIDATION


def test_retry_reaches_failed_after_three_attempts(db_session):
    opp = _entrar_opportunity(db_session, "RETRYUSDT")
    enqueue_alert(db_session, opp, AlertType.SIGNAL)

    failing_client = FakeTelegramClient(always_fail=True)
    for _ in range(3):
        process_pending_alerts(db_session, failing_client)

    alert = db_session.query(Alert).filter_by(opportunity_id=opp.id).one()
    assert alert.retry_count == 3
    assert alert.telegram_status == TelegramStatus.FAILED

    # uma 4a tentativa não deve processar um alerta já FAILED (nunca reprocessa o encerrado)
    sent, failed = process_pending_alerts(db_session, failing_client)
    assert sent == 0 and failed == 0


def test_never_resends_an_already_sent_alert(db_session):
    opp = _entrar_opportunity(db_session, "NORESENDUSDT")
    enqueue_alert(db_session, opp, AlertType.SIGNAL)

    client = FakeTelegramClient()
    process_pending_alerts(db_session, client)
    process_pending_alerts(db_session, client)  # roda de novo — não deve reenviar

    assert len(client.sent) == 1


def test_future_opportunity_produces_future_alert(db_session):
    """Fase 11: uma Future Opportunity real (decision=None) precisa gerar alert_type=FUTURE."""
    df = uptrend_pullback_to_ema50()
    _ctx, results, opportunities = scan_and_score(db_session, "FUTUREALERTUSDT", "1h", client=FakeClient(df))

    future_opps = [o for o in opportunities if o.decision is None]
    assert future_opps  # a fixture produz pelo menos uma Future Opportunity

    alert_type = decide_alert(db_session, future_opps[0])
    assert alert_type == AlertType.FUTURE

    enqueue_alert(db_session, future_opps[0], alert_type)
    client = FakeTelegramClient()
    sent, failed = process_pending_alerts(db_session, client)
    assert sent == 1 and failed == 0
    assert "FUTURE OPPORTUNITY" in client.sent[0][1]
