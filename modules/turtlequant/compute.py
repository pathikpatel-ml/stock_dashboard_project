"""
Pure, injected-data functions for the Turtle Quant classifier.

Every function here takes plain Series/values it's handed -- no file I/O, no yfinance calls, no
global state -- so each is directly unit-testable with synthetic data, mirroring
modules/turtle/compute.py's own style. ``screener.py`` is the orchestration layer that fetches
real weekly OHLCV and calls these.

RSI/ATR/ADX/SuperTrend are written fresh here rather than reusing src/indicators/__init__.py's
classes: that module takes raw numpy arrays (not DatetimeIndex-aware Series) and, per this
session's exploration, its ADX/Ichimoku/Keltner classes have real tuple-vs-dict return-shape
mismatches against their own test file -- not a dependency worth taking on for new code.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C


def wilder_rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothed moving average -- the shared building block for RSI/ATR/ADX below."""
    return series.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    return wilder_rma(true_range(high, low, close), length)


def rsi(close: pd.Series, length: int = C.RSI_LENGTH) -> pd.Series:
    """Standard Wilder RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = wilder_rma(gain, length)
    avg_loss = wilder_rma(loss, length)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    # avg_loss == 0 with avg_gain > 0 means every recent move was a gain -- RSI should be 100,
    # not NaN (the division above turns 0-loss into NaN via the replace(0, nan) guard above).
    return result.where(avg_loss != 0, 100.0)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = C.DMI_LENGTH) -> pd.Series:
    """Standard Wilder ADX/DMI. Returns the ADX line only -- the source indicator never exposes
    +DI/-DI separately, only a scalar ADX threshold (see constants.py's module docstring)."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index
    )
    atr_ = wilder_rma(true_range(high, low, close), length)
    plus_di = 100 * wilder_rma(plus_dm, length) / atr_.replace(0, np.nan)
    minus_di = 100 * wilder_rma(minus_dm, length) / atr_.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return wilder_rma(dx.fillna(0.0), length)


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_length: int = C.SUPERTREND_ATR_LENGTH,
    factor: float = C.SUPERTREND_ATR_FACTOR,
) -> pd.Series:
    """Standard recursive SuperTrend. Returns a Series of +1 (bullish) / -1 (bearish) trend
    direction, same length/index as ``close``; every value before ATR warms up is direction=+1
    by convention -- callers should only trust ``.iloc[-1]`` once the series is comfortably
    longer than atr_length, which every real weekly-history fetch is."""
    atr_ = atr(high, low, close, atr_length)
    hl2 = (high + low) / 2.0
    upper_basic = hl2 + factor * atr_
    lower_basic = hl2 - factor * atr_

    final_upper = upper_basic.copy()
    final_lower = lower_basic.copy()
    direction = pd.Series(1, index=close.index, dtype=int)

    first_valid = atr_.first_valid_index()
    if first_valid is None:
        return direction  # never warms up (series shorter than atr_length) -- default bullish

    started = False
    for i in range(len(close)):
        if pd.isna(atr_.iloc[i]):
            continue
        if not started:
            # First warmed-up bar: nothing valid to tighten against yet -- seed directly from
            # the basic bands rather than comparing against a NaN "previous" band (comparisons
            # against NaN are always False, which would otherwise wedge final_upper/final_lower
            # at NaN forever -- every branch of the tightening rule below resolves to "keep the
            # previous value").
            final_upper.iloc[i] = upper_basic.iloc[i]
            final_lower.iloc[i] = lower_basic.iloc[i]
            direction.iloc[i] = -1 if close.iloc[i] < lower_basic.iloc[i] else 1
            started = True
            continue

        prev_upper = final_upper.iloc[i - 1]
        prev_lower = final_lower.iloc[i - 1]
        prev_close = close.iloc[i - 1]

        final_upper.iloc[i] = (
            upper_basic.iloc[i]
            if (upper_basic.iloc[i] < prev_upper or prev_close > prev_upper)
            else prev_upper
        )
        final_lower.iloc[i] = (
            lower_basic.iloc[i]
            if (lower_basic.iloc[i] > prev_lower or prev_close < prev_lower)
            else prev_lower
        )

        if close.iloc[i] > final_upper.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < final_lower.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

    return direction


def rolling_ma(series: pd.Series, length: int = C.MA_LENGTH) -> pd.Series:
    return series.rolling(length).mean()


