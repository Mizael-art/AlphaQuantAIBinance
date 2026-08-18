"""
Rate limiting simples (Fase 14 — seção 42): espaçamento mínimo entre
chamadas consecutivas. Suficiente na escala deste projeto — não precisa
de token bucket distribuído (um único Worker por enquanto, seção 8).
"""
from __future__ import annotations

import time
from typing import Callable


class RateLimiter:
    def __init__(
        self,
        min_interval_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last_call is not None:
            elapsed = now - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_call = self._clock()
