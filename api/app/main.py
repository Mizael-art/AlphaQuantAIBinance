import asyncio
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.session import SessionLocal
from alphaquant_core.telegram.client import TelegramClient
from app.routers import backtests, health, market_data, opportunities, playbooks, summary, webhooks

# Adiciona o diretório do worker ao sys.path para reutilizar a função de scan
worker_path = Path(__file__).resolve().parent.parent.parent / "worker"
if str(worker_path) not in sys.path:
    sys.path.insert(0, str(worker_path))

logger = logging.getLogger("alphaquant.api")
settings = get_settings()


async def _run_embedded_worker():
    """Roda o ciclo do Scanner 24h em background para manter a operação 100% gratuita no Render."""
    logger.info("🤖 Robô Scanner 24h embutido iniciado (Plano Gratuito)...")
    await asyncio.sleep(5)  # tempo para a API e DB iniciarem completamente

    try:
        from app.main import emit_heartbeat, run_scan_cycle
    except ImportError:
        try:
            from worker.app.main import emit_heartbeat, run_scan_cycle
        except Exception as e:
            logger.error("Não foi possível importar o worker: %s", e)
            return

    telegram_client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)

    while True:
        try:
            db = SessionLocal()
            started = time.monotonic()
            assets_scanned, opportunities_found, errors = await asyncio.to_thread(run_scan_cycle, db, telegram_client)
            latency_ms = (time.monotonic() - started) * 1000
            await asyncio.to_thread(emit_heartbeat, db, assets_scanned, opportunities_found, errors, latency_ms)
            db.close()
        except Exception as exc:
            logger.exception("Erro no ciclo do scanner embutido: %s", exc)
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicia o scanner embutido em background no plano Free do Render
    worker_task = asyncio.create_task(_run_embedded_worker())
    yield
    worker_task.cancel()


app = FastAPI(
    title="AlphaQuant X API",
    description="Market Intelligence & Trade Scanner",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restringir ao domínio do dashboard em produção
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(market_data.router)
app.include_router(opportunities.router)
app.include_router(playbooks.router)
app.include_router(summary.router)
app.include_router(backtests.router)


@app.get("/")
def root() -> dict:
    return {
        "name": "ALPHAQUANT X",
        "tagline": "DON'T CHASE TRADES. FIND QUALITY.",
        "environment": settings.ENVIRONMENT,
        "test_mode": settings.TEST_MODE,
        "embedded_worker": True,
    }

