"""
Trade mathematics for the Multi-Year Breakout strategy.

Pure, deterministic functions — no I/O, no network. Each implements an exact formula
from the requirements doc (§5-§7, §10.3, §12.3) so it can be unit-tested against the
worked examples in the document.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from . import constants as C


# ---------------------------------------------------------------------------
# Stop loss, range, target, risk:reward (doc §6.1, §7.1, §5.3)
# ---------------------------------------------------------------------------
def stop_loss(breakout_candle_low: float) -> float:
    """SL = Breakout Candle Low x 0.99 (doc §6.1).

    Example: low 200 -> 198.0
    """
    return round(breakout_candle_low * C.SL_MULTIPLIER, 4)


def range_size(resistance: float, support: float) -> float:
    """Range = Resistance - Support (doc §7.1)."""
    return resistance - support


def target_1(resistance: float, support: float) -> float:
    """T1 = Resistance + (Resistance - Support)  [measured move] (doc §7.1).

    Example: resistance 220, support 150 -> range 70 -> T1 290.
    """
    return round(resistance + range_size(resistance, support), 4)


def risk_reward(entry: float, stop: float, target: float) -> float:
    """R:R = (Target - Entry) / (Entry - Stop Loss) (doc §5.3).

    Returns float (the 'X' in 1:X). Returns nan if the risk denominator is non-positive.
    """
    risk = entry - stop
    if risk <= 0:
        return float("nan")
    return round((target - entry) / risk, 4)


def passes_rr_gate(rr: float) -> bool:
    """Entry only permitted if R:R >= 1:2 (doc §5.3)."""
    return (not np.isnan(rr)) and rr >= C.MIN_RR_RATIO


def distance_to_breakout(cmp: float, resistance: float) -> float:
    """Distance to breakout % = (Resistance - CMP) / CMP x 100 (doc §10.3).

    Positive => price still below resistance (approaching). Negative => already above.
    """
    if cmp == 0:
        return float("nan")
    return round((resistance - cmp) / cmp * 100, 4)


def priority_score(age_years: float, delivery_pct: float, distance_pct: float) -> float:
    """Composite watchlist score (doc §10.3):

        (Resistance Age x 0.3) + (Delivery Volume % x 0.4) + ((1 - Distance%) x 0.3)

    The document's formula mixes scales (age in years, delivery as a percent number,
    distance as a fraction). We follow it literally: distance% is taken as a *fraction*
    (3% -> 0.03), age in years, delivery as the percent number (e.g. 65.0). Higher = better.
    """
    dist_frac = distance_pct / 100.0
    return round(
        age_years * C.PRIORITY_W_AGE
        + delivery_pct * C.PRIORITY_W_DELIVERY
        + (1.0 - dist_frac) * C.PRIORITY_W_DISTANCE,
        4,
    )


# ---------------------------------------------------------------------------
# 21-EMA weekly trailing stop (doc §7.2, §12.3)
# ---------------------------------------------------------------------------
def weekly_ema(weekly_closes: Sequence[float], period: int = C.TRAILING_EMA_PERIOD) -> np.ndarray:
    """21-period EMA on weekly closing prices.

    Uses the recursive EMA (seed = first close, multiplier = 2/(period+1)) — identical to
    the existing ``MACD._ema`` and to ``pandas.Series.ewm(span=period, adjust=False)``.
    """
    prices = np.asarray(weekly_closes, dtype=float)
    if prices.size == 0:
        return prices
    return pd.Series(prices).ewm(span=period, adjust=False).mean().to_numpy()


@dataclass
class TrailingState:
    """Result of evaluating the weekly 21-EMA trailing rule."""
    ema: float                  # latest 21-EMA value
    consecutive_below: int      # consecutive weekly closes below the EMA at the end of the series
    exit_signal: bool           # True once 2 consecutive weekly closes are below the EMA


def evaluate_weekly_trailing(
    weekly_closes: Sequence[float],
    period: int = C.TRAILING_EMA_PERIOD,
    consecutive_needed: int = C.TRAILING_CONSECUTIVE_CLOSES,
) -> TrailingState:
    """Evaluate the 21-EMA weekly trailing stop (doc §12.3).

    - 1 weekly close below EMA  -> counter = 1 (warning, hold).
    - 2 consecutive closes below -> counter = 2 (exit signal).
    - Any weekly close above EMA -> counter resets to 0.

    Returns the latest EMA, the trailing count, and whether the exit signal has fired.
    """
    prices = np.asarray(weekly_closes, dtype=float)
    if prices.size == 0:
        return TrailingState(ema=float("nan"), consecutive_below=0, exit_signal=False)

    ema = weekly_ema(prices, period)
    below = prices < ema

    # Count consecutive "below" flags ending at the last observation.
    count = 0
    for flag in below[::-1]:
        if flag:
            count += 1
        else:
            break

    return TrailingState(
        ema=round(float(ema[-1]), 4),
        consecutive_below=count,
        exit_signal=count >= consecutive_needed,
    )
