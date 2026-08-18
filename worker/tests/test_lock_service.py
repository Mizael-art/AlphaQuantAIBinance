from alphaquant_core.services.lock_service import release_lock, try_acquire_lock


def test_lock_can_be_acquired_when_free(db_session):
    acquired = try_acquire_lock(db_session, "scan:BTCUSDT:1h")
    assert acquired is True
    release_lock(db_session, "scan:BTCUSDT:1h")


def test_lock_blocks_a_second_concurrent_session(db_session):
    """
    O caso real que o lock existe para prevenir: duas conexões diferentes
    (dois processos do Worker, por exemplo) tentando processar o mesmo
    asset+timeframe ao mesmo tempo.
    """
    from alphaquant_core.db.session import SessionLocal

    other_session = SessionLocal()
    try:
        first = try_acquire_lock(db_session, "scan:ETHUSDT:15m")
        second = try_acquire_lock(other_session, "scan:ETHUSDT:15m")

        assert first is True
        assert second is False  # outra conexão não consegue o mesmo lock

        release_lock(db_session, "scan:ETHUSDT:15m")

        third = try_acquire_lock(other_session, "scan:ETHUSDT:15m")
        assert third is True  # liberado, agora a segunda conexão consegue
        release_lock(other_session, "scan:ETHUSDT:15m")
    finally:
        other_session.close()


def test_lock_is_scoped_per_key_not_global(db_session):
    from alphaquant_core.db.session import SessionLocal

    other_session = SessionLocal()
    try:
        acquired_a = try_acquire_lock(db_session, "scan:BTCUSDT:4h")
        acquired_b = try_acquire_lock(other_session, "scan:SOLUSDT:4h")  # chave diferente

        assert acquired_a is True
        assert acquired_b is True  # não conflita — são asset+timeframe diferentes

        release_lock(db_session, "scan:BTCUSDT:4h")
        release_lock(other_session, "scan:SOLUSDT:4h")
    finally:
        other_session.close()
