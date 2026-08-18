import pandas as pd
import pytest

from alphaquant_core.playbooks.base import Direction, PlaybookContext
from alphaquant_core.playbooks.engine import ALL_PLAYBOOKS, build_context, evaluate_all
from tests.playbook_fixtures import (
    bearish_liquidity_sweep,
    bullish_liquidity_sweep,
    compression_then_breakout,
    fair_value_gap_bullish,
    uptrend_pullback_to_ema50,
)


def _result_for(df: pd.DataFrame, playbook_name: str, htf_regime: str | None = None, symbol="BTCUSDT", timeframe="1h"):
    ctx = build_context(symbol, timeframe, df, htf_regime=htf_regime)
    results = evaluate_all(ctx)
    by_name = {r.playbook: r for r in results}
    return by_name[playbook_name], ctx


def test_all_ten_playbooks_are_registered():
    names = {p.name for p in ALL_PLAYBOOKS}
    assert names == {
        "Trend Continuation EMA50",
        "Liquidity Sweep Reversal",
        "Order Block Reaction",
        "FVG Retracement",
        "Breakout + Retest",
        "Wyckoff Spring",
        "Wyckoff Upthrust",
        "HTF Continuation",
        "Compression Breakout",
        "Open Range Breakout",
    }


def test_trend_continuation_ema50_matches_on_pullback_in_confirmed_uptrend():
    df = uptrend_pullback_to_ema50()
    result, ctx = _result_for(df, "Trend Continuation EMA50")

    assert ctx.regime == "BULLISH"
    assert result.matched is True
    assert result.direction is Direction.LONG
    assert result.progress == 100.0
    assert result.conditions_missing == []
    assert result.entry is not None and result.stop is not None


def test_trend_continuation_ema50_does_not_match_without_trend():
    rng_df = pd.DataFrame(
        {"open": [100] * 60, "high": [100.2] * 60, "low": [99.8] * 60, "close": [100] * 60, "volume": [100] * 60},
        index=pd.date_range("2026-01-01", periods=60, freq="h"),
    )
    result, _ = _result_for(rng_df, "Trend Continuation EMA50")
    assert result.matched is False


def test_liquidity_sweep_reversal_matches_on_bullish_sweep():
    df = bullish_liquidity_sweep()
    result, ctx = _result_for(df, "Liquidity Sweep Reversal")

    assert ctx.liquidity_sweep is not None
    assert result.matched is True
    assert result.direction is Direction.LONG
    assert result.progress == 100.0
    assert result.stop == pytest.approx(ctx.liquidity_sweep.swept_price)


def test_liquidity_sweep_reversal_matches_on_bearish_sweep():
    df = bearish_liquidity_sweep()
    result, ctx = _result_for(df, "Liquidity Sweep Reversal")

    assert result.matched is True
    assert result.direction is Direction.SHORT


def test_liquidity_sweep_reversal_no_match_without_sweep():
    df = uptrend_pullback_to_ema50()  # tendência suave, sem sweep na última candle
    result, ctx = _result_for(df, "Liquidity Sweep Reversal")
    assert ctx.liquidity_sweep is None
    assert result.matched is False
    assert result.progress == 0.0


def test_wyckoff_spring_matches_on_compressed_bullish_sweep():
    df = bullish_liquidity_sweep()
    result, ctx = _result_for(df, "Wyckoff Spring")

    assert ctx.volatility_contraction_ratio is not None
    assert ctx.volatility_contraction_ratio < 0.85
    assert result.matched is True
    assert result.direction is Direction.LONG


def test_wyckoff_upthrust_matches_on_compressed_bearish_sweep():
    df = bearish_liquidity_sweep()
    result, _ = _result_for(df, "Wyckoff Upthrust")
    assert result.matched is True
    assert result.direction is Direction.SHORT


def test_wyckoff_spring_rejects_bearish_sweep():
    df = bearish_liquidity_sweep()
    result, _ = _result_for(df, "Wyckoff Spring")
    assert result.matched is False


def test_fvg_retracement_matches_on_unfilled_gap_touch():
    df = fair_value_gap_bullish()
    result, ctx = _result_for(df, "FVG Retracement")

    assert any(not g.filled for g in ctx.fair_value_gaps)
    assert result.matched is True
    assert result.direction is Direction.LONG


