"""
Entrypoint para Render Cron Job — Backtest (Fase 13, seção 55).

Roda os 10 playbooks contra todo ativo/timeframe configurado em
SCAN_ASSETS/SCAN_TIMEFRAMES que já tenha candles suficientes persistidas
(reaproveita o histórico coletado organicamente pelo Worker — não busca
dados novos na Binance). Configuração sugerida no Render: Cron Job
semanal, comando `python app/cron_backtest.py`.
"""
import logging

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.session import SessionLocal
from alphaquant_core.playbooks.backtest_runner import run_and_save_backtest
from alphaquant_core.playbooks.engine import ALL_PLAYBOOKS

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("alphaquant.cron.backtest")


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        for symbol in settings.scan_assets:
            for timeframe in settings.scan_timeframes:
                for playbook in ALL_PLAYBOOKS:
                    stats, row = run_and_save_backtest(db, playbook, symbol, timeframe)
                    if stats is None:
                        logger.info(
                            "backtest skip (candles insuficientes) symbol=%s timeframe=%s playbook=%s",
                            symbol, timeframe, playbook.name,
                        )
                        continue
                    logger.info(
                        "backtest symbol=%s timeframe=%s playbook=%s trades=%s win_rate=%.2f profit_factor=%.2f",
                        symbol, timeframe, playbook.name, stats.trades, stats.win_rate, stats.profit_factor,
                    )
    finally:
        db.close()


if __name__ == "__main__":
    main()
