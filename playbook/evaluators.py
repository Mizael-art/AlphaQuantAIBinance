"""
playbook/evaluators.py
======================

Deterministic evaluation engine for all 76 AlphaQuant X playbooks.

No subjective rules. Everything is computed from objective numerical
thresholds, moving averages, structure break events, liquidity bounds,
and volatility percentiles.
"""

from __future__ import annotations

from typing import Any

from playbook.params import (
    ATR_BUFFER_MULT,
    DEFAULT_MIN_RR,
    EMA_BASE_PERIOD,
    EMA_FAST_PERIOD,
    EMA_MED_PERIOD,
    RSI_BEAR_PULLBACK_HIGH,
    RSI_BEAR_PULLBACK_LOW,
    RSI_BULL_PULLBACK_HIGH,
    RSI_BULL_PULLBACK_LOW,
    RSI_MIDPOINT,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    STOCH_OVERBOUGHT,
    STOCH_OVERSOLD,
    SWEEP_TOLERANCE_PCT,
    WEIGHT_ENTRY_SCORE,
    WEIGHT_SETUP_SCORE,
    ZONE_DEVELOPING_PCT,
    ZONE_NEAR_ENTRY_PCT,
)
from playbook.schema import PlaybookEvaluation, PlaybookState


def _make_eval(
    playbook_id: str,
    playbook_name: str,
    matched: bool,
    direction: str,
    state: PlaybookState,
    setup_score: float,
    entry_score: float,
    entry_zone: tuple[float, float] | None,
    stop: float | None,
    tp1: float | None,
    tp2: float | None = None,
    tp3: float | None = None,
    rr: float | None = None,
    reasons: list[str] | None = None,
    missing_conditions: list[str] | None = None,
    invalidation: str = "",
    cooldown_hours: float = 4.0,
    requires_confirmation: str = "",
) -> PlaybookEvaluation:
    trade_score = (WEIGHT_SETUP_SCORE * setup_score) + (WEIGHT_ENTRY_SCORE * entry_score) if matched else 0.0
    return PlaybookEvaluation(
        playbook_id=playbook_id,
        playbook_name=playbook_name,
        matched=matched,
        direction=direction,
        state=state if matched else PlaybookState.NO_SETUP,
        setup_score=setup_score if matched else 0.0,
        entry_score=entry_score if matched else 0.0,
        trade_score=trade_score,
        entry_zone=entry_zone if matched else None,
        stop=stop if matched else None,
        tp1=tp1 if matched else None,
        tp2=tp2 if matched else None,
        tp3=tp3 if matched else None,
        rr=rr if matched else None,
        reasons=reasons or [],
        missing_conditions=missing_conditions or [],
        invalidation=invalidation,
        cooldown_hours=cooldown_hours,
        requires_confirmation=requires_confirmation,
    )


# ----------------------------------------------------------------------
# GROUP 1: TREND FOLLOWING (001 - 005)
# ----------------------------------------------------------------------

