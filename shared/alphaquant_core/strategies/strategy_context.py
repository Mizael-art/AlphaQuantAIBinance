"""
StrategyContext == alphaquant_core.playbooks.base.PlaybookContext.

Reaproveita 100% o MarketContext ja calculado uma unica vez por ciclo
pelo Playbook Engine (indicadores, estrutura, liquidez) em vez de
duplicar esse calculo para as estrategias de prompt. Ver secao 16 da
especificacao: campos ausentes devem ser NULL/UNAVAILABLE, nunca
inventados — `get_field` abaixo segue essa regra.
"""
from __future__ import annotations

from alphaquant_core.engines.structure import StructureEvent, detect_structure_events
from alphaquant_core.playbooks.base import PlaybookContext as StrategyContext

# Campos que o vocabulario de prompt (strategy_parser) sabe ler do
# StrategyContext hoje. Qualquer palavra-chave fora desta lista vira
# UNSUPPORTED_CONDITION em vez de silenciosamente virar outra coisa
# (secao 15 da especificacao).
SUPPORTED_FIELDS: set[str] = {
    "EMA20", "EMA50", "EMA100", "EMA200",
    "RSI14",
    "ATR14",
    "MACD", "MACD_SIGNAL", "MACD_HISTOGRAM",
    "VOLUME", "VOLUME_AVG20",
    "CLOSE", "OPEN", "HIGH", "LOW",
    "REGIME", "HTF_REGIME",
    "BOS", "CHOCH",
    "LIQUIDITY_SWEEP",
    "FVG",
    "ORDER_BLOCK",
    "VOLATILITY_CONTRACTION",
}

# Palavras do vocabulario da secao 14 que a especificacao pede para
# reconhecer mas que o MarketContext atual NAO calcula. Ficam explicitas
# aqui (em vez de simplesmente "nao reconhecido") para que o validator
# devolva uma mensagem clara: "existe no vocabulario, mas ainda sem
# suporte de dado" — e nao "erro de digitacao".
KNOWN_BUT_UNSUPPORTED_FIELDS: set[str] = {
    "ADX", "VWAP", "FUNDING", "OPEN_INTEREST",
    "PREMIUM", "DISCOUNT", "CANDLE_PATTERN", "DIVERGENCE",
    "SUPPORT", "RESISTANCE",  # niveis dinamicos: ainda nao ha um engine dedicado
}


def get_field(ctx: StrategyContext, field: str) -> float | str | bool | None:
    """
    Le um campo do StrategyContext pelo nome do vocabulario do prompt.
    Nunca inventa: devolve None quando o dado nao esta disponivel para
    aquele ativo/timeframe (ex.: indicador com poucos candles).
    """
    field = field.upper()

    if field in ("EMA20", "EMA50", "EMA100", "EMA200", "RSI14", "ATR14",
                 "MACD", "MACD_SIGNAL", "MACD_HISTOGRAM", "VOLUME_AVG20"):
        key = {
            "MACD": "macd", "MACD_SIGNAL": "macd_signal", "MACD_HISTOGRAM": "macd_histogram",
        }.get(field, field.lower())
        return ctx.indicators.get(key)

    if field == "VOLUME":
        return ctx.indicators.get("volume_last")
    if field == "CLOSE":
        return ctx.last_close
    if field == "OPEN":
        return float(ctx.df["open"].iloc[-1])
    if field == "HIGH":
        return float(ctx.df["high"].iloc[-1])
    if field == "LOW":
        return float(ctx.df["low"].iloc[-1])
    if field == "REGIME":
        return ctx.regime
    if field == "HTF_REGIME":
        return ctx.htf_regime
    if field == "VOLATILITY_CONTRACTION":
        return ctx.volatility_contraction_ratio
    if field == "LIQUIDITY_SWEEP":
        return ctx.liquidity_sweep.direction if ctx.liquidity_sweep else None
    if field == "FVG":
        return bool(ctx.fair_value_gaps)
    if field == "ORDER_BLOCK":
        return bool(ctx.order_blocks)
    if field in ("BOS", "CHOCH"):
        events = detect_structure_events(ctx.swings)
        wanted = StructureEvent.BOS if field == "BOS" else StructureEvent.CHOCH
        recent = [e for e in events if e.get("event") == wanted]
        return recent[-1]["regime"] if recent else None

    return None
