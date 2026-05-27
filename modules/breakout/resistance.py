"""
Multi-year horizontal resistance / support detection (doc §3.1, §8.3, §12.2).

Given monthly OHLCV for a stock, find the highest horizontal resistance level that:
  * is at or within 5% of the (prior) all-time high,
  * has been tested (monthly high within 2%) at least 2 times, and
  * is at least 5 years (60 months) old.

The "breakout candle" is the most recent monthly bar by default; resistance is detected
from the history *before* that candle (the level the breakout candle breaks above).

Pure function — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import constants as C


@dataclass
class ResistanceInfo:
    valid: bool
    reason: str
    resistance: Optional[float] = None
    support: Optional[float] = None
    range_size: Optional[float] = None
    age_years: Optional[float] = None
    age_months: Optional[int] = None
    n_tests: Optional[int] = None
    ath: Optional[float] = None
    first_test_date: Optional[str] = None
    last_test_date: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def _cluster_highs(highs: pd.Series, tol_pct: float) -> List[Dict]:
    """Greedy top-down clustering of monthly highs.

    Sort highs descending; a high joins an existing cluster when it is within ``tol_pct``
    of that cluster's representative level (the cluster's max). Highest highs cluster first,
    so the topmost cluster naturally represents the near-ATH resistance zone.

    Returns a list of clusters: {level, touches, dates:[Timestamp,...]}.
    """
    clusters: List[Dict] = []
    for date, high in highs.sort_values(ascending=False).items():
        high = float(high)
        placed = False
        for cluster in clusters:
            if abs(high - cluster["level"]) / cluster["level"] * 100.0 <= tol_pct:
                cluster["touches"] += 1
                cluster["dates"].append(date)
                if high > cluster["level"]:
                    cluster["level"] = high
                placed = True
                break
        if not placed:
            clusters.append({"level": high, "touches": 1, "dates": [date]})
    return clusters


def detect_resistance(
    monthly_df: pd.DataFrame,
    as_of_index: int = -1,
    tol_pct: float = C.RESISTANCE_CLUSTER_TOLERANCE_PCT,
    min_touches: int = C.MIN_RESISTANCE_TOUCHES,
    ath_proximity_pct: float = C.ATH_PROXIMITY_PCT,
    min_age_months: int = C.MIN_RESISTANCE_AGE_MONTHS,
) -> ResistanceInfo:
    """Detect the multi-year horizontal resistance as of ``as_of_index`` (default: latest bar).

    Parameters
    ----------
    monthly_df : DataFrame indexed by month-end Timestamp with columns
                 High, Low, Close (Open/Volume optional).
    as_of_index : integer position of the breakout candle; resistance is detected from
                  bars *before* it. -1 (default) treats the last bar as the breakout.

    Returns a ``ResistanceInfo``; ``valid`` is True only when every Filter-1/2 condition holds.
    """
    if monthly_df is None or monthly_df.empty:
        return ResistanceInfo(valid=False, reason="no_data")

    required = {"High", "Low", "Close"}
    if not required.issubset(monthly_df.columns):
        return ResistanceInfo(valid=False, reason="missing_columns")

    df = monthly_df.sort_index()
    n = len(df)
    pos = as_of_index if as_of_index >= 0 else n + as_of_index
    if pos <= 0 or pos >= n:
        # Need at least the breakout bar plus prior history.
        if pos <= 0:
            return ResistanceInfo(valid=False, reason="breakout_bar_at_start")

    breakout_bar = df.iloc[pos]
    breakout_date = df.index[pos]
    pre = df.iloc[:pos]  # history strictly before the breakout candle

    if len(pre) < min_age_months:
        return ResistanceInfo(
            valid=False,
            reason=f"insufficient_history ({len(pre)} months < {min_age_months})",
        )

    highs = pre["High"].astype(float)
    ath_pre = float(highs.max())
    if ath_pre <= 0:
        return ResistanceInfo(valid=False, reason="non_positive_ath")

    clusters = _cluster_highs(highs, tol_pct)
    tested = [c for c in clusters if c["touches"] >= min_touches]
    near_ath = [
        c for c in tested
        if (ath_pre - c["level"]) / ath_pre * 100.0 <= ath_proximity_pct
    ]
    if not near_ath:
        return ResistanceInfo(
            valid=False,
            reason="no_multi-tested_resistance_within_5pct_of_ATH",
            ath=round(ath_pre, 4),
        )

    # Highest qualifying cluster near the ATH = the resistance being broken.
    res_cluster = max(near_ath, key=lambda c: c["level"])
    resistance = round(float(res_cluster["level"]), 4)
    dates = sorted(res_cluster["dates"])
    first_test_date = dates[0]
    last_test_date = dates[-1]

    # Resistance age: months from first test to the breakout candle (doc §12.2 step 6).
    age_months = (breakout_date.year - first_test_date.year) * 12 + (
        breakout_date.month - first_test_date.month
    )
    age_years = round(age_months / 12.0, 2)

    # Support: lowest CLOSE during the consolidation (first test -> breakout) (doc §7.1, §10.3).
    consolidation = pre[(pre.index >= first_test_date)]
    support = round(float(consolidation["Close"].astype(float).min()), 4)

    valid = age_months >= min_age_months and res_cluster["touches"] >= min_touches
    reason = "ok" if valid else f"resistance_age {age_months}m < {min_age_months}m"

    return ResistanceInfo(
        valid=valid,
        reason=reason,
        resistance=resistance,
        support=support,
        range_size=round(resistance - support, 4),
        age_years=age_years,
        age_months=age_months,
        n_tests=int(res_cluster["touches"]),
        ath=round(ath_pre, 4),
        first_test_date=pd.Timestamp(first_test_date).strftime("%Y-%m-%d"),
        last_test_date=pd.Timestamp(last_test_date).strftime("%Y-%m-%d"),
    )


def is_uptrend_dow(monthly_df: pd.DataFrame, lookback: int = 12, tol_pct: float = 2.0) -> bool:
    """Dow-Theory guard (doc §3.2): reject only stocks making **Lower Highs** (downtrend).

    The doc forbids buying Lower-High setups, but this strategy deliberately targets stocks
    that have spent years range-bound just below resistance — those do NOT make Higher Lows
    during the base, so a strict Higher-High-AND-Higher-Low test would wrongly reject valid
    setups. We therefore reject only a clear *lower high*: the recent swing high being
    materially (> ``tol_pct``) below the prior window's swing high. A breakout to a new ATH is
    a higher high by definition and passes; the ATH proximity filter (doc §3.2 STEP 3) does the
    rest of the downtrend-recovery rejection.
    """
    if monthly_df is None or len(monthly_df) < lookback * 2:
        return True  # not enough history to disprove; defer to other filters
    df = monthly_df.sort_index()
    recent_high = float(df.iloc[-lookback:]["High"].max())
    prior_high = float(df.iloc[-lookback * 2:-lookback]["High"].max())
    if prior_high <= 0:
        return True
    return recent_high >= prior_high * (1.0 - tol_pct / 100.0)
