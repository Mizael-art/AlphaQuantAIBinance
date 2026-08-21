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
from app.routers import auth, backtests, health, market_data, opportunities, playbooks, strategies, summary, webhooks

# Adiciona a raiz do repositório ao sys.path para reutilizar a função de
# scan via `from worker.app.main import ...`. IMPORTANTE: precisa ser a
# raiz do repo (que CONTÉM a pasta worker/), não a própria pasta worker/ —
# senão o import de "worker.app.main" falha com
# "ModuleNotFoundError: No module named 'worker'", pois o Python procura
# um pacote "worker" dentro do próprio diretório worker/, que não existe.
repo_root = Path(__file__).resolve().parent.parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

logger = logging.getLogger("alphaquant.api")
settings = get_settings()


async def _run_embedded_worker():
    """
    Roda o mesmo ciclo do Worker standalone (`worker/app/main.py`) em
    background, para manter a operação 100% gratuita no Render (um único
    processo serve API + Scanner). Precisa espelhar o loop standalone —
    scheduler sincronizado com o fechamento de vela (seção 6), tracking
    de trades abertas (seção 86), mensagem de boot (seção 7) e alertas
    de transição de saúde (seção 42/48) — em vez de reimplementar um
    loop mais simples que fica defasado quando o standalone evolui.
    """
    logger.info("🤖 Robô Scanner 24h embutido iniciado (Plano Gratuito)...")
    await asyncio.sleep(5)  # tempo para a API e DB iniciarem completamente

    try:
        from app.main import (
            emit_heartbeat,
            notify_health_transition,
            run_scan_cycle,
            run_trade_tracking_cycle,
            wait_for_next_cycle,
        )
    except ImportError:
        try:
            from worker.app.main import (
                emit_heartbeat,
                notify_health_transition,
                run_scan_cycle,
                run_trade_tracking_cycle,
                wait_for_next_cycle,
            )
        except Exception as e:
            logger.error("Não foi possível importar o worker: %s", e)
            return

    logger.info("[EMBEDDED_WORKER] import do módulo worker OK")

    from datetime import datetime, timezone

    from alphaquant_core.db.models import StrategyStatus
    from alphaquant_core.engines.bybit_data_engine import BybitMarketDataClient
    from alphaquant_core.services import strategy_service
    from alphaquant_core.telegram.formatting import format_scan_started_message, format_system_online_message
    from alphaquant_core.telegram.summary import compute_cycle_summary, format_cycle_summary_message

    try:
        telegram_client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)

        def _resolve_universe():
            try:
                from app.main import resolve_scan_universe
            except ImportError:
                from worker.app.main import resolve_scan_universe
            return resolve_scan_universe(BybitMarketDataClient())

        logger.info("[EMBEDDED_WORKER] contando estratégias ativas...")
        db = SessionLocal()
        try:
            active_strategies = len(strategy_service.list_strategies(db, status=StrategyStatus.ACTIVE))
        except Exception:
            logger.exception("falha ao contar estratégias ativas para a mensagem de boot")
            active_strategies = 0
        finally:
            db.close()
        logger.info("[EMBEDDED_WORKER] estratégias ativas=%s", active_strategies)

        logger.info("[EMBEDDED_WORKER] resolvendo universo de símbolos (chamada à Bybit)...")
        try:
            symbols_count = await asyncio.to_thread(_resolve_universe)
            symbols_count = len(symbols_count)
        except Exception:
            logger.exception("falha ao resolver universo de símbolos para a mensagem de boot")
            symbols_count = 0
        logger.info("[EMBEDDED_WORKER] universo resolvido, symbols_count=%s", symbols_count)

        boot_text = format_system_online_message(active_strategies, symbols_count, settings.SCAN_INTERVAL_MINUTES)
        logger.info("[EMBEDDED_WORKER] enviando mensagem de boot ao Telegram...")
        boot_result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, boot_text)
        if not boot_result.success:
            logger.error("falha ao enviar mensagem de boot: %s", boot_result.error)
        else:
            logger.info("[EMBEDDED_WORKER] mensagem de boot enviada, entrando no loop principal")
    except Exception:
        # Sem isto, qualquer exceção aqui mataria a Task silenciosamente:
        # a Task fica referenciada em `lifespan` (nunca é coletada pelo GC
        # enquanto o app roda), então o handler padrão do asyncio que
        # loga "Task exception was never retrieved" nunca dispara.
        logger.exception("[EMBEDDED_WORKER] falha fatal na inicialização — worker embutido NÃO vai rodar")
        return

    while True:
        try:
            # `wait_for_next_cycle` faz polling curto de `manual_scan_requests`
            # (comando /analisar do Telegram) enquanto espera o próximo
            # fechamento de vela — roda numa thread pra não travar o event
            # loop da API com os `time.sleep` internos.
            manual, requested_by = await asyncio.to_thread(wait_for_next_cycle, SessionLocal, settings)
            if manual:
                logger.info("análise manual disparada via Telegram (/analisar) por %s", requested_by or "desconhecido")
            else:
                logger.info("scanner embutido: fechamento de vela de %sm atingido", settings.SCAN_INTERVAL_MINUTES)

            cycle_started_at = datetime.now(timezone.utc)
            db = SessionLocal()
            try:
                from sqlalchemy import select
                from alphaquant_core.db.models import SystemHealth

                previous_row = db.execute(select(SystemHealth).where(SystemHealth.service == "worker")).scalar_one_or_none()
                previous_status = previous_row.status if previous_row else None

                started = time.monotonic()

                symbols = await asyncio.to_thread(_resolve_universe)
                started_text = format_scan_started_message(manual, len(symbols), requested_by)
                started_result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, started_text)
                if not started_result.success:
                    logger.error("falha ao enviar mensagem de início de ciclo: %s", started_result.error)

                assets_scanned, opportunities_found, errors = await asyncio.to_thread(
                    run_scan_cycle, db, telegram_client, symbols,
                )
                _updated, trade_errors = await asyncio.to_thread(
                    run_trade_tracking_cycle, db, BybitMarketDataClient(), telegram_client,
                )
                errors += trade_errors

                cycle_summary = await asyncio.to_thread(compute_cycle_summary, db, cycle_started_at)
                summary_text = format_cycle_summary_message(cycle_summary, manual, assets_scanned)
                summary_result = telegram_client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, summary_text)
                if not summary_result.success:
                    logger.error("falha ao enviar resumo de ciclo: %s", summary_result.error)

                latency_ms = (time.monotonic() - started) * 1000
                await asyncio.to_thread(emit_heartbeat, db, assets_scanned, opportunities_found, errors, latency_ms)
                await asyncio.to_thread(notify_health_transition, db, telegram_client, previous_status)
            finally:
                db.close()
        except Exception:
            # Segunda camada de proteção: qualquer exceção não prevista
            # aqui (inclusive fora do `db = SessionLocal()` acima, como
            # falha no próprio `wait_for_next_cycle`) não pode derrubar
            # a Task silenciosamente — loga e tenta de novo no próximo
            # ciclo, em vez de matar o worker embutido pro resto da vida
            # do processo.
            logger.exception("[EMBEDDED_WORKER] erro não tratado no ciclo — worker segue vivo, tentando de novo")
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Inicia o scanner embutido em background no plano Free do Render
    worker_task = asyncio.create_task(_run_embedded_worker())

    def _log_worker_task_exception(task: asyncio.Task) -> None:
        # Rede de segurança final: sem isto, uma exceção que escape de
        # TODOS os try/except de `_run_embedded_worker` mataria a Task
        # sem deixar nenhum rastro no log (ver comentário na função).
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("[EMBEDDED_WORKER] Task morreu com exceção não tratada", exc_info=exc)

    worker_task.add_done_callback(_log_worker_task_exception)
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
app.include_router(auth.router)
app.include_router(strategies.router)


@app.get("/")
def root() -> dict:
    return {
        "name": "ALPHAQUANT X",
        "tagline": "DON'T CHASE TRADES. FIND QUALITY.",
        "environment": settings.ENVIRONMENT,
        "test_mode": settings.TEST_MODE,
        "embedded_worker": True,
    }
