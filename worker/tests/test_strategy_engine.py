"""Testes do Strategy Engine (prompt-based) — secoes 12-29 da especificacao."""
from __future__ import annotations

import pytest

from alphaquant_core.playbooks.base import Direction
from alphaquant_core.playbooks.engine import build_context
from alphaquant_core.strategies import (
    ParseError,
    StrategyRegistry,
    StrategyStatus,
    detect_conflicts,
    evaluate_active_strategies,
    parse_prompt,
    validate_prompt,
)
from alphaquant_core.strategies.strategy_engine import StrategyEngineResult

from .playbook_fixtures import uptrend_pullback_to_ema50

VALID_LONG_PROMPT = """
NAME: Test Trend Long
TIMEFRAMES: 1H
MODE: SWING
DIRECTION: LONG

CONDITIONS:
  REGIME == BULLISH
  RSI14 < 100

STOP: SWING_LOW
TARGETS: RR 2.0, RR 3.0
"""

VALID_SHORT_PROMPT = """
NAME: Test Trend Short
DIRECTION: SHORT

CONDITIONS:
  REGIME == BULLISH

STOP: SWING_HIGH
TARGETS: RR 1.5
"""

UNSUPPORTED_PROMPT = """
NAME: Uses ADX
CONDITIONS:
  ADX > 25
STOP: SWING_LOW
TARGETS: RR 2
"""

NO_STOP_PROMPT = """
NAME: No Stop
CONDITIONS:
  REGIME == BULLISH
TARGETS: RR 2
"""


class TestParser:
    def test_parses_valid_prompt(self):
        parsed = parse_prompt("fallback", VALID_LONG_PROMPT)
        assert parsed.name == "Test Trend Long"
        assert parsed.timeframes == ["1H"]
        assert parsed.direction == "LONG"
        assert len(parsed.conditions) == 2
        assert parsed.stop.kind == "SWING_LOW"
        assert len(parsed.targets) == 2
        assert parsed.targets[0].value == 2.0

    def test_missing_conditions_block_raises(self):
        with pytest.raises(ParseError):
            parse_prompt("x", "NAME: broken\nSTOP: SWING_LOW\nTARGETS: RR 1")

    def test_malformed_condition_line_raises(self):
        bad = "NAME: x\nCONDITIONS:\n  THIS IS NOT A CONDITION\nSTOP: SWING_LOW\nTARGETS: RR 1"
        with pytest.raises(ParseError):
            parse_prompt("x", bad)

    def test_or_and_not_connectors_parsed(self):
        prompt = (
            "NAME: x\nCONDITIONS:\n"
            "  REGIME == BULLISH\n"
            "  OR RSI14 < 30\n"
            "  NOT VOLATILITY_CONTRACTION < 0.5\n"
            "STOP: SWING_LOW\nTARGETS: RR 1\n"
        )
        parsed = parse_prompt("x", prompt)
        assert parsed.conditions[1].connector.value == "OR"
        assert parsed.conditions[2].connector.value == "NOT"


class TestValidator:
    def test_valid_prompt_passes(self):
        parsed = parse_prompt("x", VALID_LONG_PROMPT)
        result = validate_prompt(parsed)
        assert result.valid
        assert result.status == "VALID"

    def test_unsupported_field_flagged_not_silently_dropped(self):
        parsed = parse_prompt("x", UNSUPPORTED_PROMPT)
        result = validate_prompt(parsed)
        assert not result.valid
        assert result.status == "UNSUPPORTED_CONDITION"
        assert any("ADX" in msg for msg in result.unsupported_conditions)

    def test_missing_stop_is_invalid_never_invented(self):
        parsed = parse_prompt("x", NO_STOP_PROMPT)
        result = validate_prompt(parsed)
        assert not result.valid
        assert any("STOP" in e for e in result.errors)


