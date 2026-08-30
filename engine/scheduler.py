import logging
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# A importação da função ocorrerá apenas dentro do job para evitar dependências circulares na inicialização
logger = logging.getLogger("alphaquant.engine.scheduler")

_scheduler: BackgroundScheduler | None = None
_cycle_lock = threading.Lock()

def _run_cycle_job():
    """Wrapper para rodar o ciclo garantindo exclusividade (mutex)."""
    # blocking=False faz com que o ciclo aborte imediatamente se o anterior ainda rodar.
    if not _cycle_lock.acquire(blocking=False):
        logger.warning("Ciclo autônomo anterior ainda em execução. Ignorando este disparo.")
        return
        
    try:
        # Importação no escopo da função para ligar as peças de orquestração
        from engine.autonomous_cycle import run_market_cycle
        run_market_cycle()
    except Exception as exc:
        logger.error(f"Erro fatal não tratado no pipeline do ciclo autônomo: {exc}")
    finally:
        _cycle_lock.release()

def start_scheduler(interval_minutes: int = 15):
    """Inicia o scheduler no startup da aplicação."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("Scheduler já está rodando. Ignorando tentativa dupla de inicialização.")
        return

    _scheduler = BackgroundScheduler()
    
    # Execução a cada N minutos. max_instances=1 é uma camada extra de proteção no APScheduler.
    _scheduler.add_job(
        _run_cycle_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="autonomous_market_cycle",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    logger.info(f"Scheduler iniciado. Ciclo agendado para rodar a cada {interval_minutes} minutos.")

    # Dispara o primeiro ciclo imediatamente em background para popular os dados sem esperar o intervalo
    threading.Thread(target=_run_cycle_job, daemon=True).start()
    logger.info("Primeiro ciclo de mercado disparado imediatamente na inicialização.")

def shutdown_scheduler():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler encerrado.")
