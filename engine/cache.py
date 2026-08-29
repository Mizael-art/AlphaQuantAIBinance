import time
import pandas as pd
from typing import Dict, Tuple

from api.market_data import MarketData
from config import DEFAULT_KLINES_LIMIT, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

class GlobalKlineCache:
    """Cache global na memória para evitar re-download de candles no mesmo ciclo."""
    _cache: Dict[Tuple[str, str, int], Tuple[float, pd.DataFrame]] = {}
    _ttl_seconds: int = 180  # 3 minutos é tempo suficiente para o ciclo inteiro usar os mesmos candles

    @classmethod
    def get(cls, symbol: str, timeframe: str, limit: int) -> pd.DataFrame | None:
        key = (symbol, timeframe, limit)
        if key in cls._cache:
            timestamp, df = cls._cache[key]
            if time.time() - timestamp < cls._ttl_seconds:
                return df.copy(deep=False)
        return None

    @classmethod
    def set(cls, symbol: str, timeframe: str, limit: int, df: pd.DataFrame) -> None:
        key = (symbol, timeframe, limit)
        cls._cache[key] = (time.time(), df.copy(deep=False))
        
    @classmethod
    def clear(cls):
        cls._cache.clear()

def enable_market_data_cache():
    """Monkey-patch global no MarketData para usar cache transparente no ciclo autônomo.
    Isso evita reescrever o scanner ou o discovery, que instanciam MarketData diretamente.
    """
    original_get_ohlcv = MarketData.get_ohlcv_dataframe

    def cached_get_ohlcv_dataframe(
        self,
        symbol: str = DEFAULT_SYMBOL,
        timeframe: str = DEFAULT_TIMEFRAME,
        limit: int = DEFAULT_KLINES_LIMIT,
    ) -> pd.DataFrame:
        cached_df = GlobalKlineCache.get(symbol, timeframe, limit)
        if cached_df is not None:
            return cached_df
        
        df = original_get_ohlcv(self, symbol, timeframe, limit)
        GlobalKlineCache.set(symbol, timeframe, limit, df)
        return df

    # Aplica o patch se ainda não foi aplicado
    if MarketData.get_ohlcv_dataframe.__name__ != "cached_get_ohlcv_dataframe":
        MarketData.get_ohlcv_dataframe = cached_get_ohlcv_dataframe