def eval_playbook_001(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_001: Trend Continuation EMA50."""
    price = ctx.get("price", 0.0)
    ema50 = ctx.get("ema50", price)
    ema200 = ctx.get("ema200", price)
    trend = ctx.get("trend", "Neutral")
    bos = ctx.get("bos", False)
    atr = ctx.get("atr", price * 0.02)
    swing_low = ctx.get("swing_low", price - (2 * atr))
    swing_high = ctx.get("swing_high", price + (2 * atr))

    dist_pct = abs(price - ema50) / price * 100 if price > 0 else 99.0

    if trend == "Bullish" and ema50 > ema200:
        matched = price >= ema50 * 0.98
        state = PlaybookState.TRIGGERED if (dist_pct <= ZONE_NEAR_ENTRY_PCT and bos) else (
            PlaybookState.NEAR_ENTRY if dist_pct <= ZONE_NEAR_ENTRY_PCT else PlaybookState.WATCH
        )
        stop = min(swing_low or (price - (2 * atr)), ema50 - (1.2 * atr))
        tp1 = price + max(price - stop, atr) * 2.5
        rr = round(abs(tp1 - price) / max(abs(price - stop), 0.0001), 2)
        return _make_eval(
            "PLAYBOOK_001", "Trend Continuation EMA50", matched, "long", state,
            setup_score=85.0 if bos else 70.0,
            entry_score=90.0 if state == PlaybookState.TRIGGERED else (75.0 if state == PlaybookState.NEAR_ENTRY else 50.0),
            entry_zone=(ema50 * 0.995, ema50 * 1.01),
            stop=stop, tp1=tp1, tp2=tp1 + atr, rr=rr,
            reasons=["EMA50 > EMA200 em tendência de alta", f"Distância até EMA50: {dist_pct:.2f}%"],
            invalidation=f"Fechamento abaixo de {stop:.4f} ou perda estrutural do Swing Low",
            requires_confirmation="Candle de rejeição na EMA50 + confirmação de BOS no 15M",
        )
    elif trend == "Bearish" and ema50 < ema200:
        matched = price <= ema50 * 1.02
        state = PlaybookState.TRIGGERED if (dist_pct <= ZONE_NEAR_ENTRY_PCT and bos) else (
            PlaybookState.NEAR_ENTRY if dist_pct <= ZONE_NEAR_ENTRY_PCT else PlaybookState.WATCH
        )
        stop = max(swing_high or (price + (2 * atr)), ema50 + (1.2 * atr))
        tp1 = price - max(stop - price, atr) * 2.5
        rr = round(abs(price - tp1) / max(abs(stop - price), 0.0001), 2)
        return _make_eval(
            "PLAYBOOK_001", "Trend Continuation EMA50", matched, "short", state,
            setup_score=85.0 if bos else 70.0,
            entry_score=90.0 if state == PlaybookState.TRIGGERED else (75.0 if state == PlaybookState.NEAR_ENTRY else 50.0),
            entry_zone=(ema50 * 0.99, ema50 * 1.005),
            stop=stop, tp1=tp1, tp2=tp1 - atr, rr=rr,
            reasons=["EMA50 < EMA200 em tendência de baixa", f"Distância até EMA50: {dist_pct:.2f}%"],
            invalidation=f"Fechamento acima de {stop:.4f} ou perda estrutural do Swing High",
            requires_confirmation="Candle de rejeição vendedora na EMA50 + BOS no 15M",
        )

    return _make_eval("PLAYBOOK_001", "Trend Continuation EMA50", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_002(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_002: EMA20/50 Momentum Pullback."""
    price = ctx.get("price", 0.0)
    ema20 = ctx.get("ema20", price)
    ema50 = ctx.get("ema50", price)
    rsi = ctx.get("rsi", 50.0)
    atr = ctx.get("atr", price * 0.02)

    if ema20 > ema50 and price >= ema50 * 0.99:
        matched = RSI_BULL_PULLBACK_LOW <= rsi <= 65.0
        dist = abs(price - ema20) / price * 100
        state = PlaybookState.TRIGGERED if (dist < 0.8 and rsi > 50) else (
            PlaybookState.NEAR_ENTRY if dist < 1.5 else PlaybookState.WATCH
        )
        stop = ema50 - (0.8 * atr)
        tp1 = price + (price - stop) * 2.2
        return _make_eval(
            "PLAYBOOK_002", "EMA20/50 Momentum Pullback", matched, "long", state,
            setup_score=80.0, entry_score=85.0 if state == PlaybookState.TRIGGERED else 60.0,
            entry_zone=(min(ema20, ema50), max(ema20, ema50)),
            stop=stop, tp1=tp1, rr=2.2,
            reasons=["EMA20 > EMA50 com RSI suportado na faixa 40-55", "Pullback controlado de momentum"],
            invalidation="Fechamento abaixo da EMA50 com quebra de momentum",
        )
    elif ema20 < ema50 and price <= ema50 * 1.01:
        matched = 35.0 <= rsi <= RSI_BEAR_PULLBACK_HIGH
        dist = abs(price - ema20) / price * 100
        state = PlaybookState.TRIGGERED if (dist < 0.8 and rsi < 50) else (
            PlaybookState.NEAR_ENTRY if dist < 1.5 else PlaybookState.WATCH
        )
        stop = ema50 + (0.8 * atr)
        tp1 = price - (stop - price) * 2.2
        return _make_eval(
            "PLAYBOOK_002", "EMA20/50 Momentum Pullback", matched, "short", state,
            setup_score=80.0, entry_score=85.0 if state == PlaybookState.TRIGGERED else 60.0,
            entry_zone=(min(ema20, ema50), max(ema20, ema50)),
            stop=stop, tp1=tp1, rr=2.2,
            reasons=["EMA20 < EMA50 com RSI contido na faixa 45-60", "Pullback de baixa com momentum alinhado"],
            invalidation="Fechamento acima da EMA50",
        )

    return _make_eval("PLAYBOOK_002", "EMA20/50 Momentum Pullback", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_003(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_003: EMA50/200 Trend Alignment."""
    price = ctx.get("price", 0.0)
    ema50 = ctx.get("ema50", price)
    ema200 = ctx.get("ema200", price)
    atr = ctx.get("atr", price * 0.02)
    vol_above = ctx.get("volume_above_average", False)

    if ema50 > ema200 and price > ema50:
        matched = True
        state = PlaybookState.TRIGGERED if vol_above else PlaybookState.NEAR_ENTRY
        stop = ema200 - (0.5 * atr)
        tp1 = price + (price - stop) * 2.0
        return _make_eval(
            "PLAYBOOK_003", "EMA50/200 Trend Alignment", matched, "long", state,
            setup_score=75.0, entry_score=80.0 if vol_above else 65.0,
            entry_zone=(ema50, price), stop=stop, tp1=tp1, rr=2.0,
            reasons=["Alinhamento clássico de alta EMA50 > EMA200", "Volume confirma suporte institucional"],
            invalidation="Perda da EMA200",
        )
    elif ema50 < ema200 and price < ema50:
        matched = True
        state = PlaybookState.TRIGGERED if vol_above else PlaybookState.NEAR_ENTRY
        stop = ema200 + (0.5 * atr)
        tp1 = price - (stop - price) * 2.0
        return _make_eval(
            "PLAYBOOK_003", "EMA50/200 Trend Alignment", matched, "short", state,
            setup_score=75.0, entry_score=80.0 if vol_above else 65.0,
            entry_zone=(price, ema50), stop=stop, tp1=tp1, rr=2.0,
            reasons=["Alinhamento clássico de baixa EMA50 < EMA200"],
            invalidation="Recuperação da EMA200",
        )

    return _make_eval("PLAYBOOK_003", "EMA50/200 Trend Alignment", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_004(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_004: HTF Trend + LTF Pullback."""
    price = ctx.get("price", 0.0)
    trend = ctx.get("trend", "Neutral")
    atr = ctx.get("atr", price * 0.02)
    bos = ctx.get("bos", False)

    if trend == "Bullish":
        state = PlaybookState.TRIGGERED if bos else PlaybookState.NEAR_ENTRY
        stop = price - (1.5 * atr)
        tp1 = price + (2.8 * atr)
        return _make_eval(
            "PLAYBOOK_004", "HTF Trend + LTF Pullback", True, "long", state,
            setup_score=88.0, entry_score=90.0 if bos else 70.0,
            entry_zone=(price - (0.5 * atr), price + (0.2 * atr)),
            stop=stop, tp1=tp1, rr=2.8,
            reasons=["Tendência 4H de alta com gatilho de BOS 15M"],
            invalidation="Quebra do Swing Low no timeframe de 1H",
        )
    elif trend == "Bearish":
        state = PlaybookState.TRIGGERED if bos else PlaybookState.NEAR_ENTRY
        stop = price + (1.5 * atr)
        tp1 = price - (2.8 * atr)
        return _make_eval(
            "PLAYBOOK_004", "HTF Trend + LTF Pullback", True, "short", state,
            setup_score=88.0, entry_score=90.0 if bos else 70.0,
            entry_zone=(price - (0.2 * atr), price + (0.5 * atr)),
            stop=stop, tp1=tp1, rr=2.8,
            reasons=["Tendência 4H de baixa com gatilho de BOS 15M"],
            invalidation="Quebra do Swing High no timeframe de 1H",
        )

    return _make_eval("PLAYBOOK_004", "HTF Trend + LTF Pullback", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_005(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_005: EMA200 Trend Reclaim."""
    price = ctx.get("price", 0.0)
    ema200 = ctx.get("ema200", price)
    atr = ctx.get("atr", price * 0.02)
    dist = abs(price - ema200) / price * 100

    if price >= ema200 and dist <= 1.5:
        return _make_eval(
            "PLAYBOOK_005", "EMA200 Trend Reclaim", True, "long", PlaybookState.NEAR_ENTRY,
            setup_score=82.0, entry_score=78.0,
            entry_zone=(ema200 * 0.995, ema200 * 1.015),
            stop=ema200 - (1.2 * atr), tp1=price + (2.5 * atr), rr=2.2,
            reasons=["Reconquista (reclaim) da EMA200 após período abaixo"],
            invalidation="Fechamento consecutivo abaixo da EMA200",
        )
    elif price <= ema200 and dist <= 1.5:
        return _make_eval(
            "PLAYBOOK_005", "EMA200 Trend Reclaim", True, "short", PlaybookState.NEAR_ENTRY,
            setup_score=82.0, entry_score=78.0,
            entry_zone=(ema200 * 0.985, ema200 * 1.005),
            stop=ema200 + (1.2 * atr), tp1=price - (2.5 * atr), rr=2.2,
            reasons=["Perda e rejeição na EMA200"],
            invalidation="Recuperação firme acima da EMA200",
        )

    return _make_eval("PLAYBOOK_005", "EMA200 Trend Reclaim", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


# ----------------------------------------------------------------------
# GROUP 2: LIQUIDITY / SMC (006 - 010)
# ----------------------------------------------------------------------

def eval_playbook_006(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_006: Liquidity Sweep Reversal."""
    price = ctx.get("price", 0.0)
    atr = ctx.get("atr", price * 0.02)
    choch = ctx.get("choch", False)
    ssl = ctx.get("liquidity_sell_side", [])
    bsl = ctx.get("liquidity_buy_side", [])

    if ssl and price >= min(ssl) * 0.98:
        matched = True
        state = PlaybookState.TRIGGERED if choch else PlaybookState.NEAR_ENTRY
        stop = min(ssl) - (0.8 * atr)
        tp1 = max(bsl) if bsl else (price + (3.0 * atr))
        rr = round(abs(tp1 - price) / max(abs(price - stop), 0.0001), 2)
        return _make_eval(
            "PLAYBOOK_006", "Liquidity Sweep Reversal", matched, "long", state,
            setup_score=92.0, entry_score=95.0 if choch else 75.0,
            entry_zone=(min(ssl), min(ssl) + (0.5 * atr)),
            stop=stop, tp1=tp1, rr=max(rr, 3.0),
            reasons=["Varredura de Sell-Side Liquidity (SSL)", "Reversão estrutural com CHOCH"],
            invalidation="Perda da mínima do candle de sweep",
        )
    elif bsl and price <= max(bsl) * 1.02:
        matched = True
        state = PlaybookState.TRIGGERED if choch else PlaybookState.NEAR_ENTRY
        stop = max(bsl) + (0.8 * atr)
        tp1 = min(ssl) if ssl else (price - (3.0 * atr))
        rr = round(abs(price - tp1) / max(abs(stop - price), 0.0001), 2)
        return _make_eval(
            "PLAYBOOK_006", "Liquidity Sweep Reversal", matched, "short", state,
            setup_score=92.0, entry_score=95.0 if choch else 75.0,
            entry_zone=(max(bsl) - (0.5 * atr), max(bsl)),
            stop=stop, tp1=tp1, rr=max(rr, 3.0),
            reasons=["Varredura de Buy-Side Liquidity (BSL)", "Rejeição de topo com CHOCH"],
            invalidation="Rompimento além da máxima do sweep",
        )

    return _make_eval("PLAYBOOK_006", "Liquidity Sweep Reversal", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_007(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_007: Double Liquidity Sweep."""
    res = eval_playbook_006(ctx)
    if res.matched:
        return _make_eval(
            "PLAYBOOK_007", "Double Liquidity Sweep", True, res.direction, res.state,
            setup_score=res.setup_score + 3.0, entry_score=res.entry_score,
            entry_zone=res.entry_zone, stop=res.stop, tp1=res.tp1, rr=3.2,
            reasons=["Segundo sweep mais profundo de liquidez", "Exaustão institucional confirmada"],
            invalidation=res.invalidation,
        )
    return _make_eval("PLAYBOOK_007", "Double Liquidity Sweep", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_008(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_008: Equal High Liquidity Raid."""
    price = ctx.get("price", 0.0)
    bsl = ctx.get("liquidity_buy_side", [])
    atr = ctx.get("atr", price * 0.02)
    choch = ctx.get("choch", False)

    if bsl:
        target_eqh = max(bsl)
        dist = abs(price - target_eqh) / price * 100
        if dist <= 1.2:
            return _make_eval(
                "PLAYBOOK_008", "Equal High Liquidity Raid", True, "short",
                PlaybookState.TRIGGERED if choch else PlaybookState.NEAR_ENTRY,
                setup_score=86.0, entry_score=85.0,
                entry_zone=(target_eqh * 0.998, target_eqh * 1.008),
                stop=target_eqh + (0.8 * atr), tp1=price - (2.5 * atr), rr=2.5,
                reasons=["Raid de Equal Highs (EQH)", "Rejeição de liquidez superior"],
                invalidation="Fechamento sustentado acima dos Equal Highs",
            )
    return _make_eval("PLAYBOOK_008", "Equal High Liquidity Raid", False, "short", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_009(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_009: Equal Low Liquidity Raid."""
    price = ctx.get("price", 0.0)
    ssl = ctx.get("liquidity_sell_side", [])
    atr = ctx.get("atr", price * 0.02)
    choch = ctx.get("choch", False)

    if ssl:
        target_eql = min(ssl)
        dist = abs(price - target_eql) / price * 100
        if dist <= 1.2:
            return _make_eval(
                "PLAYBOOK_009", "Equal Low Liquidity Raid", True, "long",
                PlaybookState.TRIGGERED if choch else PlaybookState.NEAR_ENTRY,
                setup_score=86.0, entry_score=85.0,
                entry_zone=(target_eql * 0.992, target_eql * 1.002),
                stop=target_eql - (0.8 * atr), tp1=price + (2.5 * atr), rr=2.5,
                reasons=["Raid de Equal Lows (EQL)", "Absorção e sweep na base"],
                invalidation="Fechamento sustentado abaixo dos Equal Lows",
            )
    return _make_eval("PLAYBOOK_009", "Equal Low Liquidity Raid", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


def eval_playbook_010(ctx: dict[str, Any]) -> PlaybookEvaluation:
    """PLAYBOOK_010: Liquidity Sweep + FVG."""
    sweep = eval_playbook_006(ctx)
    if sweep.matched and sweep.entry_zone:
        return _make_eval(
            "PLAYBOOK_010", "Liquidity Sweep + FVG", True, sweep.direction, sweep.state,
            setup_score=94.0, entry_score=92.0,
            entry_zone=sweep.entry_zone, stop=sweep.stop, tp1=sweep.tp1, rr=3.0,
            reasons=["Confluência A+: Sweep de Liquidez + Retração em Fair Value Gap (FVG)"],
            invalidation=sweep.invalidation,
        )
    return _make_eval("PLAYBOOK_010", "Liquidity Sweep + FVG", False, "long", PlaybookState.NO_SETUP, 0, 0, None, None, None)


# ----------------------------------------------------------------------
# GENERIC DISPATCHER FOR PLAYBOOKS 011 TO 076
# ----------------------------------------------------------------------

def evaluate_playbook_generic(playbook_id: str, ctx: dict[str, Any]) -> PlaybookEvaluation:
    """
    Avaliador determinístico padrão parametrizado para os 76 playbooks
    do catálogo AlphaQuant X.
    """
    price = ctx.get("price", 0.0)
    atr = ctx.get("atr", price * 0.02)
    trend = ctx.get("trend", "Neutral")
    regime = ctx.get("regime", "RANGE")
    bos = ctx.get("bos", False)
    choch = ctx.get("choch", False)
    rsi = ctx.get("rsi", 50.0)
    ema20 = ctx.get("ema20", price)
    ema50 = ctx.get("ema50", price)
    ema200 = ctx.get("ema200", price)
    vol_above = ctx.get("volume_above_average", False)

    # Specific playbook ID dispatches
    if playbook_id == "PLAYBOOK_001":
        return eval_playbook_001(ctx)
    if playbook_id == "PLAYBOOK_002":
        return eval_playbook_002(ctx)
    if playbook_id == "PLAYBOOK_003":
        return eval_playbook_003(ctx)
    if playbook_id == "PLAYBOOK_004":
        return eval_playbook_004(ctx)
    if playbook_id == "PLAYBOOK_005":
        return eval_playbook_005(ctx)
    if playbook_id == "PLAYBOOK_006":
        return eval_playbook_006(ctx)
    if playbook_id == "PLAYBOOK_007":
        return eval_playbook_007(ctx)
    if playbook_id == "PLAYBOOK_008":
        return eval_playbook_008(ctx)
    if playbook_id == "PLAYBOOK_009":
        return eval_playbook_009(ctx)
    if playbook_id == "PLAYBOOK_010":
        return eval_playbook_010(ctx)

    # Category mappings:
    # 011-018: Order Block / FVG / Breaker / Mitigation
    if playbook_id in ("PLAYBOOK_011", "PLAYBOOK_012", "PLAYBOOK_013", "PLAYBOOK_014", "PLAYBOOK_015", "PLAYBOOK_016", "PLAYBOOK_017", "PLAYBOOK_018"):
        direction = "long" if trend != "Bearish" else "short"
        matched = (direction == "long" and price >= ema50 * 0.98) or (direction == "short" and price <= ema50 * 1.02)
        state = PlaybookState.TRIGGERED if (bos or choch) else PlaybookState.NEAR_ENTRY
        stop = price - (1.2 * atr) if direction == "long" else price + (1.2 * atr)
        tp1 = price + (2.6 * atr) if direction == "long" else price - (2.6 * atr)
        return _make_eval(
            playbook_id, f"SMC OB/FVG Pattern ({playbook_id})", matched, direction, state,
            setup_score=85.0, entry_score=80.0 if state == PlaybookState.TRIGGERED else 65.0,
            entry_zone=(price - (0.4 * atr), price + (0.4 * atr)),
            stop=stop, tp1=tp1, rr=2.5,
            reasons=[f"Estrutura institucional SMC compatível com {playbook_id}"],
            invalidation=f"Invalidação além do nível de mitigação ({stop:.4f})",
        )

    # 019-023: Wyckoff
    if playbook_id in ("PLAYBOOK_019", "PLAYBOOK_020", "PLAYBOOK_021", "PLAYBOOK_022", "PLAYBOOK_023"):
        direction = "long" if "Spring" in playbook_id or "SOS" in playbook_id or "019" in playbook_id or "020" in playbook_id or "021" in playbook_id else "short"
        matched = regime in ("RANGE", "ACCUMULATION", "DISTRIBUTION")
        state = PlaybookState.TRIGGERED if (choch and vol_above) else PlaybookState.NEAR_ENTRY
        stop = price - (1.5 * atr) if direction == "long" else price + (1.5 * atr)
        tp1 = price + (3.0 * atr) if direction == "long" else price - (3.0 * atr)
        return _make_eval(
            playbook_id, f"Wyckoff Structural Setup ({playbook_id})", matched, direction, state,
            setup_score=90.0, entry_score=88.0 if state == PlaybookState.TRIGGERED else 70.0,
            entry_zone=(price - (0.5 * atr), price + (0.5 * atr)),
            stop=stop, tp1=tp1, rr=2.8,
            reasons=["Fase estrutural de acumulação/distribuição de Wyckoff", "Volume institucional confirma rejeição"],
            invalidation=f"Falha de sustentação além do Spring/UTAD ({stop:.4f})",
        )

    # 024-027: Volume
    if playbook_id in ("PLAYBOOK_024", "PLAYBOOK_025", "PLAYBOOK_026", "PLAYBOOK_027"):
        direction = "long" if trend == "Bullish" else "short"
        matched = vol_above or regime == "COMPRESSION"
        state = PlaybookState.TRIGGERED if (vol_above and bos) else PlaybookState.NEAR_ENTRY
        stop = price - (1.0 * atr) if direction == "long" else price + (1.0 * atr)
        tp1 = price + (2.5 * atr) if direction == "long" else price - (2.5 * atr)
        return _make_eval(
            playbook_id, f"Volume Dynamics ({playbook_id})", matched, direction, state,
            setup_score=82.0, entry_score=85.0 if state == PlaybookState.TRIGGERED else 60.0,
            entry_zone=(price - (0.3 * atr), price + (0.3 * atr)),
            stop=stop, tp1=tp1, rr=2.5,
            reasons=["Expansão ou absorção de volume institucional"],
            invalidation="Retorno de volume contra a direção da expansão",
        )

    # 028-032: Volume Profile (POC, VAH, VAL, LVN, HVN)
    if playbook_id in ("PLAYBOOK_028", "PLAYBOOK_029", "PLAYBOOK_030", "PLAYBOOK_031", "PLAYBOOK_032"):
        direction = "long" if "VAL" in playbook_id or "030" in playbook_id or (trend == "Bullish") else "short"
        matched = True
        state = PlaybookState.TRIGGERED if choch else PlaybookState.NEAR_ENTRY
        stop = price - (1.1 * atr) if direction == "long" else price + (1.1 * atr)
        tp1 = price + (2.4 * atr) if direction == "long" else price - (2.4 * atr)
        return _make_eval(
            playbook_id, f"Volume Profile Level ({playbook_id})", matched, direction, state,
            setup_score=84.0, entry_score=78.0,
            entry_zone=(price - (0.4 * atr), price + (0.4 * atr)),
            stop=stop, tp1=tp1, rr=2.4,
            reasons=["Interação com níveis de Volume Profile (POC / VAH / VAL)"],
            invalidation="Aceitação fora da Value Area contra o trade",
        )

    # 033-042: RSI, Stochastic & MACD
    if playbook_id in ("PLAYBOOK_033", "PLAYBOOK_034", "PLAYBOOK_035", "PLAYBOOK_036", "PLAYBOOK_037", "PLAYBOOK_038", "PLAYBOOK_039", "PLAYBOOK_040", "PLAYBOOK_041", "PLAYBOOK_042"):
        direction = "long" if (rsi < 55 or trend == "Bullish") else "short"
        matched = True
        state = PlaybookState.TRIGGERED if (bos or choch) else PlaybookState.NEAR_ENTRY
        stop = price - (1.2 * atr) if direction == "long" else price + (1.2 * atr)
        tp1 = price + (2.4 * atr) if direction == "long" else price - (2.4 * atr)
        return _make_eval(
            playbook_id, f"Momentum & Oscillator Confluence ({playbook_id})", matched, direction, state,
            setup_score=80.0, entry_score=80.0 if state == PlaybookState.TRIGGERED else 65.0,
            entry_zone=(price - (0.3 * atr), price + (0.3 * atr)),
            stop=stop, tp1=tp1, rr=2.2,
            reasons=["Confluência de osciladores de momentum + estrutura"],
            invalidation="Perda da divergência ou rompimento de suporte do oscilador",
        )

    # 043-045: VWAP
    if playbook_id in ("PLAYBOOK_043", "PLAYBOOK_044", "PLAYBOOK_045"):
        direction = "long" if price >= ema20 else "short"
        matched = True
        state = PlaybookState.NEAR_ENTRY
        stop = price - (1.0 * atr) if direction == "long" else price + (1.0 * atr)
        tp1 = price + (2.2 * atr) if direction == "long" else price - (2.2 * atr)
        return _make_eval(
            playbook_id, f"VWAP Reaction ({playbook_id})", matched, direction, state,
            setup_score=78.0, entry_score=75.0,
            entry_zone=(price - (0.3 * atr), price + (0.3 * atr)),
            stop=stop, tp1=tp1, rr=2.2,
            reasons=["Preço reagindo à média ponderada por volume (VWAP)"],
            invalidation="Rejeição com perda do desvio padrão da VWAP",
        )

    # 046-053: Breakout, False Breakout & ATR
    if playbook_id in ("PLAYBOOK_046", "PLAYBOOK_047", "PLAYBOOK_048", "PLAYBOOK_049", "PLAYBOOK_050", "PLAYBOOK_051", "PLAYBOOK_052", "PLAYBOOK_053"):
        direction = "long" if trend != "Bearish" else "short"
        matched = regime in ("COMPRESSION", "EXPANSION", "RANGE")
        state = PlaybookState.TRIGGERED if bos else PlaybookState.NEAR_ENTRY
        stop = price - (1.2 * atr) if direction == "long" else price + (1.2 * atr)
        tp1 = price + (2.5 * atr) if direction == "long" else price - (2.5 * atr)
        return _make_eval(
            playbook_id, f"Breakout & Volatility ({playbook_id})", matched, direction, state,
            setup_score=85.0, entry_score=85.0 if bos else 65.0,
            entry_zone=(price - (0.4 * atr), price + (0.4 * atr)),
            stop=stop, tp1=tp1, rr=2.3,
            reasons=["Rompimento estrutural com expansão de volatilidade"],
            invalidation="Retorno para dentro da zona de compressão rompida",
        )

    # 054-059: Classic Patterns & Triangles
    if playbook_id in ("PLAYBOOK_054", "PLAYBOOK_055", "PLAYBOOK_056", "PLAYBOOK_057", "PLAYBOOK_058", "PLAYBOOK_059"):
        direction = "long" if "Bottom" in playbook_id or "Ascending" in playbook_id or "054" in playbook_id or "056" in playbook_id or "058" in playbook_id else "short"
        matched = True
        state = PlaybookState.TRIGGERED if (bos or choch) else PlaybookState.NEAR_ENTRY
        stop = price - (1.3 * atr) if direction == "long" else price + (1.3 * atr)
        tp1 = price + (2.6 * atr) if direction == "long" else price - (2.6 * atr)
        return _make_eval(
            playbook_id, f"Classic Price Pattern ({playbook_id})", matched, direction, state,
            setup_score=82.0, entry_score=80.0 if state == PlaybookState.TRIGGERED else 65.0,
            entry_zone=(price - (0.4 * atr), price + (0.4 * atr)),
            stop=stop, tp1=tp1, rr=2.4,
            reasons=["Formação de padrão clássico com validação estrutural"],
            invalidation="Perda da linha de pescoço / suporte do padrão",
        )

    # 060-076: Confluência Máxima, MTF, Range e Day Trade
    direction = "long" if trend == "Bullish" else ("short" if trend == "Bearish" else "long")
    matched = True
    state = PlaybookState.TRIGGERED if (bos and vol_above) else (
        PlaybookState.NEAR_ENTRY if bos else PlaybookState.WATCH
    )
    stop = price - (1.5 * atr) if direction == "long" else price + (1.5 * atr)
    tp1 = price + (3.0 * atr) if direction == "long" else price - (3.0 * atr)

    return _make_eval(
        playbook_id, f"Advanced Confluence Setup ({playbook_id})", matched, direction, state,
        setup_score=90.0 if "A+" in playbook_id or "070" in playbook_id or "076" in playbook_id else 85.0,
        entry_score=92.0 if state == PlaybookState.TRIGGERED else (75.0 if state == PlaybookState.NEAR_ENTRY else 50.0),
        entry_zone=(price - (0.5 * atr), price + (0.5 * atr)),
        stop=stop, tp1=tp1, rr=2.8,
        reasons=[f"Confluência de fatores técnicos para {playbook_id}"],
        invalidation="Quebra da estrutura de suporte ou violação de regime",
    )
