"""
Entrypoint para Render Cron Job — Market Intelligence horário (seção 10;
JOB 2 da seção 61). Mesmo padrão de `cron_daily_summary.py`/
`cron_weekly_report.py`: processo separado do Worker, disparado
externamente (Render Cron Job a cada REPORT_INTERVAL_MINUTES, ex.:
`*/60 * * * *`), comando: `python app/cron_hourly_intelligence.py`.

Fica fora do loop principal do Worker de propósito — a mesma decisão
arquitetural já tomada para os relatórios diário/semanal (seção 64: usar
cron externo para jobs com cadência diferente do scanner).
"""
import logging

from alphaquant_core.core.config import get_settings
from alphaquant_core.db.session import SessionLocal
from alphaquant_core.telegram.client import TelegramClient
from alphaquant_core.telegram.summary import compute_hourly_intelligence, format_hourly_intelligence_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("alphaquant.cron.hourly_intelligence")


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        intel = compute_hourly_intelligence(db, window_minutes=settings.REPORT_INTERVAL_MINUTES)
        text = format_hourly_intelligence_message(intel)
        client = TelegramClient(bot_token=settings.TELEGRAM_BOT_TOKEN, test_mode=settings.TEST_MODE)
        result = client.send_message(settings.TELEGRAM_SIGNALS_CHAT_ID, text)
        if result.success:
            logger.info("market intelligence horário enviado, message_id=%s", result.message_id)
        else:
            logger.error("falha ao enviar market intelligence horário: %s", result.error)
    finally:
        db.close()


if __name__ == "__main__":
    main()