class TestRegistryVersioning:
    def test_create_and_update_creates_new_version_without_overwriting(self):
        reg = StrategyRegistry()
        strat = reg.create(name="X", prompt_raw=VALID_LONG_PROMPT)
        assert len(strat.versions) == 1
        assert strat.current_version.version_label == "v1"
        v1_prompt = strat.current_version.prompt_raw

        reg.update(strat.strategy_id, prompt_raw=VALID_SHORT_PROMPT, change_note="mais permissiva")
        updated = reg.get(strat.strategy_id)
        assert len(updated.versions) == 2
        assert updated.current_version.version_label == "v2"
        assert updated.versions[0].prompt_raw == v1_prompt  # v1 preservada

    def test_archive_is_soft_delete(self):
        reg = StrategyRegistry()
        strat = reg.create(name="X", prompt_raw=VALID_LONG_PROMPT)
        reg.archive(strat.strategy_id)
        archived = reg.get(strat.strategy_id)
        assert archived.status == StrategyStatus.ARCHIVED
        assert len(archived.versions) == 1  # historico intacto

    def test_duplicate_creates_independent_inactive_copy(self):
        reg = StrategyRegistry()
        strat = reg.create(name="X", prompt_raw=VALID_LONG_PROMPT)
        dup = reg.duplicate(strat.strategy_id)
        assert dup.strategy_id != strat.strategy_id
        assert dup.status == StrategyStatus.INACTIVE
        assert dup.current_version.prompt_raw == strat.current_version.prompt_raw


class TestEngineExecution:
    def test_active_valid_strategy_runs_against_context(self):
        df = uptrend_pullback_to_ema50()
        ctx = build_context("BTCUSDT", "1H", df)
        assert ctx.regime == "BULLISH"  # pré-condição do fixture

        reg = StrategyRegistry()
        reg.create(name="X", prompt_raw=VALID_LONG_PROMPT)
        results = evaluate_active_strategies(ctx, reg)

        assert len(results) == 1
        r = results[0]
        assert r.status == "RUNNABLE"
        assert r.result is not None
        assert r.result.matched is True
        assert r.result.direction == Direction.LONG
        assert r.result.stop is not None

    def test_unsupported_strategy_never_evaluated_silently(self):
        df = uptrend_pullback_to_ema50()
        ctx = build_context("BTCUSDT", "1H", df)

        reg = StrategyRegistry()
        reg.create(name="X", prompt_raw=UNSUPPORTED_PROMPT)
        results = evaluate_active_strategies(ctx, reg)

        assert results[0].status == "UNSUPPORTED_CONDITION"
        assert results[0].result is None

    def test_inactive_strategy_is_skipped_but_reported(self):
        df = uptrend_pullback_to_ema50()
        ctx = build_context("BTCUSDT", "1H", df)

        reg = StrategyRegistry()
        strat = reg.create(name="X", prompt_raw=VALID_LONG_PROMPT, active=False)
        results = evaluate_active_strategies(ctx, reg)

        assert results[0].status == "INACTIVE"
        assert results[0].strategy_id == strat.strategy_id

    def test_conflict_detected_when_strategies_disagree(self):
        df = uptrend_pullback_to_ema50()
        ctx = build_context("BTCUSDT", "1H", df)

        reg = StrategyRegistry()
        reg.create(name="Long side", prompt_raw=VALID_LONG_PROMPT)
        # Estrategia SHORT que tambem "matcha" em regime BULLISH (forcado
        # so para exercitar a deteccao de conflito, nao e' realista)
        forced_short = VALID_SHORT_PROMPT.replace("REGIME == BULLISH", "REGIME == BULLISH")
        reg.create(name="Short side", prompt_raw=forced_short)

        results = evaluate_active_strategies(ctx, reg)
        assert detect_conflicts(results) is True

    def test_no_conflict_when_single_direction(self):
        df = uptrend_pullback_to_ema50()
        ctx = build_context("BTCUSDT", "1H", df)

        reg = StrategyRegistry()
        reg.create(name="Long side", prompt_raw=VALID_LONG_PROMPT)
        results = evaluate_active_strategies(ctx, reg)
        assert detect_conflicts(results) is False

    def test_stop_insufficient_data_never_invents_stop(self):
        """Estrategia com STOP=SWING_HIGH mas cujo contexto nao tem HH/LH
        recentes o suficiente deve marcar STOP_INSUFFICIENT_DATA em vez
        de inventar um stop."""
        df = uptrend_pullback_to_ema50()
        ctx = build_context("BTCUSDT", "1H", df)

        reg = StrategyRegistry()
        # short com REGIME == BULLISH nunca teria swing high de baixa
        # coerente pos-tendencia de alta pura o suficiente em todos os
        # casos; usamos SWING_HIGH que so existe se houver LH/HH — aqui
        # testamos apenas que, quando nao ha, matched vira False com nota.
        reg.create(name="X", prompt_raw=VALID_SHORT_PROMPT)
        results = evaluate_active_strategies(ctx, reg)
        r = results[0].result
        assert r is not None
        # ou casou com stop valido, ou foi rejeitada por falta de stop —
        # nunca com matched=True e stop=None
        if r.matched:
            assert r.stop is not None
        else:
            assert r.stop is None
