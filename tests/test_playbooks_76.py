"""
tests/test_playbooks_76.py
==========================

Test suite validating the 76-Playbook Strategy Factory, deterministic
evaluators, and strategy confluence engine.
"""

from __future__ import annotations

import pytest

from discovery.confluence import consolidate_evaluations
from playbook.library import PLAYBOOK_CATALOG, compatible_playbooks, get_all_playbooks, get_playbook
from playbook.schema import Backtestability, PlaybookState, PlaybookTier
from regime.detector import RANGE, TRENDING_DOWN, TRENDING_UP


def test_catalog_has_76_playbooks():
    all_playbooks = get_all_playbooks()
    assert len(all_playbooks) == 76, f"Esperado 76 playbooks, obtido {len(all_playbooks)}"


def test_every_playbook_has_valid_fields():
    for p in PLAYBOOK_CATALOG:
        assert p.id.startswith("PLAYBOOK_"), f"{p.id} deve iniciar com PLAYBOOK_"
        assert p.name != "", f"{p.id} sem nome"
        assert p.category != "", f"{p.id} sem categoria"
        assert p.style in ("day_trade", "intraday", "swing"), f"{p.id} estilo inválido: {p.style}"
        assert p.tier in (PlaybookTier.TIER_S, PlaybookTier.TIER_A_PLUS, PlaybookTier.TIER_A, PlaybookTier.TIER_B, PlaybookTier.TIER_RESEARCH)
        assert p.min_rr >= 1.8, f"{p.id} min_rr menor que 1.8: {p.min_rr}"
        assert p.min_score >= 50, f"{p.id} min_score menor que 50: {p.min_score}"
        assert p.compatible_regimes, f"{p.id} deve ter regimes compatíveis"
        assert isinstance(p.incompatible_regimes, frozenset), f"{p.id} incompatible_regimes deve ser frozenset"
        assert p.evaluator is not None, f"{p.id} deve ter evaluator associado"


def test_regime_first_filtering():
    trending_long = compatible_playbooks(TRENDING_UP, "long")
    assert len(trending_long) > 0

    range_playbooks = compatible_playbooks(RANGE, "long")
    assert len(range_playbooks) > 0

    # Trend continuation não deve aparecer em RANGE
    playbook_001 = get_playbook("PLAYBOOK_001")
    assert playbook_001 is not None
    assert RANGE not in playbook_001.compatible_regimes


def test_evaluator_deterministic_output():
    mock_ctx = {
        "price": 65000.0,
        "ema20": 64800.0,
        "ema50": 64500.0,
        "ema100": 63000.0,
        "ema200": 61000.0,
        "trend": "Bullish",
        "regime": TRENDING_UP,
        "bos": True,
        "choch": False,
        "rsi": 54.0,
        "atr": 800.0,
        "volume_above_average": True,
        "liquidity_sell_side": [64000.0],
        "liquidity_buy_side": [66500.0],
    }

    pb1 = get_playbook("PLAYBOOK_001")
    assert pb1 is not None
    res = pb1.evaluator(mock_ctx)
    assert res.matched is True
    assert res.direction == "long"
    assert res.state in (PlaybookState.TRIGGERED, PlaybookState.NEAR_ENTRY)
    assert res.trade_score >= 70.0
    assert res.stop is not None
    assert res.tp1 is not None
    assert res.rr is not None and res.rr >= 2.0


def test_confluence_consolidation():
    mock_ctx = {
        "price": 65000.0,
        "ema20": 64800.0,
        "ema50": 64500.0,
        "ema200": 61000.0,
        "trend": "Bullish",
        "regime": TRENDING_UP,
        "bos": True,
        "rsi": 52.0,
        "atr": 800.0,
        "volume_above_average": True,
        "liquidity_sell_side": [64000.0],
        "liquidity_buy_side": [67000.0],
    }

    evals = [p.evaluator(mock_ctx) for p in PLAYBOOK_CATALOG[:10]]
    consolidated = consolidate_evaluations("BTCUSDT", evals)

    assert len(consolidated) > 0
    opp = consolidated[0]
    assert opp.asset == "BTCUSDT"
    assert opp.confluence_count >= 1
    assert opp.trade_score > 0
    assert opp.stop is not None
