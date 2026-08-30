"""
playbook/params.py
==================

Centralized parameters and technical thresholds for the AlphaQuant X
76-Playbook Strategy Factory.

No magic numbers in evaluator logic. Every threshold is named, parameterized,
and centrally configurable.
"""

from __future__ import annotations

from typing import Final

# Moving Averages
EMA_FAST_PERIOD: Final[int] = 20
EMA_MED_PERIOD: Final[int] = 50
EMA_SLOW_PERIOD: Final[int] = 100
EMA_BASE_PERIOD: Final[int] = 200

# Oscillators
RSI_PERIOD: Final[int] = 14
RSI_OVERSOLD: Final[float] = 30.0
RSI_OVERBOUGHT: Final[float] = 70.0
RSI_MIDPOINT: Final[float] = 50.0
RSI_BULL_PULLBACK_LOW: Final[float] = 40.0
RSI_BULL_PULLBACK_HIGH: Final[float] = 55.0
RSI_BEAR_PULLBACK_LOW: Final[float] = 45.0
RSI_BEAR_PULLBACK_HIGH: Final[float] = 60.0

STOCH_K_PERIOD: Final[int] = 14
STOCH_D_PERIOD: Final[int] = 3
STOCH_OVERSOLD: Final[float] = 20.0
STOCH_OVERBOUGHT: Final[float] = 80.0

# Volatility & ATR
ATR_PERIOD: Final[int] = 14
ATR_BUFFER_MULT: Final[float] = 1.0
ATR_COMPRESSION_PERCENTILE: Final[float] = 25.0
ATR_EXPANSION_MULT: Final[float] = 1.35

# Volume & Activity
VOLUME_SMA_PERIOD: Final[int] = 20
VOLUME_BREAKOUT_MULT: Final[float] = 1.5
VOLUME_EXHAUSTION_MULT: Final[float] = 2.5
VOLUME_DRYUP_MULT: Final[float] = 0.65

# Distance & Entry Zones (% from current price to reference level)
ZONE_NEAR_ENTRY_PCT: Final[float] = 1.2
ZONE_DEVELOPING_PCT: Final[float] = 3.5
SWEEP_TOLERANCE_PCT: Final[float] = 0.8

# Risk/Reward Defaults
DEFAULT_MIN_RR: Final[float] = 2.0
HIGH_CONVICTION_MIN_RR: Final[float] = 2.5
TIER_S_MIN_RR: Final[float] = 3.0

# Scoring Weights
WEIGHT_SETUP_SCORE: Final[float] = 0.60
WEIGHT_ENTRY_SCORE: Final[float] = 0.40
MIN_TRADE_SCORE_WATCH: Final[int] = 50
MIN_TRADE_SCORE_NEAR_ENTRY: Final[int] = 65
MIN_TRADE_SCORE_TRIGGERED: Final[int] = 75

# Cooldowns (hours)
DEFAULT_COOLDOWN_HOURS: Final[int] = 4
A_PLUS_COOLDOWN_HOURS: Final[int] = 2
