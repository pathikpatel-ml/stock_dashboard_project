"""Tests for the historical backtest simulation (WIN / LOSS outcomes)."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import backtest as bt
from modules.breakout import positions as pos


def _base():
    dates = pd.date_range("2015-01-31", periods=84, freq="ME")
    touch_idx = {6, 30, 54, 78}
    rows = []
    for i in range(84):
        if i in touch_idx:
            o, h, l, c = 205.0, 220.0, 200.0, 215.0
        else:
            o, h, l, c = 180.0, 208.0, 165.0, 190.0
        if i == 40:
            l, c = 150.0, 150.0
        rows.append({"Open": o, "High": h, "Low": l, "Close": c, "Volume": 2_000_000})
    return pd.DataFrame(rows, index=dates), dates


def _with_forward(forward_bars):
    base, dates = _base()
    breakout = {"Open": 216, "High": 228, "Low": 215, "Close": 226, "Volume": 4_000_000}
    idx = list(dates) + [dates[-1] + pd.offsets.MonthEnd(k) for k in range(1, len(forward_bars) + 2)]
    rows = base.to_dict("records") + [breakout] + forward_bars
    return pd.DataFrame(rows, index=pd.DatetimeIndex(idx[: len(rows)]))


def test_backtest_win_reaches_t1():
    # Climb to T1 = 290 without touching SL (212.85) -> WIN.
    forward = [
        {"Open": 230, "High": 250, "Low": 225, "Close": 245, "Volume": 3_000_000},
        {"Open": 250, "High": 275, "Low": 245, "Close": 270, "Volume": 3_000_000},
        {"Open": 275, "High": 295, "Low": 268, "Close": 292, "Volume": 3_000_000},
    ]
    df = _with_forward(forward)
    res = bt.backtest_symbol("WINCO", df, weekly_df=pd.DataFrame())
    assert res.found is True and res.outcome == "WIN", res.reason
    assert res.target_1 == pytest.approx(290.0)
    assert res.return_pct > 0


def test_backtest_loss_stops_before_t1():
    # Next month collapses through SL (low 200 < 212.85) before T1 -> LOSS.
    forward = [{"Open": 224, "High": 227, "Low": 200, "Close": 205, "Volume": 3_000_000}]
    df = _with_forward(forward)
    res = bt.backtest_symbol("LOSSCO", df, weekly_df=pd.DataFrame())
    assert res.found is True and res.outcome == "LOSS", res.reason
    assert res.return_pct < 0


def test_track_positions_metrics_and_sl_status():
    positions = pd.DataFrame(
        [{"Symbol": "ABC", "Entry_Date": "2026-01-01", "Entry_Price": 100.0,
          "Stop_Loss": 95.0, "Target_1": 130.0, "Quantity": 10,
          "Status": "OPEN", "T1_Reached": "No", "Notes": ""}]
    )
    tracked = pos.track_positions(positions, cmp_lookup={"ABC": 110.0})
    row = tracked.iloc[0]
    assert row["P&L %"] == pytest.approx(10.0)
    assert row["SL Status"] == "Green"          # 110 is >3% above 95
    assert row["T1 Status"] == "Not Reached"

    tracked2 = pos.track_positions(positions, cmp_lookup={"ABC": 96.0})
    assert tracked2.iloc[0]["SL Status"] == "Yellow"   # within 3% of SL
    tracked3 = pos.track_positions(positions, cmp_lookup={"ABC": 94.0})
    assert tracked3.iloc[0]["SL Status"] == "Red"      # SL hit
