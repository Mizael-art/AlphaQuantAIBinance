import pandas as pd

from alphaquant_core.engines.structure import Swing, SwingType, StructureLabel
from alphaquant_core.engines.targets import MIN_RR_FOR_STRUCTURAL_TARGET, compute_targets
from alphaquant_core.playbooks.base import Direction


def _swing(price: float, type_: SwingType, index: int = 0) -> Swing:
    return Swing(index=index, timestamp=pd.Timestamp("2026-01-01"), price=price, type=type_, label=StructureLabel.HH)


def test_compute_targets_uses_structural_swing_when_far_enough():
    entry, stop = 100.0, 95.0  # risco = 5
    swings = [_swing(112.0, SwingType.HIGH)]  # 12 de distância = 2.4R -> válido
    result = compute_targets(swings, Direction.LONG, entry, stop)

    assert result is not None
    assert result.targets[0].source == "structural"
    assert result.targets[0].price == 112.0
    assert result.rr == 2.4


def test_compute_targets_ignores_swing_too_close_as_noise():
    entry, stop = 100.0, 95.0  # risco = 5, mínimo exigido = 5 (1R)
    swings = [_swing(101.0, SwingType.HIGH)]  # só 1 de distância = 0.2R -> ruído, descartado
    result = compute_targets(swings, Direction.LONG, entry, stop)

    assert result is not None
    assert all(t.source == "r_multiple" for t in result.targets)


def test_compute_targets_fills_with_r_multiples_when_no_structural_swings():
    entry, stop = 100.0, 95.0
    result = compute_targets([], Direction.LONG, entry, stop)

    assert result is not None
    assert len(result.targets) == 3
    assert [t.source for t in result.targets] == ["r_multiple"] * 3
    assert result.targets[0].price == 110.0  # entry + 2R
    assert result.targets[1].price == 115.0  # entry + 3R
    assert result.targets[2].price == 120.0  # entry + 4R
    assert result.rr == 2.0


def test_compute_targets_short_direction_mirrors_long():
    entry, stop = 100.0, 105.0  # risco = 5
    swings = [_swing(88.0, SwingType.LOW)]  # 12 de distância = 2.4R
    result = compute_targets(swings, Direction.SHORT, entry, stop)

    assert result is not None
    assert result.targets[0].price == 88.0
    assert result.rr == 2.4


def test_compute_targets_returns_none_for_invalid_stop():
    # stop do lado errado (acima da entrada, para um LONG) -> risco <= 0
    result = compute_targets([], Direction.LONG, entry=100.0, stop=105.0)
    assert result is None

    result_zero_risk = compute_targets([], Direction.LONG, entry=100.0, stop=100.0)
    assert result_zero_risk is None


def test_compute_targets_picks_nearest_three_structural_swings_in_order():
    entry, stop = 100.0, 90.0  # risco = 10, mínimo = 10
    swings = [
        _swing(130.0, SwingType.HIGH),
        _swing(115.0, SwingType.HIGH),  # mais próximo
        _swing(150.0, SwingType.HIGH),
        _swing(105.0, SwingType.HIGH),  # abaixo do mínimo (5 de distância = 0.5R) -> ignorado
    ]
    result = compute_targets(swings, Direction.LONG, entry, stop)

    assert [round(t.price, 2) for t in result.targets] == [115.0, 130.0, 150.0]
    assert all(t.source == "structural" for t in result.targets)


def test_min_rr_for_structural_target_constant_is_one():
    # trava o valor da constante — mudar isso é uma decisão de produto,
    # não um detalhe de implementação a ser alterado silenciosamente
    assert MIN_RR_FOR_STRUCTURAL_TARGET == 1.0
