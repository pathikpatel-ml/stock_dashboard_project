"""
Unit tests for the Turtle Strategy pure-functions (modules/turtle/compute.py).

Mirrors tests/test_breakout_engine.py's style: plain asserts, pytest.approx for floats,
synthetic in-memory data only, no network, no mocking of pure functions.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import compute as tt


# ---------------------------------------------------------------------------
# Classifier truth table (plan §1) — exhaustive
# ---------------------------------------------------------------------------
def test_classify_add_all_three_true():
    assert tt.classify(ath_price=True, ath_profit=True, above_exit=True, outperformance=True) == "ADD"
    # ADD doesn't depend on Above-Exit at all -- still ADD with above_exit False.
    assert tt.classify(ath_price=True, ath_profit=True, above_exit=False, outperformance=True) == "ADD"


def test_classify_hold_two_of_three_combos():
    # {ath_profit, above_exit} true, outperformance false
    assert tt.classify(ath_price=False, ath_profit=True, above_exit=True, outperformance=False) == "HOLD"
    # {ath_profit, outperformance} true, above_exit false -- and ath_price False so ADD's
    # extra requirement (ATH Price) is what keeps this out of ADD, not the HOLD set itself.
    assert tt.classify(ath_price=False, ath_profit=True, above_exit=False, outperformance=True) == "HOLD"
    # {above_exit, outperformance} true, ath_profit false
    assert tt.classify(ath_price=True, ath_profit=False, above_exit=True, outperformance=True) == "HOLD"


def test_classify_exit_exactly_one_true():
    assert tt.classify(ath_price=False, ath_profit=True, above_exit=False, outperformance=False) == "EXIT"
    assert tt.classify(ath_price=False, ath_profit=False, above_exit=True, outperformance=False) == "EXIT"
    assert tt.classify(ath_price=False, ath_profit=False, above_exit=False, outperformance=True) == "EXIT"


def test_classify_exit_none_true():
    assert tt.classify(ath_price=False, ath_profit=False, above_exit=False, outperformance=False) == "EXIT"


def test_classify_ath_price_excluded_from_hold_set():
    # doc edge case: ATH Price true + exactly one of {ath_profit, above_exit, outperformance}
    # true must still be EXIT -- ATH Price does not substitute into the HOLD 2-of-3 set.
    assert tt.classify(ath_price=True, ath_profit=False, above_exit=False, outperformance=True) == "EXIT"
    assert tt.classify(ath_price=True, ath_profit=True, above_exit=False, outperformance=False) == "EXIT"


# ---------------------------------------------------------------------------
# ath_price_flag
# ---------------------------------------------------------------------------
def test_ath_price_flag_at_and_within_threshold():
    assert tt.ath_price_flag(current_price=100, historical_max_close=100) is True
    assert tt.ath_price_flag(current_price=96, historical_max_close=100, threshold_pct=5.0) is True  # exactly at 4%


def test_ath_price_flag_off_high():
    assert tt.ath_price_flag(current_price=94, historical_max_close=100, threshold_pct=5.0) is False


def test_ath_price_flag_missing_data():
    assert tt.ath_price_flag(None, 100) is False
    assert tt.ath_price_flag(100, None) is False
    assert tt.ath_price_flag(np.nan, 100) is False
    assert tt.ath_price_flag(100, 0) is False


# ---------------------------------------------------------------------------
# ath_profit_flag -- shares-outstanding-derived current EPS vs historical max EPS
# ---------------------------------------------------------------------------
def test_ath_profit_flag_current_eps_at_or_above_historical_max():
    # market_cap=1e9, price=100 -> shares=1e7. TTM profit=10 Cr -> current_eps = 10*1e7/1e7 = 10.
    assert tt.ath_profit_flag(current_ttm_profit_cr=10, market_cap=1e9, current_price=100,
                               historical_max_eps=8) is True
    assert tt.ath_profit_flag(current_ttm_profit_cr=10, market_cap=1e9, current_price=100,
                               historical_max_eps=10) is True  # equal counts as ATH


def test_ath_profit_flag_current_eps_below_historical_max():
    assert tt.ath_profit_flag(current_ttm_profit_cr=10, market_cap=1e9, current_price=100,
                               historical_max_eps=12) is False


def test_ath_profit_flag_guards_zero_and_missing():
    assert tt.ath_profit_flag(10, 0, 100, 8) is False       # zero market cap
    assert tt.ath_profit_flag(10, 1e9, 0, 8) is False        # zero price
    assert tt.ath_profit_flag(None, 1e9, 100, 8) is False
    assert tt.ath_profit_flag(10, 1e9, 100, None) is False
    assert tt.ath_profit_flag(np.nan, 1e9, 100, 8) is False


# ---------------------------------------------------------------------------
# above_exit_flag
# ---------------------------------------------------------------------------
def test_above_exit_flag_both_directions():
    assert tt.above_exit_flag(current_price=110, ma200=100) is True
    assert tt.above_exit_flag(current_price=90, ma200=100) is False
    assert tt.above_exit_flag(current_price=100, ma200=100) is False  # strictly above required


def test_above_exit_flag_missing_ma200():
    assert tt.above_exit_flag(110, None) is False
    assert tt.above_exit_flag(110, np.nan) is False


# ---------------------------------------------------------------------------
# relative_strength -- exact % on a known synthetic daily series
# ---------------------------------------------------------------------------
def test_relative_strength_known_series():
    n = 400
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    closes = pd.Series(100.0 + np.arange(n), index=dates)

    result = tt.relative_strength(closes, window_days=365)

    base_date = dates[-1] - pd.Timedelta(days=365)
    base_close = closes[closes.index <= base_date].iloc[-1]
    expected = (closes.iloc[-1] / base_close - 1.0) * 100.0
    assert result == pytest.approx(expected)


def test_relative_strength_insufficient_history():
    dates = pd.date_range("2024-01-01", periods=30, freq="D")
    closes = pd.Series(100.0 + np.arange(30), index=dates)
    assert tt.relative_strength(closes, window_days=365) is None


def test_relative_strength_empty_or_undated():
    assert tt.relative_strength(pd.Series(dtype=float)) is None
    assert tt.relative_strength(None) is None
    assert tt.relative_strength(pd.Series([1.0, 2.0, 3.0])) is None  # no DatetimeIndex


# ---------------------------------------------------------------------------
# outperformance_flag
# ---------------------------------------------------------------------------
def test_outperformance_beats_both():
    assert tt.outperformance_flag(stock_rs=20, sector_rs=10, benchmark_rs=5) is True


def test_outperformance_beats_only_one():
    assert tt.outperformance_flag(stock_rs=20, sector_rs=25, benchmark_rs=5) is False   # loses to sector
    assert tt.outperformance_flag(stock_rs=20, sector_rs=10, benchmark_rs=25) is False  # loses to benchmark


def test_outperformance_beats_neither():
    assert tt.outperformance_flag(stock_rs=5, sector_rs=10, benchmark_rs=15) is False


def test_outperformance_missing_inputs():
    assert tt.outperformance_flag(None, 10, 5) is False
    assert tt.outperformance_flag(20, None, 5) is False
    assert tt.outperformance_flag(20, 10, None) is False


# ---------------------------------------------------------------------------
# filter_by_index -- Nifty 50/100/200/All membership
# ---------------------------------------------------------------------------
def test_filter_by_index_all_always_matches():
    assert tt.filter_by_index(None, "All") is True
    assert tt.filter_by_index("NIFTY 200", "All") is True


def test_filter_by_index_nifty_50_membership():
    assert tt.filter_by_index("NIFTY 50,NIFTY METAL", "NIFTY 50") is True
    assert tt.filter_by_index("NIFTY 200", "NIFTY 50") is False


def test_filter_by_index_nesting():
    # Nifty 50 membership implies Nifty 100 and Nifty 200 membership (NSE indices nest).
    assert tt.filter_by_index("NIFTY 50", "NIFTY 100") is True
    assert tt.filter_by_index("NIFTY 50", "NIFTY 200") is True
    assert tt.filter_by_index("NIFTY 100", "NIFTY 200") is True
    assert tt.filter_by_index("NIFTY 200", "NIFTY 100") is False  # not the reverse


def test_filter_by_index_missing_categories():
    assert tt.filter_by_index(np.nan, "NIFTY 50") is False
    assert tt.filter_by_index(None, "NIFTY 100") is False


# ---------------------------------------------------------------------------
# merge_live_prices -- intraday price overlay (leaves every other column untouched)
# ---------------------------------------------------------------------------
def _signals_df():
    return pd.DataFrame([
        {"Symbol": "RELIANCE", "Current_Price": 1300.0, "Signal": "EXIT", "ATH_Price_Flag": False},
        {"Symbol": "TCS", "Current_Price": 3400.0, "Signal": "HOLD", "ATH_Price_Flag": True},
        {"Symbol": "INFY", "Current_Price": 1500.0, "Signal": "ADD", "ATH_Price_Flag": True},
    ])


def test_merge_live_prices_overrides_matched_symbols():
    live = pd.DataFrame([
        {"Symbol": "RELIANCE", "Live_Price": 1435.4, "Price_As_Of": "2026-08-02T10:00:00+00:00"},
        {"Symbol": "TCS", "Live_Price": 3500.0, "Price_As_Of": "2026-08-02T10:00:00+00:00"},
    ])
    result = tt.merge_live_prices(_signals_df(), live)
    assert result.set_index("Symbol").loc["RELIANCE", "Current_Price"] == 1435.4
    assert result.set_index("Symbol").loc["TCS", "Current_Price"] == 3500.0


def test_merge_live_prices_keeps_original_for_unmatched_symbol():
    live = pd.DataFrame([{"Symbol": "RELIANCE", "Live_Price": 1435.4, "Price_As_Of": "x"}])
    result = tt.merge_live_prices(_signals_df(), live)
    # INFY has no live-price entry -- keeps the daily batch's own Current_Price.
    assert result.set_index("Symbol").loc["INFY", "Current_Price"] == 1500.0


def test_merge_live_prices_keeps_original_when_live_price_is_nan():
    live = pd.DataFrame([{"Symbol": "RELIANCE", "Live_Price": float("nan"), "Price_As_Of": "x"}])
    result = tt.merge_live_prices(_signals_df(), live)
    assert result.set_index("Symbol").loc["RELIANCE", "Current_Price"] == 1300.0


def test_merge_live_prices_never_touches_other_columns():
    live = pd.DataFrame([{"Symbol": "RELIANCE", "Live_Price": 1435.4, "Price_As_Of": "x"}])
    result = tt.merge_live_prices(_signals_df(), live)
    row = result.set_index("Symbol").loc["RELIANCE"]
    assert row["Signal"] == "EXIT"
    assert row["ATH_Price_Flag"] == False  # noqa: E712


def test_merge_live_prices_empty_live_prices_returns_unchanged():
    signals = _signals_df()
    result = tt.merge_live_prices(signals, pd.DataFrame())
    pd.testing.assert_frame_equal(result, signals)


def test_merge_live_prices_none_live_prices_returns_unchanged():
    signals = _signals_df()
    result = tt.merge_live_prices(signals, None)
    pd.testing.assert_frame_equal(result, signals)


def test_merge_live_prices_empty_signals_returns_unchanged():
    empty = pd.DataFrame(columns=["Symbol", "Current_Price"])
    result = tt.merge_live_prices(empty, pd.DataFrame([{"Symbol": "X", "Live_Price": 1.0, "Price_As_Of": "x"}]))
    assert result.empty


def test_merge_live_prices_missing_symbol_column_in_live_prices_is_safe():
    live = pd.DataFrame([{"NotSymbol": "RELIANCE", "Live_Price": 1435.4}])
    result = tt.merge_live_prices(_signals_df(), live)
    assert result.set_index("Symbol").loc["RELIANCE", "Current_Price"] == 1300.0
