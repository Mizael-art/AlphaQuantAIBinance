from alphaquant_core.engines.quality_filter import evaluate_quality
from alphaquant_core.engines.scoring import ScoreCriterion, ScoreResult
from alphaquant_core.engines.targets import Target, TargetResult
from alphaquant_core.playbooks.base import Direction, PlaybookResult


def _matched_result(matched=True) -> PlaybookResult:
    return PlaybookResult(
        playbook="Trend Continuation EMA50", matched=matched, direction=Direction.LONG,
        progress=100.0 if matched else 50.0, entry=100.0, stop=95.0,
    )


def _score(total: float) -> ScoreResult:
    return ScoreResult(total=total, criteria=[ScoreCriterion("CONTEXTO", "x", total, 100.0)])


def _targets(rr: float) -> TargetResult:
    return TargetResult(entry=100.0, stop=95.0, risk=5.0, targets=[Target(110.0, "structural")], rr=rr)


def test_approved_when_everything_passes():
    result = evaluate_quality(_matched_result(), _targets(rr=3.0), _score(85.0), confidence="ALTA")
    assert result.approved is True
    assert result.reasons == []


def test_rejected_when_no_playbook_matched_even_with_high_score():
    """Mesmo Score 95+ deve ser REPROVADO se não houver Playbook confirmado (seção 27)."""
    result = evaluate_quality(_matched_result(matched=False), _targets(rr=3.0), _score(95.0), confidence="ALTA")
    assert result.approved is False
    assert any("Playbook" in r for r in result.reasons)


def test_rejected_when_rr_below_minimum_even_with_high_score():
    """Mesmo Score 95+ deve ser REPROVADO se RR < mínimo exigido (seção 27)."""
    result = evaluate_quality(_matched_result(), _targets(rr=1.5), _score(95.0), confidence="ALTA")
    assert result.approved is False
    assert any("RR" in r for r in result.reasons)


def test_rejected_when_stop_invalid_even_with_high_score():
    """Mesmo Score 95+ deve ser REPROVADO se o stop não representar uma invalidação real."""
    result = evaluate_quality(_matched_result(), None, _score(95.0), confidence="ALTA")
    assert result.approved is False
    assert any("Stop" in r for r in result.reasons)


def test_rejected_when_score_below_playbook_minimum():
    result = evaluate_quality(_matched_result(), _targets(rr=3.0), _score(60.0), confidence="ALTA", minimum_score=70.0)
    assert result.approved is False
    assert any("Score" in r for r in result.reasons)


def test_rejected_when_data_insufficient_even_with_high_score():
    """Mesmo Score 95+ deve ser REPROVADO se os dados forem insuficientes (confidence BAIXA)."""
    result = evaluate_quality(_matched_result(), _targets(rr=3.0), _score(95.0), confidence="BAIXA")
    assert result.approved is False
    assert any("insuficientes" in r for r in result.reasons)


def test_multiple_blocks_all_reported_together():
    result = evaluate_quality(_matched_result(matched=False), None, _score(30.0), confidence="BAIXA")
    assert result.approved is False
    assert len(result.reasons) == 4  # playbook, stop/RR, score, dados — todos reportados, não só o primeiro


def test_respects_per_playbook_thresholds_not_hardcoded():
    """
    Os limiares vêm da tabela `playbooks` (minimum_score/minimum_rr),
    não são fixos no código — um playbook mais rigoroso (ex.: RR mínimo 3)
    deve reprovar um RR que outro playbook aprovaria.
    """
    lenient = evaluate_quality(_matched_result(), _targets(rr=2.5), _score(85.0), confidence="ALTA", minimum_rr=2.0)
    strict = evaluate_quality(_matched_result(), _targets(rr=2.5), _score(85.0), confidence="ALTA", minimum_rr=3.0)

    assert lenient.approved is True
    assert strict.approved is False
