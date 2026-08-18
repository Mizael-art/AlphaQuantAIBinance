"""
Entrypoint para Render Cron Job — relatório semanal (seção 22).

Configuração sugerida no Render: Cron Job separado, rodando uma vez por
semana (ex.: `0 23 * * 0` para domingo às 23:00 UTC), comando:
`python app/cron_weekly_report.py`.
"""
import logging

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.session import SessionLocal
from alphaquant_core.telegram.client import TelegramClient
from alphaquant_core.telegram.summary import compute_weekly_report, format_weekly_report_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("alphaquant.cron.weekly_report")


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        report = compute_weekly_report(db)
        text = format_weekly_report_message(report)
        client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)
        result = client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, text)
        if result.success:
            logger.info("relatório semanal enviado, message_id=%s", result.message_id)
        else:
            logger.error("falha ao enviar relatório semanal: %s", result.error)
    finally:
        db.close()


if __name__ == "__main__":
    main()
