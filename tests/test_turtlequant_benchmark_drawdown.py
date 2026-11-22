"""
Unit tests for modules/turtlequant/benchmark_drawdown.py (2026-11-22) -- the Nifty-50-anchored
ATH/52-week-low drawdown comparison. Pure functions, no I/O: all corner cases (None handling,
holiday/listing gaps, zero-price, missing reference) are exercised directly.
"""
import os
import sys
from datetime import date

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtlequant import benchmark_drawdown as bd


# ---------------------------------------------------------------------------
# pct_return
# ---------------------------------------------------------------------------
def test_pct_return_basic_gain():
    assert bd.pct_return(100, 120) == pytest.approx(20.0)


def test_pct_return_basic_loss():
    assert bd.pct_return(100, 80) == pytest.approx(-20.0)


def test_pct_return_none_start_is_none():
    assert bd.pct_return(None, 100) is None


def test_pct_return_none_end_is_none():
    assert bd.pct_return(100, None) is None


def test_pct_return_nan_is_none():
    assert bd.pct_return(float("nan"), 100) is None
    assert bd.pct_return(100, float("nan")) is None


def test_pct_return_zero_start_is_none():
    assert bd.pct_return(0, 100) is None


def test_pct_return_unchanged_is_zero():
    assert bd.pct_return(100, 100) == 0.0


# ---------------------------------------------------------------------------
# nifty_reference_from_ohlc
# ---------------------------------------------------------------------------
def _ohlc(rows):
    """rows: list of (date_str, high, low, close)."""
    idx = pd.DatetimeIndex([r[0] for r in rows])
    return pd.DataFrame(
        {"High": [r[1] for r in rows], "Low": [r[2] for r in rows], "Close": [r[3] for r in rows]},
        index=idx,
    )


def test_nifty_reference_picks_high_for_ath_not_close():
    # Real live incident (2026-11-22): the ATH date/price must come from the High column, one
    # day AFTER the highest Close in this example -- matches the confirmed real-world case
    # (Nifty's true ATH was 2026-01-05's High, not 2026-01-02's higher Close).
    ohlc = _ohlc([
        ("2026-01-01", 100, 95, 98),
        ("2026-01-02", 101, 96, 99),   # highest CLOSE, but not the highest High
        ("2026-01-05", 105, 97, 97.5),  # highest HIGH -- this is the real ATH
    ])
    ref = bd.nifty_reference_from_ohlc(ohlc, window_weeks=1)
    assert ref["ath_price"] == 105
    assert ref["ath_date"] == date(2026, 1, 5)


def test_nifty_reference_52wk_low_uses_low_not_close_within_trailing_window():
    ohlc = _ohlc([
        ("2026-01-01", 110, 90, 105),  # lowest LOW, within the trailing window
        ("2026-01-08", 112, 100, 108),
        ("2026-01-15", 113, 101, 110),  # latest -- "today"
    ])
    ref = bd.nifty_reference_from_ohlc(ohlc, window_weeks=52)
    assert ref["low_52wk_price"] == 90
    assert ref["low_52wk_date"] == date(2026, 1, 1)


def test_nifty_reference_52wk_low_excludes_older_rows_outside_the_window():
    ohlc = _ohlc([
        ("2020-01-01", 50, 10, 45),      # ancient low, OUTSIDE the trailing 52-week window
        ("2026-01-01", 110, 90, 105),
        ("2026-06-01", 112, 95, 108),
        ("2026-11-20", 113, 100, 110),  # latest -- "today"
    ])
    ref = bd.nifty_reference_from_ohlc(ohlc, window_weeks=52)
    assert ref["low_52wk_price"] == 90  # the 2020 row (10) must NOT be picked
    assert ref["ath_price"] == 113      # ATH still scans the FULL history, unlike the low


def test_nifty_reference_today_is_latest_close_and_date():
    ohlc = _ohlc([
        ("2026-01-01", 100, 90, 95),
        ("2026-11-20", 103, 99, 101.5),
    ])
    ref = bd.nifty_reference_from_ohlc(ohlc, window_weeks=52)
    assert ref["today_price"] == 101.5
    assert ref["today_date"] == date(2026, 11, 20)


def test_nifty_reference_empty_df_returns_none():
    assert bd.nifty_reference_from_ohlc(pd.DataFrame()) is None


def test_nifty_reference_none_returns_none():
    assert bd.nifty_reference_from_ohlc(None) is None


def test_nifty_reference_missing_required_column_returns_none():
    df = pd.DataFrame({"Close": [100, 101]}, index=pd.DatetimeIndex(["2026-01-01", "2026-01-02"]))
    assert bd.nifty_reference_from_ohlc(df) is None


