import pandas as pd

from alphaquant_core.engines.indicators import atr, compute_indicators, ema, macd, rsi


def _uptrend_df(n: int = 60) -> pd.DataFrame:
    close = pd.Series(range(100, 100 + n), dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": pd.Series([100.0] * n),
        }
    )


def test_ema_reacts_faster_with_shorter_length():
    close = pd.Series([100, 101, 102, 103, 104, 120], dtype=float)
    ema_fast = ema(close, 3).iloc[-1]
    ema_slow = ema(close, 20).iloc[-1]
    # EMA curta reage mais ao salto final que a EMA longa
    assert ema_fast > ema_slow


def test_rsi_is_high_in_pure_uptrend():
    df = _uptrend_df()
    value = rsi(df["close"], 14).iloc[-1]
    assert value > 70  # tendência de alta constante -> RSI elevado


def test_atr_is_positive_and_finite():
    df = _uptrend_df()
    value = atr(df["high"], df["low"], df["close"], 14).iloc[-1]
    assert value > 0


def test_macd_returns_three_columns():
    df = _uptrend_df()
    result = macd(df["close"])
    assert set(result.columns) == {"macd", "signal", "histogram"}
    assert len(result) == len(df)


def test_compute_indicators_full_output():
    df = _uptrend_df(220)  # >= 200 para EMA200 não ser NaN
    result = compute_indicators(df)
    expected_keys = {
        "ema20", "ema50", "ema100", "ema200", "rsi14", "atr14",
        "macd", "macd_signal", "macd_histogram", "volume_avg20", "volume_last",
    }
    assert expected_keys == set(result.keys())
    assert result["ema200"] is not None
    # Em tendência de alta pura, EMAs mais curtas ficam acima das mais longas
    assert result["ema20"] > result["ema50"] > result["ema100"] > result["ema200"]
