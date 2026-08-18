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

    # Market data
    MARKET_DATA_API_KEY: str | None = None

    # Auth
    JWT_SECRET: str

    # Modo de operação
    TEST_MODE: bool = True  # True = PAPER/TEST MODE, nunca trata alerta como sinal real

    # Data Engine — ativos e timeframes monitorados pelo scanner
    SCAN_ASSETS: str = "BTCUSDT,ETHUSDT"
    SCAN_TIMEFRAMES: str = "15m,1h,4h"

    @property
    def database_url_normalized(self) -> str:
        url = (self.DATABASE_URL or "").strip().strip('"').strip("'")
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql://", 1)
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

