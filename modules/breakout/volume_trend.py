"""
Volume-trend classification over the 5-6 months before breakout (doc §3.3).

Rule: in the months preceding the breakout, volume must be rising — shown by a positive
regression slope OR at least 3 of the last 5 months posting above-average volume. Flat or
declining volume disqualifies the setup.

Pure functions — no I/O.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from . import constants as C

RISING = "RISING"
FLAT = "FLAT"
DECLINING = "DECLINING"


def classify_volume_trend(
    monthly_volumes: Sequence[float],
    lookback: int = C.VOLUME_TREND_LOOKBACK_MONTHS,
    window: int = C.VOLUME_TREND_WINDOW,
    min_above_avg: int = C.VOLUME_TREND_MIN_ABOVE_AVG,
    slope_eps: float = C.VOLUME_TREND_SLOPE_EPS,
) -> str:
    """Classify recent monthly volume as RISING / FLAT / DECLINING (doc §3.3).

    - ``RISING``    : relative regression slope > +eps, OR >= ``min_above_avg`` of the last
                      ``window`` months exceed the lookback average.
    - ``DECLINING`` : relative regression slope < -eps and the above-average count is short.
    - ``FLAT``      : otherwise.

    The relative slope normalises by mean volume so the band is scale-independent.
    """
    vols = np.asarray(list(monthly_volumes), dtype=float)
    vols = vols[~np.isnan(vols)]
    if vols.size < 2:
        return FLAT

    recent = vols[-lookback:]
    mean_vol = float(np.mean(recent))
    if mean_vol <= 0:
        return FLAT

    x = np.arange(recent.size, dtype=float)
    slope = float(np.polyfit(x, recent, 1)[0])
    rel_slope = slope / mean_vol  # fractional change in volume per month

    last_window = vols[-window:]
    avg = float(np.mean(recent))
    above_avg_count = int(np.sum(last_window > avg))

    if rel_slope > slope_eps or above_avg_count >= min_above_avg:
        return RISING
    if rel_slope < -slope_eps and above_avg_count < min_above_avg:
        return DECLINING
    return FLAT
