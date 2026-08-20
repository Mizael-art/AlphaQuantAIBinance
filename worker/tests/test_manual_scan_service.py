from alphaquant_core.services.manual_scan_service import (
    claim_pending_manual_scan,
    has_pending_manual_scan,
    request_manual_scan,
)


def test_no_pending_requests_by_default(db_session):
    assert has_pending_manual_scan(db_session) is False
    assert claim_pending_manual_scan(db_session) is None


def test_request_manual_scan_is_visible_as_pending(db_session):
    request_manual_scan(db_session, chat_id="-100111", username="joao")
    assert has_pending_manual_scan(db_session) is True


def test_claim_marks_request_as_processed(db_session):
    request_manual_scan(db_session, chat_id="-100111", username="joao")

    claim = claim_pending_manual_scan(db_session)
    assert claim is not None
    assert claim.requested_by_chat_id == "-100111"
    assert claim.requested_by_username == "joao"

    # Depois de reivindicado, não deve mais aparecer como pendente.
    assert has_pending_manual_scan(db_session) is False
    assert claim_pending_manual_scan(db_session) is None


def test_claim_survives_session_close():
    """
    Regressão: `claim_pending_manual_scan` devolvia antes o objeto ORM
    direto, que expira em `db.commit()` — ler qualquer atributo dele
    depois de fechar a Session (o padrão real de uso em
    `worker/app/main.py::wait_for_next_cycle`) levantava
    `DetachedInstanceError`. Agora devolve um dataclass desacoplado.
    """
    from alphaquant_core.db.session import SessionLocal

    db = SessionLocal()
    request_manual_scan(db, chat_id="-100111", username="maria")
    db.close()

    db2 = SessionLocal()
    claim = claim_pending_manual_scan(db2)
    db2.close()

    # Nenhum acesso a atributo aqui deve tocar a Session já fechada.
    assert claim.requested_by_username == "maria"
    assert claim.requested_by_chat_id == "-100111"


def test_multiple_pending_requests_are_all_claimed_together(db_session):
    request_manual_scan(db_session, chat_id="-100111", username="joao")
    request_manual_scan(db_session, chat_id="-100111", username="maria")

    claim = claim_pending_manual_scan(db_session)
    # Devolve o mais recente...
    assert claim.requested_by_username == "maria"
    # ...mas os dois somem da fila (um único ciclo de scan cobre ambos).
    assert has_pending_manual_scan(db_session) is False
