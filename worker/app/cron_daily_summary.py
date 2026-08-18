"""
Entrypoint para Render Cron Job — resumo diário (seção 21).

Configuração sugerida no Render: Cron Job separado do Worker/API, rodando
uma vez por dia (ex.: `0 23 * * *` para 23:00 UTC), comando:
`python app/cron_daily_summary.py`.
"""
import logging

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.session import SessionLocal
from alphaquant_core.telegram.client import TelegramClient
from alphaquant_core.telegram.summary import compute_daily_summary, format_daily_summary_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("alphaquant.cron.daily_summary")


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        summary = compute_daily_summary(db)
        text = format_daily_summary_message(summary)
        client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)
        result = client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, text)
        if result.success:
            logger.info("resumo diário enviado, message_id=%s", result.message_id)
        else:
            logger.error("falha ao enviar resumo diário: %s", result.error)
    finally:
        db.close()


if __name__ == "__main__":
    main()
