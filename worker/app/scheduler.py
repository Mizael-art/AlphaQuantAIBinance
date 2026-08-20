"""
scheduler — seção 6: o Worker nunca roda "N minutos depois de o processo
iniciar". Ele sincroniza com o fechamento REAL da vela (00:00, 00:15,
00:30, ...), usando UTC internamente (seção 62).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def seconds_until_next_boundary(interval_minutes: int, now: datetime | None = None) -> float:
    """
    Segundos até o próximo múltiplo de `interval_minutes` dentro da hora
    (ex.: interval_minutes=15 -> :00, :15, :30, :45). Se `now` já está
    exatamente num boundary, devolve 0.0 (não espera um ciclo inteiro a
    mais) — quem chama já está no instante certo de rodar.
    """
    if interval_minutes <= 0:
        raise ValueError("interval_minutes deve ser positivo")

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    minute_block = (now.minute // interval_minutes) * interval_minutes
    boundary = now.replace(minute=minute_block, second=0, microsecond=0)
    if boundary < now:
        boundary += timedelta(minutes=interval_minutes)

    return max(0.0, (boundary - now).total_seconds())
