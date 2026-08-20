"""
Configuração central do AlphaQuant X.

Todos os segredos vêm exclusivamente de variáveis de ambiente.
Nunca hardcode tokens, chaves ou senhas aqui.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "development"  # development | production

    # Database
    DATABASE_URL: str

    # Redis / Queue (opcional na Fase 1)
    REDIS_URL: str | None = None

    # TradingView webhook
    TRADINGVIEW_WEBHOOK_SECRET: str

    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_SIGNALS_CHAT_ID: str
    TELEGRAM_FUTURE_CHAT_ID: str
    # Secret configurado no `setWebhook` (header X-Telegram-Bot-Api-Secret-Token) —
    # garante que POST /webhooks/telegram só aceita updates vindos do Telegram
    # de verdade. Opcional só para não quebrar quem ainda não fez o setWebhook.
    TELEGRAM_WEBHOOK_SECRET: str | None = None
    # Intervalo de polling (segundos) usado pelo Worker enquanto espera o
    # próximo fechamento de vela automático, para reagir rápido a um
    # /analisar sem esperar os SCAN_INTERVAL_MINUTES inteiros.
    MANUAL_SCAN_POLL_SECONDS: int = 5

    # Market data
    MARKET_DATA_API_KEY: str | None = None

    # Auth
    JWT_SECRET: str

    # Strategy Lab — área protegida (seção 24). Nunca hardcoded no
    # frontend; valores padrão documentados pela própria especificação,
    # mas sempre sobrescrevíveis por variável de ambiente em produção.
    ALPHAQUANT_ADMIN_USER: str = "AlphaQuant"
    ALPHAQUANT_ADMIN_PASSWORD: str = "VIP"

    # Modo de operação
    TEST_MODE: bool = True  # True = PAPER/TEST MODE, nunca trata alerta como sinal real

    # Data Engine — ativos e timeframes monitorados pelo scanner.
    # SCAN_ASSETS="AUTO" ativa a descoberta dinâmica de símbolos USDT
    # Perpetual na Bybit (seção 4); o padrão continua sendo a lista
    # manual abaixo, para não mudar o comportamento de um worker já
    # implantado sem uma escolha explícita.
    SCAN_ASSETS: str = "BTCUSDT,ETHUSDT"
    SCAN_TIMEFRAMES: str = "15m,1h,4h"
    MIN_SYMBOLS: int = 50
    MAX_SYMBOLS: int = 100
    SCAN_INTERVAL_MINUTES: int = 15
    REPORT_INTERVAL_MINUTES: int = 60

    @property
    def database_url_normalized(self) -> str:
        url = (self.DATABASE_URL or "").strip().strip('"').strip("'")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        # Trata hostnames curtos do Render (dpg-xxxxxx-a) quando o DNS interno falha
        if "@dpg-" in url and ".render.com" not in url:
            prefix, remainder = url.split("@dpg-", 1)
            if "/" in remainder:
                host_code, db_name = remainder.split("/", 1)
                url = f"{prefix}@dpg-{host_code}.singapore-postgres.render.com/{db_name}"
            else:
                url = f"{prefix}@dpg-{remainder}.singapore-postgres.render.com"
        return url



    @property
    def scan_assets(self) -> list[str]:
        return [s.strip().upper() for s in self.SCAN_ASSETS.split(",") if s.strip()]

    @property
    def scan_timeframes(self) -> list[str]:
        return [t.strip() for t in self.SCAN_TIMEFRAMES.split(",") if t.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production" and not self.TEST_MODE


@lru_cache
def get_settings() -> Settings:
    return Settings()