def volume_building(volume: pd.Series, length: int = C.MA_LENGTH) -> Optional[bool]:
    """True if the latest week's volume is above its own 13-week average volume -- same shape
    as ``price_trend_ok`` but for volume (confirmed directly with the user 2026-09-05: a
    current-vs-its-own-average check, NOT "is the average itself trending up")."""
    vma = rolling_ma(volume, length)
    if vma.empty or pd.isna(vma.iloc[-1]):
        return None
    return bool(volume.iloc[-1] > vma.iloc[-1])


def price_trend_ok(close: pd.Series, length: int = C.MA_LENGTH) -> Optional[bool]:
    """True if the latest close is above its own MA -- a short-term trend filter."""
    pma = rolling_ma(close, length)
    if pma.empty or pd.isna(pma.iloc[-1]):
        return None
    return bool(close.iloc[-1] > pma.iloc[-1])


def relative_strength_vs_index(
    stock_close_weekly: Optional[pd.Series],
    index_close_weekly: Optional[pd.Series],
    window_weeks: int,
) -> Optional[float]:
    """Ratio-based RS vs the comparative index (approved formula, no Pine Script source
    available -- see constants.py's module docstring). Reuses
    modules.turtle.compute.relative_strength (the same %-return-over-window calc already tested
    for the Turtle Strategy tab) for BOTH legs, then combines them:

        RS = (1 + stock_return/100) / (1 + index_return/100) - 1

    e.g. RS ~= 1.0 means the stock roughly doubled relative to the index over the window;
    RS = -0.25 means the stock underperformed the index by 25% over the window. Returns None if
    either leg lacks enough history for ``window_weeks``.
    """
    from modules.turtle.compute import relative_strength as _base_rs

    stock_return = _base_rs(stock_close_weekly, window_weeks)
    index_return = _base_rs(index_close_weekly, window_weeks)
    if stock_return is None or index_return is None:
        return None
    denom = 1.0 + index_return / 100.0
    if denom == 0:
        return None
    return (1.0 + stock_return / 100.0) / denom - 1.0


def classify(
    rs_long: Optional[float],
    rs_short: Optional[float],
    adx_value: Optional[float],
    volume_ok: Optional[bool],
    price_trend_ok_: Optional[bool],
    rsi_value: Optional[float],
    supertrend_bullish: bool,
) -> str:
    """Stateless, priority-ordered 3-state classification (mirrors
    modules/turtle/compute.py::classify's if/elif shape, and its precedent of labelling every
    screened stock rather than only ones the user personally holds -- SELL/HOLD are screener
    labels, not portfolio state).

    SELL and BUY are symmetric, both all-or-nothing (confirmed with the user 2026-09-05, a
    deliberate reversal of the earlier "any single weakening signal" design):
      SELL -- every one of: RS Long Term < 0, RS Short Term < 0, ADX < threshold, RSI < RSI_EXIT,
        SuperTrend bearish, price below its own MA. Volume is NOT part of SELL (explicitly
        excluded by the user) -- it's a BUY-only requirement.
      BUY  -- every one of: RS Long Term > 0, RS Short Term > 0, ADX >= threshold, RSI >= RSI_ENTRY,
        SuperTrend bullish, volume building, price above its own MA.
    HOLD -- everything else (e.g. RSI sitting between RSI_EXIT and RSI_ENTRY, or a mix of
      bullish and bearish conditions) -- neither full set is satisfied.
    """
    if (
        rs_long is not None and rs_long < 0
        and rs_short is not None and rs_short < 0
        and adx_value is not None and adx_value < C.ADX_MIN_THRESHOLD
        and rsi_value is not None and rsi_value < C.RSI_EXIT
        and not supertrend_bullish
        and price_trend_ok_ is False
    ):
        return "SELL"

    if (
        rs_long is not None and rs_long > 0
        and rs_short is not None and rs_short > 0
        and adx_value is not None and adx_value >= C.ADX_MIN_THRESHOLD
        and volume_ok
        and price_trend_ok_
        and rsi_value is not None and rsi_value >= C.RSI_ENTRY
        and supertrend_bullish
    ):
        return "BUY"

    return "HOLD"


