"""
persistence/db.py
====================

Configuração de engine/sessão do SQLAlchemy (Fase 2 do Plano de
Evolução -- Documento 2/Master, "criar banco de dados").

Produção (Render): variável de ambiente `DATABASE_URL` aponta pro
Postgres gerenciado (`postgresql+psycopg://...`). Local/testes: sem
`DATABASE_URL`, cai para SQLite em arquivo (`alphaquant.db`, no
diretório de trabalho) -- e os testes usam SQLite em memória via
`get_engine(url="sqlite:///:memory:")` explicitamente, nunca tocando
o arquivo local.

Nenhum código de negócio (em `setups/`) importa `sqlalchemy`
diretamente fora deste módulo e de `persistence/models.py` -- mantém
a opção de trocar de ORM/driver sem espalhar a dependência pelo
projeto.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from persistence.models import Base

_DEFAULT_LOCAL_URL = "sqlite:///alphaquant.db"


def _normalize_url(url: str) -> str:
    """
    O Render fornece a connection string do Postgres gerenciado como
    `postgres://...` ou `postgresql://...` (sem dialeto/driver
    explícito) -- o SQLAlchemy exige o driver na URL. Este projeto usa
    `psycopg` (v3, ver requirements.txt), não `psycopg2`.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _sync_schema_columns(engine: Engine, resolved_url: str) -> None:
    """Adiciona colunas novas em tabelas existentes caso não tenham sido criadas (compatível com SQLite e PostgreSQL)."""
    from sqlalchemy import text
    new_cols = {
        "entry_price": "DOUBLE PRECISION" if "postgres" in resolved_url else "FLOAT",
        "exit_price": "DOUBLE PRECISION" if "postgres" in resolved_url else "FLOAT",
        "exit_reason": "VARCHAR(32)",
        "realized_pnl_pct": "DOUBLE PRECISION" if "postgres" in resolved_url else "FLOAT",
        "realized_r_multiple": "DOUBLE PRECISION" if "postgres" in resolved_url else "FLOAT",
        "regime": "VARCHAR(32)",
        "opened_at": "TIMESTAMP WITH TIME ZONE" if "postgres" in resolved_url else "DATETIME",
        "closed_at": "TIMESTAMP WITH TIME ZONE" if "postgres" in resolved_url else "DATETIME",
        "duration_minutes": "DOUBLE PRECISION" if "postgres" in resolved_url else "FLOAT",
    }
    try:
        with engine.connect() as conn:
            if "postgres" in resolved_url:
                for col, ctype in new_cols.items():
                    conn.execute(text(f"ALTER TABLE setups ADD COLUMN IF NOT EXISTS {col} {ctype}"))
                conn.commit()
            elif resolved_url.startswith("sqlite"):
                res = conn.execute(text("PRAGMA table_info(setups)"))
                existing = {row[1] for row in res.fetchall()}
                if existing:
                    for col, ctype in new_cols.items():
                        if col not in existing:
                            conn.execute(text(f"ALTER TABLE setups ADD COLUMN {col} {ctype}"))
                    conn.commit()
    except Exception as exc:
        import logging
        logging.getLogger("alphaquant.persistence").warning(f"Aviso ao sincronizar schema do banco: {exc}")



@lru_cache(maxsize=8)
def get_engine(url: str | None = None) -> Engine:
    """
    `lru_cache` por `url` -- cada URL distinta (produção, dev local,
    `sqlite:///:memory:` de um teste) recebe seu próprio engine/pool,
    sem recriar conexões a cada chamada.
    """
    resolved_url = _normalize_url(url or os.environ.get("DATABASE_URL") or _DEFAULT_LOCAL_URL)
    connect_args = {"check_same_thread": False, "timeout": 30} if resolved_url.startswith("sqlite") else {}
    engine = create_engine(resolved_url, connect_args=connect_args, future=True)
    Base.metadata.create_all(engine)
    _sync_schema_columns(engine, resolved_url)
    return engine



def get_sessionmaker(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False, future=True)


@contextmanager
def session_scope(url: str | None = None):
    """Context manager padrão: commit em sucesso, rollback em exceção."""
    session = get_sessionmaker(url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
