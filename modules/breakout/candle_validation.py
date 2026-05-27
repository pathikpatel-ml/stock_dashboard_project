"""
Breakout-candle validation (doc §4) and supply-absorption bonus (doc §4.3).

After a stock passes the screening filters, the breakout monthly candle itself must be
validated. Three candle types are explicitly rejected:
  1. Weak close just above resistance (< 1.5%).
  2. Large upper wick (> 30% of range, or wick > body).
  3. Low volume (< 1.5x average of prior 3 months).

A VALID breakout requires all three: strong close (>= 2%), small wick (<= 30%, ideal < 20%),
and a volume spike (>= 1.5x).

Pure functions — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from . import constants as C


@dataclass
class CandleValidation:
    is_valid: bool
    quality: str                       # "VALID" | "INVALID"
    reasons: List[str] = field(default_factory=list)   # why invalid (empty if valid)
    flags: List[str] = field(default_factory=list)     # positive qualifiers (ideal wick, strong vol, ...)
    close_above_pct: Optional[float] = None
    upper_wick_pct: Optional[float] = None
    close_position_pct: Optional[float] = None
    volume_spike_ratio: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)


def validate_breakout_candle(
    open_: float,
    high: float,
    low: float,
    close: float,
    resistance: float,
    breakout_volume: float,
    prior_volumes: Sequence[float],
) -> CandleValidation:
    """Classify the breakout monthly candle (doc §4.1, §4.2).

    Parameters
    ----------
    open_, high, low, close : the breakout candle's OHLC.
    resistance              : the multi-year resistance level being broken.
    breakout_volume         : volume on the breakout candle.
    prior_volumes           : volumes of the months before the breakout (last 3 are used).

    Upper-wick % uses the document's explicit definition (§10.3):
        Upper Wick % = (High - Close) / (High - Low) x 100
    and additionally checks the §4.1 alternative "upper wick > body".
    """
    reasons: List[str] = []
    flags: List[str] = []

    candle_range = high - low
    if candle_range <= 0 or resistance <= 0:
        return CandleValidation(
            is_valid=False, quality="INVALID", reasons=["degenerate_candle"],
        )

    close_above_pct = (close - resistance) / resistance * 100.0
    upper_wick = high - close                       # doc §10.3
    upper_wick_pct = upper_wick / candle_range * 100.0
    body = abs(close - open_)
    close_position_pct = (close - low) / candle_range * 100.0  # 0=at low, 100=at high

    prior = np.asarray(list(prior_volumes), dtype=float)
    prior = prior[~np.isnan(prior)]
    prior3 = prior[-C.VOLUME_SPIKE_LOOKBACK:] if prior.size else prior
    avg_prior = float(np.mean(prior3)) if prior3.size else float("nan")
    volume_spike_ratio = (
        round(breakout_volume / avg_prior, 4) if avg_prior and not np.isnan(avg_prior) and avg_prior > 0
        else float("nan")
    )

    # ---- Reject rules (doc §4.1) ----
    if close_above_pct < C.WEAK_CLOSE_PCT:
        reasons.append(f"weak_close ({close_above_pct:.2f}% < {C.WEAK_CLOSE_PCT}%)")
    if upper_wick_pct > C.UPPER_WICK_REJECT_PCT or upper_wick > body:
        reasons.append(
            f"large_upper_wick ({upper_wick_pct:.1f}% of range; wick>body={upper_wick > body})"
        )
    if np.isnan(volume_spike_ratio) or volume_spike_ratio < C.VOLUME_SPIKE_MIN:
        reasons.append(
            f"low_volume (spike {volume_spike_ratio}x < {C.VOLUME_SPIKE_MIN}x)"
        )

    # ---- Valid requires a STRONG close (>= 2%), not merely "not weak" (doc §4.2) ----
    if not reasons and close_above_pct < C.STRONG_CLOSE_PCT:
        reasons.append(
            f"close_not_strong ({close_above_pct:.2f}% < {C.STRONG_CLOSE_PCT}%)"
        )

    is_valid = len(reasons) == 0

    # ---- Positive qualifiers ----
    if is_valid:
        if upper_wick_pct < C.UPPER_WICK_IDEAL_PCT:
            flags.append("ideal_marubozu_wick")
        if volume_spike_ratio >= C.VOLUME_SPIKE_STRONG:
            flags.append("strong_volume_spike")
        if close_position_pct >= C.CLOSE_UPPER_RANGE_FRAC_PCT:
            flags.append("close_in_upper_range")

    return CandleValidation(
        is_valid=is_valid,
        quality="VALID" if is_valid else "INVALID",
        reasons=reasons,
        flags=flags,
        close_above_pct=round(close_above_pct, 4),
        upper_wick_pct=round(upper_wick_pct, 4),
        close_position_pct=round(close_position_pct, 4),
        volume_spike_ratio=volume_spike_ratio,
    )


@dataclass
class SupplyAbsorption:
    present: bool
    months: int            # number of qualifying consolidation months (0-3)
    detail: str = ""


def detect_supply_absorption(
    pre_breakout_monthly: pd.DataFrame,
    resistance: float,
    proximity_pct: float = C.SUPPLY_ABSORPTION_PROXIMITY_PCT,
    range_pct: float = C.SUPPLY_ABSORPTION_RANGE_PCT,
    min_months: int = C.SUPPLY_ABSORPTION_MIN_MONTHS,
    max_months: int = C.SUPPLY_ABSORPTION_MAX_MONTHS,
) -> SupplyAbsorption:
    """Bonus signal (doc §4.3): 1-3 months of tight consolidation just below resistance.

    A month qualifies when its CLOSE is within ``proximity_pct`` of resistance AND its
    candle range (High-Low) is below ``range_pct`` of the average range over the lookback.
    We inspect the ``max_months`` bars immediately preceding the breakout candle.
    """
    if pre_breakout_monthly is None or pre_breakout_monthly.empty or resistance <= 0:
        return SupplyAbsorption(present=False, months=0, detail="no_data")

    df = pre_breakout_monthly.sort_index()
    window = df.iloc[-max_months:]
    if window.empty:
        return SupplyAbsorption(present=False, months=0, detail="no_window")

    avg_range = float((df["High"] - df["Low"]).tail(12).mean())
    if avg_range <= 0:
        return SupplyAbsorption(present=False, months=0, detail="flat_history")

    qualifying = 0
    for _, bar in window.iterrows():
        close = float(bar["Close"])
        near = abs(close - resistance) / resistance * 100.0 <= proximity_pct
        tight = (float(bar["High"]) - float(bar["Low"])) < avg_range * (range_pct / 100.0)
        if near and tight:
            qualifying += 1

    present = qualifying >= min_months
    return SupplyAbsorption(
        present=present,
        months=qualifying,
        detail=f"{qualifying} tight month(s) near resistance" if present else "not detected",
    )
