import pandas as pd
import pytest

from alphaquant_core.engines.scoring import BONUS_MAX, SCORE_MAX, compute_score
from alphaquant_core.engines.targets import Target, TargetResult
from alphaquant_core.playbooks.base import Direction, PlaybookContext, PlaybookResult


def _ctx(regime="BULLISH", htf_regime=None, rsi=50.0, order_blocks=None, fvgs=None) -> PlaybookContext:
    df = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0], "volume": [100.0]},
        index=pd.date_range("2026-01-01", periods=1, freq="h"),
    )
    return PlaybookContext(
        symbol="BTCUSDT", timeframe="1h", df=df,
        indicators={"rsi14": rsi}, swings=[], regime=regime,
        fair_value_gaps=fvgs or [], order_blocks=order_blocks or [], liquidity_sweep=None,
        htf_regime=htf_regime,
    )


def _matched_result(direction=Direction.LONG, progress=100.0, matched=True) -> PlaybookResult:
    return PlaybookResult(
        playbook="Trend Continuation EMA50", matched=matched, direction=direction,
        progress=progress, conditions_met=["a", "b"], conditions_missing=[],
        entry=100.0, stop=95.0,
    )


def _targets(rr: float, structural_count: int = 1) -> TargetResult:
    targets = [Target(price=100 + i, source="structural") for i in range(structural_count)]
    targets += [Target(price=200 + i, source="r_multiple") for i in range(3 - structural_count)]
    return TargetResult(entry=100.0, stop=95.0, risk=5.0, targets=targets[:3], rr=rr)


def test_score_never_exceeds_100():
    ctx = _ctx(regime="BULLISH", htf_regime="BULLISH", rsi=50.0, order_blocks=[1, 2, 3, 4], fvgs=[])
    result = _matched_result()
    targets = _targets(rr=10.0, structural_count=3)  # cenário perfeito, deveria estourar o teto sem o cap

    score = compute_score(ctx, result, targets)
    assert score.total <= SCORE_MAX
    assert score.total == SCORE_MAX


def test_score_is_zero_without_direction():
    ctx = _ctx()
    result = PlaybookResult(playbook="X", matched=False, direction=None, progress=0.0)
    score = compute_score(ctx, result, None)
    assert score.total == 0.0


def test_score_higher_when_playbook_matched_vs_partial():
    ctx = _ctx()
    targets = _targets(rr=2.5)

    full = compute_score(ctx, _matched_result(matched=True, progress=100.0), targets)
    partial = compute_score(ctx, _matched_result(matched=False, progress=50.0), targets)

    assert full.total > partial.total


def test_score_increases_with_better_rr():
    ctx = _ctx()
    result = _matched_result()

    low_rr = compute_score(ctx, result, _targets(rr=1.5))
    mid_rr = compute_score(ctx, result, _targets(rr=2.5))
    high_rr = compute_score(ctx, result, _targets(rr=4.0))

    assert low_rr.total < mid_rr.total < high_rr.total


def test_score_zero_execucao_when_no_valid_targets():
    ctx = _ctx()
    result = _matched_result()
    score = compute_score(ctx, result, None)

    execucao_points = score.breakdown_by_category().get("EXECUCAO", None)
    assert execucao_points == 0.0
    assert score.total < SCORE_MAX


def test_bonus_only_applies_when_matched_and_rr_above_5():
    ctx = _ctx()

    matched_high_rr = compute_score(ctx, _matched_result(matched=True), _targets(rr=6.0))
    matched_low_rr = compute_score(ctx, _matched_result(matched=True), _targets(rr=3.0))
    partial_high_rr = compute_score(ctx, _matched_result(matched=False, progress=60.0), _targets(rr=6.0))

    bonus_matched_high = next(c for c in matched_high_rr.criteria if c.category == "BONUS")
    bonus_matched_low = next(c for c in matched_low_rr.criteria if c.category == "BONUS")
    bonus_partial_high = next(c for c in partial_high_rr.criteria if c.category == "BONUS")

    assert bonus_matched_high.points == BONUS_MAX
    assert bonus_matched_low.points == 0.0
    assert bonus_partial_high.points == 0.0


def test_htf_confirmation_adds_points_only_when_available_and_aligned():
    ctx_no_htf = _ctx(htf_regime=None)
    ctx_htf_aligned = _ctx(regime="BULLISH", htf_regime="BULLISH")
    ctx_htf_conflicting = _ctx(regime="BULLISH", htf_regime="BEARISH")

    result = _matched_result()
    targets = _targets(rr=2.5)

    score_no_htf = compute_score(ctx_no_htf, result, targets)
    score_aligned = compute_score(ctx_htf_aligned, result, targets)
    score_conflicting = compute_score(ctx_htf_conflicting, result, targets)

    assert score_aligned.total > score_no_htf.total
    assert score_conflicting.total == score_no_htf.total  # HTF conflitante não pontua, igual a "não disponível"


def test_every_criterion_has_a_human_readable_name():
    """
    Contrato de auditoria (seção 57): todo critério precisa de um nome
    explicável, nunca só um número — trava isso para qualquer critério
    futuro que alguém adicionar ao Scoring Engine.
    """
    ctx = _ctx()
    score = compute_score(ctx, _matched_result(), _targets(rr=2.5))
    for c in score.criteria:
        assert isinstance(c.name, str) and len(c.name) > 0
        assert c.category in {"CONTEXTO", "ESTRUTURA", "EXECUCAO", "BONUS"}
        assert 0.0 <= c.points <= c.max_points
