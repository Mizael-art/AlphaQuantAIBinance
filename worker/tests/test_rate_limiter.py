from alphaquant_core.services.rate_limiter import RateLimiter


def test_rate_limiter_does_not_wait_on_first_call():
    sleeps = []
    clock = iter([100.0, 100.0])
    limiter = RateLimiter(1.0, clock=lambda: next(clock), sleep=lambda s: sleeps.append(s))

    limiter.wait()
    assert sleeps == []


def test_rate_limiter_waits_remaining_interval_between_calls():
    # primeira chamada em t=100, segunda em t=100.2 (0.2s depois) com
    # intervalo mínimo de 1.0s -> deve esperar 0.8s
    clock_values = iter([100.0, 100.0, 100.2, 100.2])
    sleeps = []
    limiter = RateLimiter(1.0, clock=lambda: next(clock_values), sleep=lambda s: sleeps.append(s))

    limiter.wait()
    limiter.wait()

    assert len(sleeps) == 1
    assert abs(sleeps[0] - 0.8) < 1e-9


def test_rate_limiter_does_not_wait_if_interval_already_elapsed():
    # primeira chamada em t=100, segunda em t=105 (5s depois) com
    # intervalo mínimo de 1.0s -> não precisa esperar
    clock_values = iter([100.0, 100.0, 105.0, 105.0])
    sleeps = []
    limiter = RateLimiter(1.0, clock=lambda: next(clock_values), sleep=lambda s: sleeps.append(s))

    limiter.wait()
    limiter.wait()

    assert sleeps == []