def test_nifty_reference_all_nan_rows_returns_none():
    ohlc = _ohlc([("2026-01-01", float("nan"), float("nan"), float("nan"))])
    assert bd.nifty_reference_from_ohlc(ohlc) is None


def test_nifty_reference_picks_up_a_new_later_ath_automatically():
    # 2026-11-22, per explicit user request: confirms there's no caching/hardcoding of the
    # reference date -- re-running nifty_reference_from_ohlc on a LATER day's data (e.g. Nifty
    # just made a fresh all-time high) must find the NEW ATH date/price, not the old one. This
    # is the same pure function the daily batch job calls fresh every run, so "does it pick up
    # a changed ATH/52wk-low" reduces to "does this function see the new max/min" -- it does,
    # since it always recomputes from whatever OHLC it's given, never from a stored value.
    old_ath = _ohlc([
        ("2026-01-05", 105, 97, 97.5),  # the OLD all-time-high
        ("2026-06-01", 102, 95, 100),
    ])
    assert bd.nifty_reference_from_ohlc(old_ath, window_weeks=1)["ath_price"] == 105

    new_ath = _ohlc([
        ("2026-01-05", 105, 97, 97.5),   # yesterday's ATH
        ("2026-06-01", 102, 95, 100),
        ("2026-11-22", 130, 120, 128),   # today -- a BRAND NEW, higher all-time-high
    ])
    ref = bd.nifty_reference_from_ohlc(new_ath, window_weeks=1)
    assert ref["ath_price"] == 130
    assert ref["ath_date"] == date(2026, 11, 22)


def test_nifty_reference_52wk_low_rolls_forward_as_the_window_moves():
    # Similarly: as "today" advances, an old low that's now OUTSIDE the trailing 52-week
    # window must stop being picked, even though it's still the lowest Low in the full series.
    ohlc = _ohlc([
        ("2025-01-01", 110, 50, 105),    # the lowest Low ever, but will fall out of the window
        ("2026-01-01", 110, 90, 105),
        ("2026-11-22", 113, 100, 110),   # "today" -- window now starts ~52 weeks before this
    ])
    ref = bd.nifty_reference_from_ohlc(ohlc, window_weeks=52)
    assert ref["low_52wk_price"] == 90  # not 50 -- the 2025 row aged out of the window
    assert ref["low_52wk_date"] == date(2026, 1, 1)


def test_nifty_reference_trailing_window_falls_back_to_full_series_if_empty():
    # window_weeks absurdly small relative to the data's own spacing shouldn't matter here --
    # this covers the defensive "trailing window ended up empty" fallback path directly.
    ohlc = _ohlc([("2026-01-01", 100, 90, 95)])
    ref = bd.nifty_reference_from_ohlc(ohlc, window_weeks=0)
    assert ref["low_52wk_price"] == 90


# ---------------------------------------------------------------------------
# price_on_or_before
# ---------------------------------------------------------------------------
def _close(rows):
    idx = pd.DatetimeIndex([r[0] for r in rows])
    return pd.Series([r[1] for r in rows], index=idx)


def test_price_on_or_before_exact_date_match():
    series = _close([("2026-01-01", 10), ("2026-01-05", 15), ("2026-01-10", 20)])
    assert bd.price_on_or_before(series, "2026-01-05") == 15


def test_price_on_or_before_falls_back_to_nearest_prior_trading_day():
    # Target date 01-06 has no row (holiday/gap) -- must fall back to 01-05, not 01-10.
    series = _close([("2026-01-01", 10), ("2026-01-05", 15), ("2026-01-10", 20)])
    assert bd.price_on_or_before(series, "2026-01-06") == 15


def test_price_on_or_before_no_data_before_target_returns_none():
    # Stock listed AFTER the target reference date -- e.g. a recent IPO.
    series = _close([("2026-06-01", 50)])
    assert bd.price_on_or_before(series, "2026-01-05") is None


def test_price_on_or_before_empty_series_returns_none():
    assert bd.price_on_or_before(pd.Series(dtype=float), "2026-01-05") is None


def test_price_on_or_before_none_series_returns_none():
    assert bd.price_on_or_before(None, "2026-01-05") is None


def test_price_on_or_before_drops_nan_values_before_searching():
    series = _close([("2026-01-01", 10), ("2026-01-05", float("nan")), ("2026-01-06", 16)])
    # 01-05 is NaN, so the nearest valid price at/before 01-05 is 01-01's 10.
    assert bd.price_on_or_before(series, "2026-01-05") == 10


# ---------------------------------------------------------------------------
# compute_stock_drawdown
# ---------------------------------------------------------------------------
_NIFTY_REF = {
    "ath_price": 200.0, "ath_date": date(2026, 1, 5),
    "low_52wk_price": 150.0, "low_52wk_date": date(2026, 10, 8),
    "today_price": 190.0, "today_date": date(2026, 11, 20),
}


