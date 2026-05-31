"""
Historical backtest of the full Multi-Year Breakout trade plan (doc §7.3 hybrid exit).

Given a symbol's monthly + weekly OHLCV, locate the historical multi-year breakout, then
simulate the documented hybrid plan:
  * enter at the breakout monthly close,
  * SL = breakout candle low x 0.99,
  * T1 = Resistance + Range (exit 50% there),
  * trail the remaining 50% on the weekly 21-EMA, exiting on 2 consecutive weekly closes below it.

Returns one trade record per symbol (the primary multi-year breakout) with a blended return.
Used by the Historical/Backtest dashboard module and the golden-case validation tests.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import trade_math as tm
from .candle_validation import validate_breakout_candle
from .resistance import detect_resistance


@dataclass
class BacktestResult:
    symbol: str
    found: bool
    reason: str = ""
    breakout_date: Optional[str] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    resistance: Optional[float] = None
    support: Optional[float] = None
    resistance_age_years: Optional[float] = None
    peak_price: Optional[float] = None
    exit_price: Optional[float] = None       # blended representative exit
    return_pct: Optional[float] = None       # blended return on the full position
    holding_months: Optional[int] = None
    outcome: Optional[str] = None            # WIN | LOSS | OPEN

    def to_dict(self) -> Dict:
        return asdict(self)


def find_breakout_month(monthly_df: pd.DataFrame, min_prior: int = C.MIN_RESISTANCE_AGE_MONTHS):
    """Return (position, ResistanceInfo) of the earliest valid historical breakout, else (None, None)."""
    if monthly_df is None or len(monthly_df) <= min_prior:
        return None, None
    for i in range(min_prior, len(monthly_df)):
        res = detect_resistance(monthly_df, as_of_index=i)
        if not res.valid:
            continue
        bar = monthly_df.iloc[i]
        if float(bar["Close"]) <= res.resistance:
            continue
        candle = validate_breakout_candle(
            open_=float(bar["Open"]), high=float(bar["High"]), low=float(bar["Low"]),
            close=float(bar["Close"]), resistance=res.resistance,
            breakout_volume=float(bar.get("Volume", np.nan)),
            prior_volumes=monthly_df["Volume"].iloc[:i].tolist() if "Volume" in monthly_df else [],
        )
        if not candle.is_valid:
            continue
        entry = float(bar["Close"])
        sl = tm.stop_loss(float(bar["Low"]))
        t1 = tm.target_1(res.resistance, res.support)
        if not tm.passes_rr_gate(tm.risk_reward(entry, sl, t1)):
            continue
        return i, res
    return None, None


def _weekly_trail_exit(weekly_df: pd.DataFrame, after_date: pd.Timestamp):
    """First price/date where 2 consecutive weekly closes fall below the 21-EMA, after ``after_date``.

    Returns (exit_price, exit_date, triggered: bool). If never triggered, returns the final
    weekly close (the position rode to the end of available data).
    """
    if weekly_df is None or weekly_df.empty:
        return None, None, False
    closes = weekly_df["Close"].to_numpy(dtype=float)
    ema = tm.weekly_ema(closes)
    below = closes < ema
    consec = 0
    for pos, dt in enumerate(weekly_df.index):
        if dt <= after_date:
            consec = 0
            continue
        if below[pos]:
            consec += 1
            if consec >= C.TRAILING_CONSECUTIVE_CLOSES:
                return float(closes[pos]), dt, True
        else:
            consec = 0
    return float(closes[-1]), weekly_df.index[-1], False


def backtest_symbol(symbol: str, monthly_df: pd.DataFrame, weekly_df: pd.DataFrame) -> BacktestResult:
    """Simulate the hybrid trade plan on the symbol's first historical multi-year breakout."""
    pos, res = find_breakout_month(monthly_df)
    if pos is None:
        return BacktestResult(symbol=symbol, found=False, reason="no_valid_breakout")

    bar = monthly_df.iloc[pos]
    breakout_date = monthly_df.index[pos]
    entry = float(bar["Close"])
    sl = tm.stop_loss(float(bar["Low"]))
    t1 = tm.target_1(res.resistance, res.support)
    forward = monthly_df.iloc[pos + 1:]

    peak = entry
    t1_reached = False
    t1_date = None
    for dt, row in forward.iterrows():
        peak = max(peak, float(row["High"]))
        if not t1_reached:
            if float(row["Low"]) <= sl:  # stopped out before T1 -> full LOSS
                ret = (sl - entry) / entry * 100.0
                return BacktestResult(
                    symbol=symbol, found=True, reason="stopped_before_t1",
                    breakout_date=breakout_date.strftime("%Y-%m-%d"), entry=round(entry, 2),
                    stop_loss=sl, target_1=t1, resistance=res.resistance, support=res.support,
                    resistance_age_years=res.age_years, peak_price=round(peak, 2),
                    exit_price=sl, return_pct=round(ret, 2),
                    holding_months=_months_between(breakout_date, dt), outcome="LOSS",
                )
            if float(row["High"]) >= t1:
                t1_reached = True
                t1_date = dt
                break

    if not t1_reached:
        last_close = float(monthly_df["Close"].iloc[-1])
        ret = (last_close - entry) / entry * 100.0
        return BacktestResult(
            symbol=symbol, found=True, reason="t1_not_reached",
            breakout_date=breakout_date.strftime("%Y-%m-%d"), entry=round(entry, 2),
            stop_loss=sl, target_1=t1, resistance=res.resistance, support=res.support,
            resistance_age_years=res.age_years, peak_price=round(peak, 2),
            exit_price=round(last_close, 2), return_pct=round(ret, 2),
            holding_months=_months_between(breakout_date, monthly_df.index[-1]), outcome="OPEN",
        )

    # T1 reached: book 50% at T1, trail the rest on the weekly 21-EMA.
    trail_price, trail_date, triggered = _weekly_trail_exit(weekly_df, t1_date)
    if trail_price is None:
        trail_price, trail_date = t1, t1_date  # no weekly data -> treat as fully exited at T1

    r_t1 = (t1 - entry) / entry
    r_trail = (trail_price - entry) / entry
    blended = (C.T1_EXIT_FRACTION * r_t1 + (1 - C.T1_EXIT_FRACTION) * r_trail) * 100.0
    exit_repr = round(C.T1_EXIT_FRACTION * t1 + (1 - C.T1_EXIT_FRACTION) * trail_price, 2)
    end_date = trail_date if triggered else monthly_df.index[-1]

    return BacktestResult(
        symbol=symbol, found=True,
        reason="hybrid_exit" if triggered else "rode_to_end",
        breakout_date=breakout_date.strftime("%Y-%m-%d"), entry=round(entry, 2),
        stop_loss=sl, target_1=t1, resistance=res.resistance, support=res.support,
        resistance_age_years=res.age_years, peak_price=round(peak, 2),
        exit_price=exit_repr, return_pct=round(blended, 2),
        holding_months=_months_between(breakout_date, end_date), outcome="WIN",
    )


def _months_between(a: pd.Timestamp, b: pd.Timestamp) -> int:
    return abs((b.year - a.year) * 12 + (b.month - a.month))