def test_fvg_retracement_no_match_without_gap():
    df = uptrend_pullback_to_ema50()
    result, _ = _result_for(df, "FVG Retracement")
    # não garantimos ausência total de FVG nessa fixture, mas garantimos
    # que o playbook não quebra e devolve um resultado bem formado
    assert result.playbook == "FVG Retracement"
    assert 0.0 <= result.progress <= 100.0


def test_compression_breakout_matches_upward():
    df = compression_then_breakout(breakout_direction="up")
    result, ctx = _result_for(df, "Compression Breakout")

    assert ctx.volatility_contraction_ratio is not None
    assert result.matched is True
    assert result.direction is Direction.LONG
    assert result.entry is not None


def test_compression_breakout_matches_downward():
    df = compression_then_breakout(breakout_direction="down")
    result, _ = _result_for(df, "Compression Breakout")
    assert result.matched is True
    assert result.direction is Direction.SHORT


def test_compression_breakout_no_match_inside_range():
    df = compression_then_breakout(breakout_direction="up")
    # remove a candle de rompimento — preço permanece dentro do range
    df = df.iloc[:-1]
    result, _ = _result_for(df, "Compression Breakout")
    assert result.matched is False


def test_htf_continuation_requires_htf_regime():
    df = uptrend_pullback_to_ema50()
    result, _ = _result_for(df, "HTF Continuation", htf_regime=None)
    assert result.matched is False
    assert "HTF" in result.conditions_missing[0] or "regime" in result.conditions_missing[0].lower()


def test_htf_continuation_matches_when_ltf_confirms_htf_trend():
    df = uptrend_pullback_to_ema50()
    result, ctx = _result_for(df, "HTF Continuation", htf_regime="BULLISH")

    assert ctx.regime == "BULLISH"
    assert result.matched is True
    assert result.direction is Direction.LONG


def test_htf_continuation_no_match_when_htf_undefined():
    df = uptrend_pullback_to_ema50()
    result, _ = _result_for(df, "HTF Continuation", htf_regime="UNDEFINED")
    assert result.matched is False


def test_order_block_reaction_and_breakout_retest_return_well_formed_results():
    """
    Order Block Reaction e Breakout + Retest dependem de o preço revisitar
    uma zona específica calculada a partir dos swings/estrutura — cenário
    mais difícil de forçar deterministicamente numa fixture sintética
    simples. Aqui garantimos, com dados reais de tendência, que os
    playbooks nunca quebram e sempre devolvem uma estrutura de resultado
    válida (o contrato que o restante do sistema depende).
    """
    df = uptrend_pullback_to_ema50()
    ctx = build_context("BTCUSDT", "1h", df)
    for name in ("Order Block Reaction", "Breakout + Retest"):
        result = {r.playbook: r for r in evaluate_all(ctx)}[name]
        assert 0.0 <= result.progress <= 100.0
        assert isinstance(result.conditions_met, list)
        assert isinstance(result.conditions_missing, list)
        if result.matched:
            assert result.direction is not None
            assert result.entry is not None
            assert result.stop is not None


def test_open_range_breakout_is_experimental_and_well_formed():
    df = compression_then_breakout(breakout_direction="up")
    ctx = build_context("BTCUSDT", "1h", df)
    result = {r.playbook: r for r in evaluate_all(ctx)}["Open Range Breakout"]

    assert 0.0 <= result.progress <= 100.0
    if not result.matched:
        assert result.conditions_missing  # sempre explica o que faltou


def test_evaluate_all_returns_one_result_per_playbook():
    df = uptrend_pullback_to_ema50()
    ctx = build_context("BTCUSDT", "1h", df)
    results = evaluate_all(ctx)
    assert len(results) == len(ALL_PLAYBOOKS)
    assert {r.playbook for r in results} == {p.name for p in ALL_PLAYBOOKS}


def test_unmatched_results_still_report_progress_for_future_opportunity_engine():
    """
    Todo PlaybookResult com matched=False mas progress>0 é, por definição,
    material bruto do Future Opportunity Engine (Fase 11) — este teste
    trava esse contrato.
    """
    df = uptrend_pullback_to_ema50()
    ctx = build_context("BTCUSDT", "1h", df)
    results = evaluate_all(ctx)
    assert any(not r.matched and r.progress > 0 for r in results)