def test_compute_stock_drawdown_full_example_matches_hand_calculation():
    # Stock: High=100 on ATH date, Low=80 on 52wk-low date, Close=90 today -- same price-type
    # convention as Nifty's own reference (High for ATH, Low for the 52wk-low, Close for today).
    stock_ohlc = _ohlc([
        ("2026-01-05", 100, 95, 98),
        ("2026-10-08", 85, 80, 82),
        ("2026-11-20", 92, 88, 90),
    ])
    result = bd.compute_stock_drawdown(stock_ohlc, _NIFTY_REF)

    # Nifty ATH->today: (190/200-1)*100 = -5.0; stock: (90/100-1)*100 = -10.0
    assert result["stock_ath_return_pct"] == -10.0
    assert result["rs_vs_nifty_ath"] == pytest.approx(-10.0 - (-5.0), abs=1e-9)

    # Nifty low->today: (190/150-1)*100 = 26.666...7; stock: (90/80-1)*100 = 12.5
    assert result["stock_52wklow_return_pct"] == 12.5
    nifty_low_return = (190 / 150 - 1) * 100
    assert result["rs_vs_nifty_52wklow"] == pytest.approx(round(12.5 - nifty_low_return, 2), abs=1e-6)


def test_compute_stock_drawdown_outperform_example_from_user_illustration():
    # The user's own illustration: Nifty down 30% from ATH, stock down only 20% -> stock
    # outperforms (positive rs_vs_nifty_ath).
    nifty_ref = {
        "ath_price": 100.0, "ath_date": date(2026, 1, 5),
        "low_52wk_price": 100.0, "low_52wk_date": date(2026, 10, 8),
        "today_price": 70.0, "today_date": date(2026, 11, 20),  # Nifty -30% from ATH
    }
    stock_ohlc = _ohlc([
        ("2026-01-05", 100, 90, 95),
        ("2026-10-08", 105, 100, 98),
        ("2026-11-20", 85, 78, 80),   # Close=80 -> stock -20%
    ])
    result = bd.compute_stock_drawdown(stock_ohlc, nifty_ref)
    assert result["stock_ath_return_pct"] == -20.0
    assert result["rs_vs_nifty_ath"] == pytest.approx(10.0)  # -20 - (-30) = +10, outperform
    assert result["rs_vs_nifty_ath"] > 0


def test_compute_stock_drawdown_none_nifty_ref_returns_all_none():
    stock_ohlc = _ohlc([("2026-01-05", 100, 95, 98)])
    result = bd.compute_stock_drawdown(stock_ohlc, None)
    assert all(v is None for v in result.values())
    assert set(result) == set(bd.DRAWDOWN_FIELDS)


def test_compute_stock_drawdown_stock_missing_history_returns_all_none():
    # Stock listed after all 3 reference dates -- no usable anchor price at all.
    stock_ohlc = _ohlc([("2026-12-01", 105, 95, 100)])
    result = bd.compute_stock_drawdown(stock_ohlc, _NIFTY_REF)
    assert result["stock_ath_return_pct"] is None
    assert result["rs_vs_nifty_ath"] is None
    assert result["stock_52wklow_return_pct"] is None
    assert result["rs_vs_nifty_52wklow"] is None


def test_compute_stock_drawdown_none_ohlc_returns_all_none():
    result = bd.compute_stock_drawdown(None, _NIFTY_REF)
    assert all(v is None for v in result.values())


def test_compute_stock_drawdown_partial_history_only_one_reference_reachable():
    # Stock has data back to the 52wk-low date but NOT back to the (earlier) ATH date --
    # ATH-anchored fields are None, 52wk-low-anchored fields are still computed.
    stock_ohlc = _ohlc([("2026-10-08", 85, 80, 82), ("2026-11-20", 92, 88, 90)])
    result = bd.compute_stock_drawdown(stock_ohlc, _NIFTY_REF)
    assert result["stock_ath_return_pct"] is None
    assert result["rs_vs_nifty_ath"] is None
    assert result["stock_52wklow_return_pct"] == 12.5
    assert result["rs_vs_nifty_52wklow"] is not None


def test_compute_stock_drawdown_missing_ohlc_column_treated_as_unavailable():
    # A frame with only Close (e.g. an upstream shape change) -- High/Low-anchored fields must
    # degrade to None, not raise, since _column_or_none can't find those columns.
    stock_close_only = pd.DataFrame(
        {"Close": [98.0, 90.0]}, index=pd.DatetimeIndex(["2026-01-05", "2026-11-20"]),
    )
    result = bd.compute_stock_drawdown(stock_close_only, _NIFTY_REF)
    assert result["stock_ath_return_pct"] is None  # needs High, which isn't there
    assert result["rs_vs_nifty_ath"] is None
