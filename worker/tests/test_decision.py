from alphaquant_core.engines.decision import ENTRAR, ESPERAR, REPROVAR, make_decision
from alphaquant_core.engines.quality_filter import QualityFilterResult


def test_decision_reprovar_when_quality_filter_rejects():
    qf = QualityFilterResult(approved=False, reasons=["RR abaixo do mínimo"])
    result = make_decision(qf, confidence="ALTA")
    assert result.decision == REPROVAR
    assert result.reasons == ["RR abaixo do mínimo"]


def test_decision_entrar_when_approved_and_high_confidence():
    qf = QualityFilterResult(approved=True, reasons=[])
    result = make_decision(qf, confidence="ALTA")
    assert result.decision == ENTRAR


def test_decision_esperar_when_approved_but_moderate_confidence():
    qf = QualityFilterResult(approved=True, reasons=[])
    result = make_decision(qf, confidence="MODERADA")
    assert result.decision == ESPERAR
    assert result.reasons  # sempre explica o motivo de esperar


def test_decision_never_returns_something_other_than_the_three_valid_values():
    qf_approved = QualityFilterResult(approved=True, reasons=[])
    qf_rejected = QualityFilterResult(approved=False, reasons=["x"])

    for qf in (qf_approved, qf_rejected):
        for confidence in ("BAIXA", "MODERADA", "ALTA"):
            result = make_decision(qf, confidence)
            assert result.decision in {ENTRAR, ESPERAR, REPROVAR}


def test_decision_reprovar_takes_priority_over_confidence():
    """
    Mesmo com confidence ALTA, um Quality Filter reprovado nunca vira
    ENTRAR nem ESPERAR — REPROVAR é absoluto (seção 27).
    """
    qf = QualityFilterResult(approved=False, reasons=["Score abaixo do mínimo"])
    result = make_decision(qf, confidence="ALTA")
    assert result.decision == REPROVAR
