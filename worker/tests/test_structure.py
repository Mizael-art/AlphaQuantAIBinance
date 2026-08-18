import pandas as pd

from alphaquant_core.engines.structure import (
    StructureLabel,
    SwingType,
    current_regime,
    detect_structure_events,
    find_swings,
)


def _df_from_highs_lows(highs: list[float], lows: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(highs), freq="h")
    return pd.DataFrame({"high": highs, "low": lows}, index=index)


def test_find_swings_detects_a_clear_high_and_low():
    # sobe até o pico no índice 5, desce até o vale no índice 11, sobe de novo
    highs = [10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10, 5, 10, 11, 12, 13, 14]
    lows = [h - 2 for h in highs]
    df = _df_from_highs_lows(highs, lows)

    swings = find_swings(df, left=3, right=3)
    swing_prices = {(s.type, s.price) for s in swings}

    assert (SwingType.HIGH, 20.0) in swing_prices
    assert (SwingType.LOW, 3.0) in swing_prices  # low = high - 2 no índice do vale


def test_structure_labels_hh_hl_in_uptrend():
    # três picos ascendentes com vales ascendentes entre eles -> HH/HL
    highs = [10, 20, 10, 12, 25, 12, 14, 30, 14]
    lows = [h - 3 for h in highs]
    df = _df_from_highs_lows(highs, lows)

    swings = find_swings(df, left=1, right=1)
    labels = [s.label for s in swings if s.label is not None]

    assert StructureLabel.HH in labels
    assert StructureLabel.HL in labels
    assert StructureLabel.LL not in labels


def test_detect_structure_events_choch_on_trend_reversal():
    # tendência de alta confirmada (HH/HL/HH/HL) seguida de LH e depois um
    # LL confirmado (com candle de confirmação após o vale) -> CHOCH
    highs = [10, 20, 12, 25, 14, 30, 16, 18, 9, 15, 20]
    lows = [8, 17, 9, 22, 11, 27, 13, 15, 4, 12, 17]
    df = _df_from_highs_lows(highs, lows)

    swings = find_swings(df, left=1, right=1)
    events = detect_structure_events(swings)

    assert any(e["event"] == "CHOCH" and e["regime"] == "BEARISH" for e in events)


def test_current_regime_undefined_without_confirmed_trend():
    highs = [10, 11, 10, 11, 10]
    lows = [h - 1 for h in highs]
    df = _df_from_highs_lows(highs, lows)

    swings = find_swings(df, left=1, right=1)
    assert current_regime(swings) in {"UNDEFINED", "BULLISH", "BEARISH"}
