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

    SELL -- any single weakening signal (approved "any single weakening signal" exit strictness):
      SuperTrend bearish, OR RS Long Term <= exit threshold, OR RSI <= RSI_EXIT. This also
      covers a stock that was never in an uptrend at all (SuperTrend bearish) -- there is no
      separate "not applicable" state, same as the existing Turtle tab's EXIT.
    BUY  -- every entry condition holds: SuperTrend bullish, RS Long Term and RS Short Term both
      positive, ADX >= threshold, volume building, price above its own MA, RSI >= RSI_ENTRY.
    HOLD -- SuperTrend bullish but the full BUY confirmation isn't met.
    """
    if (
        not supertrend_bullish
        or (rs_long is not None and rs_long <= C.RS_LONG_TERM_EXIT_THRESHOLD)
        or (rsi_value is not None and rsi_value <= C.RSI_EXIT)
    ):
        return "SELL"

    if (
        rs_long is not None and rs_long > 0
        and rs_short is not None and rs_short > 0
        and adx_value is not None and adx_value >= C.ADX_MIN_THRESHOLD
        and volume_ok
        and price_trend_ok_
        and rsi_value is not None and rsi_value >= C.RSI_ENTRY
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


def last_signal_dates(history_df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Per-symbol most-recent BUY date and most-recent SELL date, derived from the full
    ``turtlequant_signals_history`` table (one row per symbol per actual week -- see
    screener.py::screen_symbol's Signal_Date). Expects columns ``Symbol``, ``Signal``,
    ``Signal_Date`` (string or date-like, sortable lexicographically as ISO ``YYYY-MM-DD``).

    Returns columns ``Symbol``, ``Last_Buy_Date``, ``Last_Sell_Date`` -- either may be missing
    (NaN) for a symbol that has never had that signal type in the recorded history yet (history
    only goes back as far as the table has existed, so this fills in and gets more complete
    week over week, not something this function can backfill on its own).
    """
    empty = pd.DataFrame(columns=["Symbol", "Last_Buy_Date", "Last_Sell_Date"])
    if history_df is None or history_df.empty:
        return empty
    if not {"Symbol", "Signal", "Signal_Date"}.issubset(history_df.columns):
        return empty

    df = history_df[history_df["Signal"].isin(["BUY", "SELL"])]
    if df.empty:
        return empty

    pivot = df.groupby(["Symbol", "Signal"])["Signal_Date"].max().unstack("Signal")
    pivot = pivot.reindex(columns=["BUY", "SELL"])
    pivot = pivot.rename(columns={"BUY": "Last_Buy_Date", "SELL": "Last_Sell_Date"})
    return pivot.reset_index()


def detect_transition(
    previous_signal: Optional[str],
    previous_signal_date: Optional[str],
    new_signal: str,
    new_signal_date: str,
) -> Optional[dict]:
    """True entry/exit event detection: a transition is only real when a genuinely NEW week's
    signal (``new_signal_date != previous_signal_date``) differs from the symbol's last
    recorded signal, AND the new signal is BUY or SELL (per the user's own framing 2026-09-05:
    HOLD isn't an actionable "event" worth logging, only fresh entries/exits are).

    Deliberately does NOT fire just because the SAME still-forming week's classification shifts
    between two runs of the same day's batch job (that's the candle updating intraday, not a
    real week-over-week move) -- the ``new_signal_date != previous_signal_date`` guard is what
    prevents that noise from being logged as a spurious transition.

    Returns ``{"from_signal": previous_signal, "to_signal": new_signal}`` if a transition
    qualifies, else ``None``. ``previous_signal`` may be ``None`` (the symbol's very first-ever
    recorded signal) -- that alone is NOT a transition (nothing to transition FROM), so this
    also returns ``None`` in that case, even if ``new_signal`` is BUY or SELL.
    """
    if previous_signal is None or previous_signal_date is None:
        return None
    if new_signal_date == previous_signal_date:
        return None
    if new_signal == previous_signal:
        return None
    if new_signal not in ("BUY", "SELL"):
        return None
    return {"from_signal": previous_signal, "to_signal": new_signal}
