import pytest

from alphaquant_core.services.retry import retry_with_backoff


def test_retry_succeeds_on_first_attempt_without_sleeping():
    calls = []
    sleeps = []

    def fn():
        calls.append(1)
        return "ok"

    result = retry_with_backoff(fn, sleep=lambda s: sleeps.append(s))
    assert result == "ok"
    assert len(calls) == 1
    assert sleeps == []


def test_retry_succeeds_after_transient_failures():
    attempts = {"n": 0}
    sleeps = []

    def fn():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    result = retry_with_backoff(fn, max_attempts=3, base_delay=1.0, sleep=lambda s: sleeps.append(s))
    assert result == "ok"
    assert attempts["n"] == 3
    assert sleeps == [1.0, 2.0]  # backoff exponencial: 1*(2^0), 1*(2^1)


def test_retry_exhausts_attempts_and_reraises():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        raise ConnectionError("always fails")

    with pytest.raises(ConnectionError):
        retry_with_backoff(fn, max_attempts=3, sleep=lambda s: None)
    assert attempts["n"] == 3


def test_retry_does_not_retry_when_should_retry_returns_false():
    attempts = {"n": 0}

    def fn():
        attempts["n"] += 1
        raise ValueError("permanent, not transient")

    with pytest.raises(ValueError):
        retry_with_backoff(
            fn, max_attempts=5, sleep=lambda s: None,
            should_retry=lambda exc: isinstance(exc, ConnectionError),
        )
    assert attempts["n"] == 1  # falhou na primeira, nunca tentou de novo
