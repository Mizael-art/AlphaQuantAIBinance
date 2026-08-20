from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture()
def _mocked_telegram_send():
    """
    Evita chamada de rede real à API do Telegram nos testes — mocka no
    nível do `python-telegram-bot.Bot`, o mesmo ponto usado pelo
    smoke-test manual deste endpoint.
    """
    with patch("alphaquant_core.telegram.client.Bot") as mock_bot_cls:
        instance = mock_bot_cls.return_value
        fake_result = type("FakeResult", (), {"message_id": 4242})()
        instance.send_message = AsyncMock(return_value=fake_result)
        yield instance


def test_telegram_webhook_rejects_missing_secret(client, _mocked_telegram_send, monkeypatch):
    from alphaquant_core.core import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "supersecret")
    config.get_settings.cache_clear()

    response = client.post(
        "/webhooks/telegram",
        json={"message": {"text": "/analisar", "chat": {"id": -100111}, "from": {"username": "joao"}}},
    )
    assert response.status_code == 401
    config.get_settings.cache_clear()


def test_telegram_webhook_ignores_non_command_text(db_session, client, _mocked_telegram_send):
    response = client.post(
        "/webhooks/telegram",
        json={"message": {"text": "bom dia pessoal", "chat": {"id": -100111}, "from": {"username": "joao"}}},
    )
    assert response.status_code == 200

    from alphaquant_core.services.manual_scan_service import has_pending_manual_scan
    assert has_pending_manual_scan(db_session) is False


def test_telegram_webhook_enqueues_manual_scan_from_authorized_chat(db_session, client, _mocked_telegram_send):
    from alphaquant_core.core.config import get_settings
    settings = get_settings()

    response = client.post(
        "/webhooks/telegram",
        json={
            "message": {
                "text": "/analisar",
                "chat": {"id": settings.TELEGRAM_SIGNALS_CHAT_ID},
                "from": {"username": "joao"},
            },
        },
    )
    assert response.status_code == 200

    from alphaquant_core.services.manual_scan_service import claim_pending_manual_scan
    claim = claim_pending_manual_scan(db_session)
    assert claim is not None
    assert claim.requested_by_username == "joao"
    _mocked_telegram_send.send_message.assert_called()


def test_telegram_webhook_rejects_unauthorized_chat(db_session, client, _mocked_telegram_send):
    response = client.post(
        "/webhooks/telegram",
        json={"message": {"text": "/scan", "chat": {"id": -999999999}, "from": {"username": "estranho"}}},
    )
    assert response.status_code == 200

    from alphaquant_core.services.manual_scan_service import has_pending_manual_scan
    assert has_pending_manual_scan(db_session) is False


def test_telegram_webhook_accepts_command_with_bot_username_suffix(db_session, client, _mocked_telegram_send):
    from alphaquant_core.core.config import get_settings
    settings = get_settings()

    response = client.post(
        "/webhooks/telegram",
        json={
            "message": {
                "text": "/analisar@AlphaQuantXBot",
                "chat": {"id": settings.TELEGRAM_SIGNALS_CHAT_ID},
                "from": {"username": "maria"},
            },
        },
    )
    assert response.status_code == 200

    from alphaquant_core.services.manual_scan_service import claim_pending_manual_scan
    claim = claim_pending_manual_scan(db_session)
    assert claim is not None
    assert claim.requested_by_username == "maria"
