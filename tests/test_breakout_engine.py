"""
Unit tests for the Multi-Year Breakout engine pure-functions.

Assertions are tied to the worked examples and exact thresholds in the requirements
document so a regression in any rule fails loudly.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import constants as C
from modules.breakout import trade_math as tm
from modules.breakout import volume_trend as vt
from modules.breakout.candle_validation import (
    validate_breakout_candle,
    detect_supply_absorption,
)
from modules.breakout.resistance import detect_resistance, is_uptrend_dow


# ---------------------------------------------------------------------------
# Trade math — doc §6.1, §7.1, §5.3, §10.3
# ---------------------------------------------------------------------------
def test_stop_loss_doc_example():
    # doc §6.1: low 200 -> 200 * 0.99 = 198
    assert tm.stop_loss(200) == 198.0


def test_range_and_target_doc_example():
    # doc §7.1: resistance 220, support 150 -> range 70, T1 290
    assert tm.range_size(220, 150) == 70
    assert tm.target_1(220, 150) == 290.0


def test_risk_reward_and_gate():
    # entry 220, SL 198, T1 290 -> (290-220)/(220-198) = 70/22 = 3.18 -> passes 1:2
    rr = tm.risk_reward(entry=220, stop=198, target=290)
    assert rr == pytest.approx(3.1818, abs=1e-3)
    assert tm.passes_rr_gate(rr) is True

    # A very large breakout candle shrinks upside: entry 250 -> RR 0.77 -> SKIP (doc §5.3)
    rr_bad = tm.risk_reward(entry=250, stop=198, target=290)
    assert tm.passes_rr_gate(rr_bad) is False

    # Just-below-gate case: entry 230 -> 60/32 = 1.875 < 2 -> SKIP
    assert tm.passes_rr_gate(tm.risk_reward(230, 198, 290)) is False


def test_distance_to_breakout():
    # CMP 100, resistance 103 -> 3% away
    assert tm.distance_to_breakout(100, 103) == pytest.approx(3.0)


def test_priority_score_literal_formula():
    # age 13y, delivery 65%, distance 3% -> 13*0.3 + 65*0.4 + (1-0.03)*0.3
    expected = 13 * 0.3 + 65 * 0.4 + (1 - 0.03) * 0.3
    assert tm.priority_score(13, 65, 3) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 21-EMA weekly trailing — doc §7.2, §12.3
# ---------------------------------------------------------------------------
def test_weekly_trailing_hold_then_exit_then_reset():
    base = [10.0] * 30

    one_below = base + [9.0]
    st1 = tm.evaluate_weekly_trailing(one_below)
    assert st1.consecutive_below == 1 and st1.exit_signal is False  # 1 close below -> hold

    two_below = base + [9.0, 9.0]
    st2 = tm.evaluate_weekly_trailing(two_below)
    assert st2.consecutive_below == 2 and st2.exit_signal is True   # 2 consecutive -> exit

    reset = base + [9.0, 9.0, 11.0]
    st3 = tm.evaluate_weekly_trailing(reset)
    assert st3.consecutive_below == 0 and st3.exit_signal is False  # close above -> reset


def test_weekly_ema_matches_pandas_ewm():
    closes = np.linspace(100, 200, 60)
    expected = pd.Series(closes).ewm(span=21, adjust=False).mean().to_numpy()
    np.testing.assert_allclose(tm.weekly_ema(closes), expected)


# ---------------------------------------------------------------------------
# Volume trend — doc §3.3
# ---------------------------------------------------------------------------
def test_volume_trend_classes():
    assert vt.classify_volume_trend([100, 110, 120, 130, 140, 160]) == vt.RISING
    assert vt.classify_volume_trend([200, 180, 160, 140, 120, 100]) == vt.DECLINING
    assert vt.classify_volume_trend([100, 101, 99, 100, 100, 100]) == vt.FLAT


# ---------------------------------------------------------------------------
# Breakout candle validation — doc §4
# ---------------------------------------------------------------------------
PRIOR_VOL = [100_000, 110_000, 120_000]  # mean 110,000


def test_valid_breakout_candle():
    res = validate_breakout_candle(
        open_=221, high=255, low=219, close=250, resistance=220,
        breakout_volume=300_000, prior_volumes=PRIOR_VOL,
    )
    assert res.is_valid is True and res.quality == "VALID"
    assert "ideal_marubozu_wick" in res.flags
    assert "strong_volume_spike" in res.flags
    assert res.volume_spike_ratio == pytest.approx(2.7273, abs=1e-3)


def test_reject_weak_close():
    res = validate_breakout_candle(
        open_=219, high=224, low=218, close=222, resistance=220,
        breakout_volume=300_000, prior_volumes=PRIOR_VOL,
    )
    assert res.is_valid is False
    assert any("weak_close" in r for r in res.reasons)


def test_reject_large_upper_wick():
    res = validate_breakout_candle(
        open_=221, high=290, low=219, close=250, resistance=220,
        breakout_volume=300_000, prior_volumes=PRIOR_VOL,
    )
    assert res.is_valid is False
    assert any("large_upper_wick" in r for r in res.reasons)


def test_reject_low_volume():
    res = validate_breakout_candle(
        open_=221, high=255, low=219, close=250, resistance=220,
        breakout_volume=100_000, prior_volumes=PRIOR_VOL,  # 0.91x < 1.5x
    )
    assert res.is_valid is False
    assert any("low_volume" in r for r in res.reasons)


# ---------------------------------------------------------------------------
# Resistance detection — doc §12.2
# ---------------------------------------------------------------------------
def _build_synthetic_monthly():
    """7 years of monthly bars bouncing between ~150 support and ~220 resistance,
    with the 220 ceiling tested at months 6/30/54/78, then a breakout to 250."""
    n_pre = 84
    dates = pd.date_range("2018-01-31", periods=n_pre + 1, freq="ME")
    touch_idx = {6, 30, 54, 78}
    rows = []
    for i in range(n_pre):
        if i in touch_idx:
            high, low, close, open_ = 220.0, 200.0, 215.0, 205.0  # tests resistance
        else:
            high, low, close, open_ = 208.0, 165.0, 190.0, 180.0  # inside the range
        if i == 40:
            low, close = 150.0, 150.0  # consolidation floor -> support
        rows.append({"Open": open_, "High": high, "Low": low, "Close": close,
                     "Volume": 100_000 + i * 100})
    # Breakout candle
    rows.append({"Open": 221.0, "High": 255.0, "Low": 219.0, "Close": 250.0, "Volume": 400_000})
    return pd.DataFrame(rows, index=dates)


def test_detect_resistance_synthetic():
    df = _build_synthetic_monthly()
    info = detect_resistance(df)
    assert info.valid is True, info.reason
    assert info.resistance == pytest.approx(220.0)
    assert info.support == pytest.approx(150.0)
    assert info.range_size == pytest.approx(70.0)
    assert info.n_tests >= 4
    assert info.age_months >= C.MIN_RESISTANCE_AGE_MONTHS
    assert info.age_years >= 5


def test_detect_resistance_rejects_short_history():
    df = _build_synthetic_monthly().iloc[-30:]  # < 60 months
    info = detect_resistance(df)
    assert info.valid is False
    assert "insufficient_history" in info.reason


def test_uptrend_dow_true_for_breakout_series():
    df = _build_synthetic_monthly()
    assert is_uptrend_dow(df) is True


def test_uptrend_dow_rejects_lower_highs_downtrend():
    # A clear downtrend: peaks step down month over month (Lower Highs) -> forbidden.
    idx = pd.date_range("2022-01-31", periods=24, freq="ME")
    highs = np.linspace(300, 120, 24)
    rows = [{"Open": h - 10, "High": h, "Low": h - 30, "Close": h - 20, "Volume": 1} for h in highs]
    df = pd.DataFrame(rows, index=idx)
    assert is_uptrend_dow(df) is False


def test_supply_absorption_detection():
    # Three tight months whose close sits within 3% of resistance 220.
    idx = pd.date_range("2024-01-31", periods=12, freq="ME")
    rows = [{"Open": 180, "High": 210, "Low": 160, "Close": 185, "Volume": 1} for _ in range(9)]
    rows += [{"Open": 217, "High": 219, "Low": 215, "Close": 218, "Volume": 1} for _ in range(3)]
    df = pd.DataFrame(rows, index=idx)
    sa = detect_supply_absorption(df, resistance=220)
    assert sa.present is True and sa.months == 3
