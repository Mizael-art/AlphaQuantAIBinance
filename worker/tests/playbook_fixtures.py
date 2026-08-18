"""
Geradores de candles sintéticas usados pelos testes de playbooks — cada
função constrói um DataFrame OHLCV desenhado deliberadamente para acionar
(ou não) um padrão específico.
"""
from __future__ import annotations

import random

import pandas as pd


def make_df(rows: list[dict], start="2026-01-01", freq="1h") -> pd.DataFrame:
    index = pd.date_range(start, periods=len(rows), freq=freq)
    df = pd.DataFrame(rows, index=index)
    return df[["open", "high", "low", "close", "volume"]]


def uptrend_pullback_to_ema50(n: int = 220, pullback_pct: float = 0.005) -> pd.DataFrame:
    """
    Zigue-zague de alta com HH/HL genuínos (regime BULLISH confirmado) e
    um recuo final mais profundo que traz o preço para perto da EMA50 —
    cenário alvo do Trend Continuation EMA50 (e, com htf_regime setado
    manualmente no teste, também do HTF Continuation).
    """
    rng = random.Random(3)
    rows: list[dict] = []
    price = 100.0

    cycles = 8
    rally_bars, rally_gain = 6, 10.0
    pullback_bars, pullback_loss = 4, 5.0

    for c in range(cycles):
        step_up = rally_gain / rally_bars
        for _ in range(rally_bars):
            o = price
            price += step_up
            jitter = rng.uniform(0.05, 0.25)
            rows.append({
                "open": o, "high": max(o, price) + jitter, "low": min(o, price) - jitter * 0.3,
                "close": price, "volume": rng.uniform(150, 250),
            })
        if c < cycles - 1:
            step_down = pullback_loss / pullback_bars
            for _ in range(pullback_bars):
                o = price
                price -= step_down
                jitter = rng.uniform(0.05, 0.25)
                rows.append({
                    "open": o, "high": max(o, price) + jitter * 0.3, "low": min(o, price) - jitter,
                    "close": price, "volume": rng.uniform(150, 250),
                })

    # pullback final mais profundo, aproximando o preço da EMA50, sem
    # confirmar ainda um novo swing (candle mais recente = "em formação")
    final_bars, final_loss = 6, 13.5
    step_down = final_loss / final_bars
    for _ in range(final_bars):
        o = price
        price -= step_down
        jitter = rng.uniform(0.05, 0.25)
        rows.append({
            "open": o, "high": max(o, price) + jitter * 0.3, "low": min(o, price) - jitter,
            "close": price, "volume": rng.uniform(150, 250),
        })

    return make_df(rows)


def bullish_liquidity_sweep(n_wide: int = 40, n_tight: int = 40) -> pd.DataFrame:
    """
    Volatilidade larga seguida de uma faixa comprimida (squeeze real —
    ATR recente bem abaixo da média do período), depois uma varredura de
    liquidez abaixo do suporte da faixa com fechamento de reclamação
    moderado (RSI não fica esticado) — cenário alvo do Liquidity Sweep
    Reversal e do Wyckoff Spring.
    """
    rng = random.Random(11)
    rows: list[dict] = []
    price = 100.0

    for _ in range(n_wide):
        price += rng.uniform(-0.35, 0.35)
        rows.append({
            "open": price, "high": price + 0.5, "low": price - 0.5,
            "close": price + rng.uniform(-0.2, 0.2), "volume": rng.uniform(150, 250),
        })
    for _ in range(n_tight):
        price += rng.uniform(-0.05, 0.05)
        rows.append({
            "open": price, "high": price + 0.08, "low": price - 0.08,
            "close": price + rng.uniform(-0.03, 0.03), "volume": rng.uniform(150, 250),
        })

    # candle que forma o swing low do suporte da faixa
    rows.append({"open": price + 0.05, "high": price + 0.1, "low": price - 1.0, "close": price + 0.1, "volume": 200})
    swept = price - 1.0
    # candle de confirmação intermediária
    rows.append({"open": price + 0.1, "high": price + 0.15, "low": price + 0.05, "close": price + 0.12, "volume": 200})
    # candle de sweep: perfura o suporte e fecha de volta acima, sem se esticar demais
    last_close = price + 0.35
    rows.append({
        "open": price + 0.12, "high": price + 0.4, "low": swept - 0.3,
        "close": last_close, "volume": 500,
    })

    return make_df(rows)


