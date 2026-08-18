"""
Retry com backoff exponencial (Fase 14 — seção 39: self-healing).

Uso genérico — quem chama decide o que é "retryable" (ex.: erro de rede
sim, erro de payload/validação não) via `should_retry`.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger("alphaquant.retry")

T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: float = 0.5,
    should_retry: Callable[[Exception], bool] = lambda exc: True,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """
    Chama `fn()`; em caso de exceção, tenta de novo com backoff
    exponencial (`base_delay * 2**(tentativa-1)`) até `max_attempts`.
    Reraise imediato se `should_retry(exc)` for False (erro não-transiente
    — tentar de novo não ajudaria) ou se as tentativas se esgotarem.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — decisão de retry é de quem chama, via should_retry
            last_exc = exc
            if attempt == max_attempts or not should_retry(exc):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "tentativa %s/%s falhou (%s) — nova tentativa em %.1fs",
                attempt, max_attempts, exc, delay,
            )
            sleep(delay)
    raise last_exc  # pragma: no cover — inatingível, loop sempre retorna ou re-levanta
