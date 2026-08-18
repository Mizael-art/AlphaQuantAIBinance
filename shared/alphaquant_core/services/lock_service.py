"""
Lock distribuído (seção 47 do master prompt) usando os advisory locks
nativos do Postgres — nenhuma infraestrutura extra (Redis) é necessária
só para isso.

`pg_try_advisory_lock`/`pg_advisory_unlock` são amarrados à CONEXÃO do
banco, não à transação: o lock só é liberado de verdade quando chamamos
`release_lock` explicitamente na MESMA sessão que o adquiriu (ou quando a
conexão cai). Por isso este módulo sempre recebe a `Session` já em uso
pelo chamador — nunca abre uma conexão nova para lock/unlock.
"""
from __future__ import annotations

import zlib

from sqlalchemy import text
from sqlalchemy.orm import Session


def _lock_key(key: str) -> int:
    """
    pg_advisory_lock espera um bigint. crc32 dá um inteiro de 32 bits
    determinístico a partir da string — colisão é teoricamente possível
    mas irrelevante aqui: na pior hipótese, dois asset+timeframe
    diferentes disputam o mesmo lock por acaso, e um deles só espera o
    próximo ciclo (nunca corrompe dado, só adia um scan).
    """
    return zlib.crc32(key.encode("utf-8"))


def try_acquire_lock(db: Session, key: str) -> bool:
    """Não bloqueia — devolve True se conseguiu o lock, False se outro processo já o detém."""
    result = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _lock_key(key)}).scalar()
    return bool(result)


def release_lock(db: Session, key: str) -> None:
    db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _lock_key(key)})
