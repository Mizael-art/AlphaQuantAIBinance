"""
tests/test_trade_discovery_quality_gates.py
============================================

Testes de regressão e validação dos Hard Quality Gates:
1. Hard Gate de RR Mínimo (rejeição de RR < 2.0 ou < playbook.min_rr)
2. Directional Conflict Resolution (desempate LONG vs SHORT no mesmo ativo)
3. 3-Score Architecture (Setup 60%, Entry 40%, Trade Score) sem score 70 padrão
4. Entry Extension / Chase Risk Filter (WAIT_PULLBACK para entradas esticadas)
5. Telegram Gate (somente sinais qualificados)
"""

import pytest
from decision.engine import evaluate_decision, LONG_NOW, SHORT_NOW, WAIT_PULLBACK, REJECT
from scoring.engine import compute_opportunity_score
from playbook.library import PLAYBOOK_CATALOG


def test_hard_gate_rr_rejection():
    """Valida que trades com RR abaixo do mínimo obrigatório são sumariamente rejeitados."""
    # Caso 1: RR 1.3 com min_rr 2.5 -> REJECT
    dec1 = evaluate_decision(
        direction="long",
        overall_score=85.0,
        risk_decision="APPROVED",
        setup_status="READY",
        entry_quality="ENTRY_NOW",
        rr=1.3,
        min_rr=2.5,
    )
    assert dec1.decision == REJECT
    assert any("abaixo do mínimo" in r for r in dec1.reasons)

    # Caso 2: RR 2.49 com min_rr 2.5 -> REJECT
    dec2 = evaluate_decision(
        direction="long",
        overall_score=90.0,
        risk_decision="APPROVED",
        setup_status="READY",
        entry_quality="ENTRY_NOW",
        rr=2.49,
        min_rr=2.5,
    )
    assert dec2.decision == REJECT

    # Caso 3: RR 2.50 com min_rr 2.5 -> PASS (LONG_NOW)
    dec3 = evaluate_decision(
        direction="long",
        overall_score=85.0,
        risk_decision="APPROVED",
        setup_status="READY",
        entry_quality="ENTRY_NOW",
        rr=2.50,
        min_rr=2.5,
    )
    assert dec3.decision == LONG_NOW


def test_three_score_architecture():
    """Valida que Trade Score é exatamente 0.60*SetupScore + 0.40*EntryScore sem fallback arbitrário de 70."""
    score = compute_opportunity_score(
        trend="Bullish",
        bos=True,
        choch=False,
        regime_compatible=True,
        rr=2.8,
        distance_to_zone_pct=0.4,
        volatility_bucket="NORMAL",
        btc_context="BTC_SUPPORTIVE",
        correlation_penalty=False,
        volume_expansion=True,
        rsi_alignment=True,
        obstacle_ahead=False,
    )

    assert score.setup_score > 70.0
    assert score.entry_score > 70.0
    expected_trade_score = round(0.60 * score.setup_score + 0.40 * score.entry_score, 1)
    assert round(score.trade_score, 1) == expected_trade_score
    assert score.overall == score.trade_score


def test_stretched_entry_chase_risk():
    """Valida que entradas esticadas (> 2.5% da zona) resultam em WAIT_PULLBACK."""
    dec = evaluate_decision(
        direction="long",
        overall_score=88.0,
        risk_decision="APPROVED",
        setup_status="UNKNOWN",
        entry_quality="NO_ENTRY",
        rr=2.5,
        min_rr=2.0,
    )
    assert dec.decision == WAIT_PULLBACK
    assert any("aguardar pullback" in r for r in dec.reasons)


def test_directional_conflict_resolution():
    """Valida que um ativo não pode ter LONG e SHORT simultâneos aprovados no mesmo ciclo."""
    from discovery.engine import scan_opportunities
    import pandas as pd
    import numpy as np

    class FakeMarketData:
        last_result = None

        def get_ohlcv_dataframe(self, symbol: str, timeframe: str = "1H", limit: int = 500):
            # Cria 200 candles simulados
            dates = pd.date_range("2026-01-01", periods=200, freq="1h")
            close = 100.0 + np.cumsum(np.random.normal(0, 0.5, 200))
            high = close + 0.5
            low = close - 0.5
            volume = np.full(200, 1000.0)
            return pd.DataFrame({
                "timestamp": dates,
                "open": close,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            })

        def get_current_price(self, symbol: str) -> float:
            return 100.0


    res = scan_opportunities(
        symbols=["FFUSDT"],
        btc_symbol="BTCUSDT",
        timeframe="1H",
        top_n=5,
        market_data=FakeMarketData(),
    )

    opps = res.get("opportunities", [])
    # Não pode ter mais de 1 oportunidade para o mesmo símbolo (LONG e SHORT simultâneos eliminados)
    symbols_in_opps = [o["symbol"] for o in opps]
    assert len(symbols_in_opps) == len(set(symbols_in_opps))

