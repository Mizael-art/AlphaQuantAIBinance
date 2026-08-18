"""
Indicadores técnicos calculados sobre o DataFrame de candles.

Implementação manual (sem pandas-ta) para evitar divergência de versões
entre ambientes — as fórmulas seguem a definição clássica (Wilder para
RSI/ATR, EMA exponencial padrão, MACD 12/26/9).
"""
from __future__ import annotations

import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # média de Wilder (equivalente a EMA com alpha = 1/length)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, float("nan"))
    result = 100 - (100 / (1 + rs))

    # avg_loss == 0: sem perdas na janela -> RSI = 100 (ou 50 se avg_gain também for 0)
    no_losses = avg_loss == 0
    result = result.where(~no_losses, 100.0)
    result = result.where(~(no_losses & (avg_gain == 0)), 50.0)
    return result


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "histogram": histogram})


def atr_contraction_ratio(
    high: pd.Series, low: pd.Series, close: pd.Series,
    short: int = 14, lookback: int = 50, exclude_last: int = 1,
) -> float | None:
    """
    Razão entre o ATR e a média do ATR nas últimas `lookback` candles,
    medida a partir de `exclude_last` candles atrás (por padrão, ignora a
    candle mais recente). < 1 indica volatilidade em contração (squeeze).

    `exclude_last=1` é o padrão porque os Playbooks Wyckoff Spring/
    Upthrust e Compression Breakout usam essa razão para responder "a
    faixa estava comprimida ANTES deste rompimento/sweep?" — incluir a
    própria candle de rompimento (que tem range grande por definição)
    inflaria artificialmente a leitura e mascararia a compressão real que
    a precedeu.
    """
    series = atr(high, low, close, short)
    usable = series.iloc[: len(series) - exclude_last] if exclude_last else series
    if len(usable.dropna()) < lookback:
        return None
    latest = usable.iloc[-1]
    baseline = usable.rolling(lookback).mean().iloc[-1]
    if pd.isna(latest) or pd.isna(baseline) or baseline == 0:
        return None
    return float(latest / baseline)


def compute_indicators(df: pd.DataFrame) -> dict:
    """
    df precisa ter as colunas: open, high, low, close, volume, ordenadas
    da candle mais antiga para a mais recente. Retorna os valores mais
    recentes de cada indicador (última linha), prontos para o JSON
    padronizado do AlphaQuant X.
    """
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"colunas ausentes no DataFrame: {missing}")
    if df.empty:
        raise ValueError("DataFrame de candles vazio")

    close = df["close"]
    macd_df = macd(close)

    def last(series: pd.Series) -> float | None:
        value = series.iloc[-1]
        return None if pd.isna(value) else float(value)

    return {
        "ema20": last(ema(close, 20)),
        "ema50": last(ema(close, 50)),
        "ema100": last(ema(close, 100)),
        "ema200": last(ema(close, 200)),
        "rsi14": last(rsi(close, 14)),
        "atr14": last(atr(df["high"], df["low"], close, 14)),
        "macd": last(macd_df["macd"]),
        "macd_signal": last(macd_df["signal"]),
        "macd_histogram": last(macd_df["histogram"]),
        "volume_avg20": last(df["volume"].rolling(20).mean()),
        "volume_last": float(df["volume"].iloc[-1]),
    }
