"""Integration-style tests for the composed per-symbol screening pipeline (synthetic data)."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import screener as sc


def _base_consolidation(n_pre=84, base_vol=2_000_000):
    """7-year base bouncing 150..220, ceiling 220 tested at months 6/30/54/78, dip to 150 once."""
    dates = pd.date_range("2018-01-31", periods=n_pre, freq="ME")
    touch_idx = {6, 30, 54, 78}
    rows = []
    for i in range(n_pre):
        if i in touch_idx:
            o, h, l, c = 205.0, 220.0, 200.0, 215.0
        else:
            o, h, l, c = 180.0, 208.0, 165.0, 190.0
        if i == 40:
            l, c = 150.0, 150.0
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": base_vol})
    return pd.DataFrame(rows, index=dates), dates


def _append_bar(df, dates, bar):
    new_idx = dates[-1] + pd.offsets.MonthEnd(1)
    return pd.concat([df, pd.DataFrame([bar], index=[new_idx])])


def test_screen_symbol_breakout():
    base, dates = _base_consolidation()
    # Tight breakout candle: close just above resistance -> small risk, large upside -> R:R clears gate.
    df = _append_bar(base, dates, {"Open": 216, "High": 228, "Low": 215, "Close": 226, "Volume": 4_000_000})
    res = sc.screen_symbol("TESTCO", "Test Co", df, daily_df=None, delivery_pcts=[60, 65, 70])
    assert res["status"] == "BREAKOUT", res["reason"]
    assert res["Resistance"] == pytest.approx(220.0)
    assert res["Support"] == pytest.approx(150.0)
    assert res["Stop_Loss"] == pytest.approx(215 * 0.99)
    assert res["Target_1"] == pytest.approx(290.0)
    assert res["Volume_Spike_x"] == pytest.approx(2.0, abs=0.05)
    assert res["Risk_Reward"] >= 2.0
    assert res["Delivery_Rising"] == "Yes"


def test_screen_symbol_skips_oversized_candle_low_rr():
    # doc §5.3: a 40-50% one-month candle whose R:R drops below 1:2 must be SKIPPED.
    base, dates = _base_consolidation()
    df = _append_bar(base, dates, {"Open": 221, "High": 255, "Low": 219, "Close": 250, "Volume": 4_000_000})
    res = sc.screen_symbol("BIGCO", "Big Co", df, daily_df=None, delivery_pcts=[60, 65, 70])
    assert res["status"] == "REJECT" and res["step"] == 8 and "rr_below_gate" in res["reason"]


def test_screen_symbol_watchlist():
    base, dates = _base_consolidation()
    df = _append_bar(base, dates, {"Open": 214, "High": 217, "Low": 213, "Close": 216, "Volume": 2_000_000})
    res = sc.screen_symbol("NEARCO", "Near Co", df, daily_df=None, delivery_pcts=[55])
    assert res["status"] == "WATCHLIST", res["reason"]
    assert 0 < res["Distance_to_Breakout_Pct"] <= 3.0
    assert res["Priority_Score"] is not None


def test_screen_symbol_reject_short_history():
    base, dates = _base_consolidation(n_pre=40)
    df = _append_bar(base, dates, {"Open": 221, "High": 255, "Low": 219, "Close": 250, "Volume": 4_000_000})
    res = sc.screen_symbol("YOUNGCO", "Young Co", df, daily_df=None, delivery_pcts=[70])
    assert res["status"] == "REJECT"
    assert res["step"] in (1, 4)  # too-short listing / insufficient resistance history


def test_screen_symbol_reject_weak_close_candle():
    base, dates = _base_consolidation()
    # Closes only 0.45% above resistance -> weak-close reject at STEP 7.
    df = _append_bar(base, dates, {"Open": 219, "High": 222, "Low": 218, "Close": 221, "Volume": 4_000_000})
    res = sc.screen_symbol("WEAKCO", "Weak Co", df, daily_df=None, delivery_pcts=[70])
    assert res["status"] == "REJECT"
    assert res["step"] == 7 and "weak_close" in res["reason"]


def test_screen_symbol_reject_missing_delivery_when_required():
    base, dates = _base_consolidation()
    df = _append_bar(base, dates, {"Open": 221, "High": 255, "Low": 219, "Close": 250, "Volume": 4_000_000})
    res = sc.screen_symbol("NODELIV", "No Deliv", df, daily_df=None, delivery_pcts=None, require_delivery=True)
    assert res["status"] == "REJECT" and res["step"] == 6
