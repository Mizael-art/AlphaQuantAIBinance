"""
Mesmo padrão do worker/tests/conftest.py: sobe um PostgreSQL real e
efêmero via pgserver (pip puro, sem apt/docker) ANTES de qualquer import
de alphaquant_core, e semeia os 10 playbooks (espelhando a migration
0002) para os testes que dependem dos limiares por playbook.
"""
import atexit
import os
import tempfile

os.environ.setdefault("TRADINGVIEW_WEBHOOK_SECRET", "test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test")
os.environ.setdefault("TELEGRAM_SIGNALS_CHAT_ID", "test")
os.environ.setdefault("TELEGRAM_FUTURE_CHAT_ID", "test")
os.environ.setdefault("JWT_SECRET", "test")

try:
    import pgserver

    _datadir = tempfile.mkdtemp(prefix="aqx_api_test_pg_")
    _server = pgserver.get_server(_datadir, cleanup_mode="delete")
    os.environ["DATABASE_URL"] = _server.get_uri().replace("postgresql://", "postgresql+psycopg2://")
    atexit.register(_server.cleanup)
    _HAS_POSTGRES = True
except ImportError:
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg2://unused/unused")
    _HAS_POSTGRES = False

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    if not _HAS_POSTGRES:
        yield
        return

    from alphaquant_core.db import models  # noqa: F401
    from alphaquant_core.db.session import Base, SessionLocal, engine

    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        if db.query(models.Playbook).count() == 0:
            for name, status in [
                ("Trend Continuation EMA50", models.PlaybookStatus.VALIDATING),
                ("Liquidity Sweep Reversal", models.PlaybookStatus.VALIDATING),
                ("Order Block Reaction", models.PlaybookStatus.VALIDATING),
                ("FVG Retracement", models.PlaybookStatus.VALIDATING),
                ("Breakout + Retest", models.PlaybookStatus.VALIDATING),
                ("Wyckoff Spring", models.PlaybookStatus.VALIDATING),
                ("Wyckoff Upthrust", models.PlaybookStatus.VALIDATING),
                ("HTF Continuation", models.PlaybookStatus.VALIDATING),
                ("Compression Breakout", models.PlaybookStatus.VALIDATING),
                ("Open Range Breakout", models.PlaybookStatus.EXPERIMENTAL),
            ]:
                db.add(models.Playbook(
                    name=name, version="v1.0", tier="A",
                    minimum_score=70.0, minimum_rr=2.0, status=status,
                ))
            db.commit()
    finally:
        db.close()

    yield


@pytest.fixture()
def db_session():
    if not _HAS_POSTGRES:
        pytest.skip("pgserver não instalado — pulando teste de integração com Postgres")

    from alphaquant_core.db.session import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