def bearish_liquidity_sweep(n_wide: int = 40, n_tight: int = 40) -> pd.DataFrame:
    """Espelho de bullish_liquidity_sweep — sweep para cima com rejeição."""
    rng = random.Random(13)
    rows: list[dict] = []
    price = 100.0

    for _ in range(n_wide):
        price += rng.uniform(-0.35, 0.35)
        rows.append({
            "open": price, "high": price + 0.5, "low": price - 0.5,
            "close": price + rng.uniform(-0.2, 0.2), "volume": rng.uniform(150, 250),
        })
    for _ in range(n_tight):
        price += rng.uniform(-0.05, 0.05)
        rows.append({
            "open": price, "high": price + 0.08, "low": price - 0.08,
            "close": price + rng.uniform(-0.03, 0.03), "volume": rng.uniform(150, 250),
        })

    rows.append({"open": price - 0.05, "high": price + 1.0, "low": price - 0.1, "close": price - 0.1, "volume": 200})
    swept = price + 1.0
    rows.append({"open": price - 0.1, "high": price - 0.05, "low": price - 0.15, "close": price - 0.12, "volume": 200})
    last_close = price - 0.35
    rows.append({
        "open": price - 0.12, "high": swept + 0.3, "low": price - 0.4,
        "close": last_close, "volume": 500,
    })

    return make_df(rows)


def fair_value_gap_bullish(n: int = 60) -> pd.DataFrame:
    """
    Base lateral, um candle de impulso que deixa um FVG de alta claro, e
    um recuo controlado que traz o preço de volta para dentro do gap
    (ainda não preenchido) — cenário alvo do FVG Retracement.
    """
    rng = random.Random(5)
    rows: list[dict] = []
    price = 100.0
    for _ in range(n):
        price += rng.uniform(-0.1, 0.15)
        rows.append({"open": price, "high": price + 0.2, "low": price - 0.2, "close": price, "volume": 200})

    rows.append({"open": price, "high": price + 0.3, "low": price - 0.2, "close": price + 0.2, "volume": 200})
    a_high = rows[-1]["high"]

    price2 = price + 3.0
    rows.append({"open": price + 0.2, "high": price2 + 0.3, "low": price + 0.1, "close": price2, "volume": 500})

    price3 = price2 + 0.5
    c_low = a_high + 0.5
    rows.append({"open": price2 + 0.1, "high": price3 + 0.2, "low": c_low, "close": price3, "volume": 300})

    gap_mid = (a_high + c_low) / 2
    price4 = price3
    for _ in range(4):
        price4 -= (price3 - gap_mid) / 4
        rows.append({"open": price4 + 0.1, "high": price4 + 0.2, "low": price4 - 0.1, "close": price4, "volume": 200})

    return make_df(rows)


def compression_then_breakout(n_wide: int = 40, n_range: int = 40, breakout_direction: str = "up") -> pd.DataFrame:
    """
    Volatilidade normal seguida de uma faixa comprimida de verdade (ATR
    recente bem abaixo da média do período) e então um rompimento com
    volume acima da média — cenário alvo do Compression Breakout (e,
    ajustando a data do índice, também do Open Range Breakout).
    """
    rng = random.Random(17)
    rows: list[dict] = []
    price = 100.0
    for _ in range(n_wide):
        price += rng.uniform(-0.3, 0.3)
        rows.append({
            "open": price, "high": price + 0.4, "low": price - 0.4,
            "close": price + rng.uniform(-0.15, 0.15), "volume": rng.uniform(150, 200),
        })
    for _ in range(n_range):
        price += rng.uniform(-0.05, 0.05)
        rows.append({
            "open": price, "high": price + 0.08, "low": price - 0.08,
            "close": price + rng.uniform(-0.03, 0.03), "volume": rng.uniform(150, 200),
        })

    move = 2.5 if breakout_direction == "up" else -2.5
    breakout_price = price + move
    rows.append({
        "open": price, "high": max(price, breakout_price) + 0.2, "low": min(price, breakout_price) - 0.1,
        "close": breakout_price, "volume": 600,  # bem acima da média de ~150-200
    })

    return make_df(rows)
