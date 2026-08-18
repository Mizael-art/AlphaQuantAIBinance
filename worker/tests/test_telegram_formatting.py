from types import SimpleNamespace

from alphaquant_core.telegram.formatting import (
    format_future_message,
    format_invalidation_message,
    format_signal_message,
)


class _FakeDirection:
    def __init__(self, value):
        self.value = value


def _opportunity(**overrides):
    base = dict(
        asset="BTCUSDT", timeframe="1h", playbook="FVG Retracement", score=95.0,
        confidence="ALTA", direction=_FakeDirection("LONG"), entry=131.5, stop=131.3,
        rr=19.0, progress=100.0,
        audit_snapshot={
            "conditions_met": ["Preço dentro de FVG não preenchido"],
            "targets": [{"price": 135.2, "source": "structural"}],
            "quality_filter": {"approved": True, "reasons": []},
            "decision": {"decision": "ENTRAR", "reasons": ["Quality Filter aprovado com dados de alta confiança"]},
        },
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_signal_message_contains_real_data_not_placeholders():
    opp = _opportunity()
    text = format_signal_message(opp)

    assert "BTCUSDT" in text
    assert "FVG Retracement" in text
    assert "95/100" in text
    assert "ALTA" in text
    assert "LONG" in text
    assert "131.5000" in text
    assert "1 : 19.00" in text
    assert "Preço dentro de FVG não preenchido" in text
    assert "🟢 ENTRAR" in text
    assert "Não é garantia de resultado." in text


def test_signal_message_never_shows_example_values_from_spec():
    """
    O template da especificação usa BTCUSDT/87/1:3.4 como exemplo — este
    teste garante que estamos preenchendo com os dados reais do teste
    (que por acaso usam outro conjunto), não copiando literais do
    documento original.
    """
    opp = _opportunity(score=42.0, rr=2.5)
    text = format_signal_message(opp)
    assert "42/100" in text
    assert "1 : 2.50" in text
    assert "87/100" not in text


def test_future_message_shows_progress_and_next_trigger():
    opp = _opportunity(
        score=74.0, progress=82.0, confidence="MODERADA",
        audit_snapshot={
            "conditions_met": ["HTF bullish", "Pullback"],
            "targets": [],
            "quality_filter": {"approved": True, "reasons": []},
            "decision": {"decision": "ESPERAR", "reasons": ["aguardando confirmação do HTF"]},
        },
    )
    text = format_future_message(opp)

    assert "FUTURE OPPORTUNITY" in text
    assert "74/100" in text
    assert "82%" in text
    assert "HTF bullish" in text
    assert "aguardando confirmação do HTF" in text
    assert "EM FORMAÇÃO" in text
    assert "Não é entrada." in text


def test_future_message_has_fallback_next_trigger_when_no_reasons():
    opp = _opportunity(audit_snapshot={
        "conditions_met": [], "targets": [],
        "quality_filter": {"approved": True, "reasons": []},
        "decision": {"decision": "ESPERAR", "reasons": []},
    })
    text = format_future_message(opp)
    assert "Aguardando confirmação adicional." in text


def test_invalidation_message_shows_quality_filter_reasons():
    opp = _opportunity(
        score=65.0,
        audit_snapshot={
            "conditions_met": [], "targets": [],
            "quality_filter": {"approved": False, "reasons": ["RR 1.08 abaixo do mínimo exigido pelo playbook (2.00)"]},
            "decision": {"decision": "REPROVAR", "reasons": []},
        },
    )
    text = format_invalidation_message(opp)

    assert "SETUP INVALIDADO" in text
    assert "65" in text
    assert "RR 1.08 abaixo do mínimo exigido pelo playbook (2.00)" in text
    assert "REPROVADO" in text
    assert "Nenhuma entrada foi recomendada." in text


def test_invalidation_message_has_fallback_reason_when_none_given():
    opp = _opportunity(audit_snapshot={
        "conditions_met": [], "targets": [],
        "quality_filter": {"approved": False, "reasons": []},
        "decision": {"decision": "REPROVAR", "reasons": []},
    })
    text = format_invalidation_message(opp)
    assert "Condições deixaram de ser atendidas" in text


def test_all_messages_are_plain_strings_safe_for_telegram():
    opp = _opportunity()
    for fn in (format_signal_message, format_future_message, format_invalidation_message):
        text = fn(opp)
        assert isinstance(text, str)
        assert len(text) > 0