def relative_strength_vs_index_series(
    stock_close_weekly: pd.Series,
    index_close_weekly: pd.Series,
    window_weeks: int,
) -> pd.Series:
    """Vectorized version of ``relative_strength_vs_index``, computing the ratio-based RS at
    EVERY point in ``stock_close_weekly`` at once (not just the latest) -- used for historical
    backtesting (walking every past week), where calling the point-in-time function once per
    historical week would be far slower.

    Unlike ``modules.turtle.compute.relative_strength`` (which the point-in-time function reuses
    and which buckets DAILY closes into weeks), this operates on already-native weekly bars, so
    a straight N-bar ``.shift()`` is the direct, correct equivalent -- no bucketing needed. Both
    approaches agree at the latest point on real weekly-spaced data (see
    tests/test_turtlequant_engine.py's consistency check).

    ``index_close_weekly`` is reindexed onto ``stock_close_weekly``'s own dates (forward-filled)
    since the two series may not have identical fetch histories. Returns a Series aligned with
    ``stock_close_weekly``'s index; NaN wherever there isn't ``window_weeks`` of prior history yet.
    """
    index_aligned = index_close_weekly.reindex(stock_close_weekly.index, method="ffill")
    stock_return = (stock_close_weekly / stock_close_weekly.shift(window_weeks) - 1.0) * 100.0
    index_return = (index_aligned / index_aligned.shift(window_weeks) - 1.0) * 100.0
    denom = 1.0 + index_return / 100.0
    return (1.0 + stock_return / 100.0) / denom - 1.0


def detect_transition(
    previous_signal: Optional[str],
    previous_signal_date: Optional[str],
    new_signal: str,
    new_signal_date: str,
) -> Optional[dict]:
    """Entry/exit event detection.

    A symbol's very first-ever recorded signal (``previous_signal is None``) counts as a real,
    displayable event ONLY if it's a BUY (confirmed with the user 2026-09-05: an "entry" needs
    no prior state to make sense, but a first-ever SELL would mean "exit a position that was
    never validly entered," which stays disallowed -- nothing to transition FROM there).

    Once a symbol has a prior recorded signal, a transition is only real when a genuinely NEW
    week's signal (``new_signal_date != previous_signal_date``) differs from that prior signal,
    AND the new signal is BUY or SELL (HOLD isn't an actionable "event" worth logging, only
    fresh entries/exits are). Deliberately does NOT fire just because the SAME still-forming
    week's classification shifts between two runs of the same day's batch job (that's the
    candle updating intraday, not a real week-over-week move) -- the
    ``new_signal_date != previous_signal_date`` guard is what prevents that noise from being
    logged as a spurious transition.

    Returns ``{"from_signal": previous_signal, "to_signal": new_signal}`` if a transition
    qualifies (``from_signal`` is ``None`` for a first-ever BUY), else ``None``.
    """
    if new_signal not in ("BUY", "SELL"):
        return None

    if previous_signal is None or previous_signal_date is None:
        return {"from_signal": None, "to_signal": "BUY"} if new_signal == "BUY" else None

    if new_signal_date == previous_signal_date:
        return None
    if new_signal == previous_signal:
        return None
    return {"from_signal": previous_signal, "to_signal": new_signal}


def current_validated_signal(transitions_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Per-symbol VALIDATED current signal, derived purely from the transition event log
    (turtlequant_signal_transitions), not the raw weekly classify() output. Confirmed with the
    user 2026-09-05: the dashboard's displayed Signal must never show a SELL (or anything else)
    for a symbol that hasn't first had a genuine recorded BUY -- and must never show HOLD at
    all, only BUY or SELL.

    Since detect_transition() only ever logs a move INTO BUY or SELL (never HOLD), and only once
    a real prior signal existed to transition from, "the most recent logged event" is exactly
    the validated state: a symbol with no rows here has never had a qualifying event yet, so it
    gets no row back at all (callers left-merging this should get NaN/blank for it, not a
    fabricated status) -- once it does, this reflects whichever of BUY/SELL it flipped into
    most recently, held until the next qualifying flip.

    Returns columns ``Symbol``, ``Signal``, ``Signal_Date`` -- one row per symbol that has ever
    had at least one qualifying transition.
    """
    empty = pd.DataFrame(columns=["Symbol", "Signal", "Signal_Date"])
    if transitions_df is None or transitions_df.empty:
        return empty
    if not {"Symbol", "To_Signal", "Transition_Date"}.issubset(transitions_df.columns):
        return empty

    latest_idx = transitions_df.groupby("Symbol")["Transition_Date"].idxmax()
    latest = transitions_df.loc[latest_idx, ["Symbol", "To_Signal", "Transition_Date"]]
    return latest.rename(columns={"To_Signal": "Signal", "Transition_Date": "Signal_Date"}).reset_index(drop=True)
