"""
Tests for the Turtle Quant screening pipeline (modules/turtlequant/screener.py).

2026-10-02: the original weekly RS/SuperTrend/ADX/RSI technical-signal system was removed per
explicit user request. What's left is a pure, network-free fundamental quality/valuation screen
-- these tests no longer monkeypatch any fetch, since run_pipeline now does no I/O at all.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtlequant import screener as sc

UNIVERSE = pd.DataFrame([
    {"Symbol": "BUYSTOCK", "Company Name": "Buy Co", "Sector": "Alpha", "Industry": "Widgets", "Current_Price": 400.0},
    {"Symbol": "HOLDSTOCK", "Company Name": "Hold Co", "Sector": "Beta", "Industry": "Gadgets", "Current_Price": 140.0},
])


def test_run_pipeline_schema():
    out = sc.run_pipeline(UNIVERSE, verbose=False)
    signals = out["signals"]
    assert list(signals.columns) == sc.SIGNAL_COLUMNS
    assert len(signals) == 2
    assert out["rejections"].empty


def test_run_pipeline_passes_through_universe_fields():
    out = sc.run_pipeline(UNIVERSE, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["Company"] == "Buy Co"
    assert row["Industry"] == "Widgets"
    assert row["Current_Price"] == pytest.approx(400.0)


def test_run_pipeline_limit():
    out = sc.run_pipeline(UNIVERSE, limit=1, verbose=False)
    assert len(out["signals"]) == 1


# ---------------------------------------------------------------------------
# Screener.in Sector/Broad_Sector preference (2026-09-24) -- same rule as
# modules/turtle/screener.py::run_pipeline, applied here so both tabs are consistent.
# ---------------------------------------------------------------------------
def test_run_pipeline_prefers_screener_sector_over_universe_yahoo_tag():
    fundamentals = pd.DataFrame([
        {"Symbol": "BUYSTOCK", "Broad_Sector": "Energy", "Sector": "Oil, Gas & Consumable Fuels"},
    ])
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=fundamentals, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["Sector"] == "Oil, Gas & Consumable Fuels"
    assert row["Broad_Sector"] == "Energy"


def test_run_pipeline_falls_back_to_universe_sector_when_screener_has_none():
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=None, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["Sector"] == "Alpha"  # the universe CSV's own Yahoo-style tag
    assert pd.isna(row["Broad_Sector"]) or row["Broad_Sector"] is None


def test_run_pipeline_falls_back_per_symbol_when_screener_has_only_some():
    # Only BUYSTOCK has screener.in data -- HOLDSTOCK must still fall back to its universe tag.
    fundamentals = pd.DataFrame([
        {"Symbol": "BUYSTOCK", "Broad_Sector": "Energy", "Sector": "Oil, Gas & Consumable Fuels"},
    ])
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=fundamentals, verbose=False)
    signals = out["signals"].set_index("Symbol")
    assert signals.loc["BUYSTOCK", "Sector"] == "Oil, Gas & Consumable Fuels"
    assert signals.loc["HOLDSTOCK", "Sector"] == "Beta"


# ---------------------------------------------------------------------------
# Fundamental quality/valuation flags (2026-10-01) threaded through from fundamentals_df
# ---------------------------------------------------------------------------
def test_run_pipeline_threads_quality_flags_through_to_signal_row():
    fundamentals = pd.DataFrame([{
        "Symbol": "BUYSTOCK",
        "Book_Value_CAGR_10Y": 14.59, "Book_Value_Growth_Flag": True,
        "ROCE_Avg_10Y": 9.9, "ROCE_Flag": False,
        "PB_Current": 2.1, "PB_5Y_Avg": 2.45, "PB_Flag": True,
    }])
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=fundamentals, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["Book_Value_CAGR_10Y"] == pytest.approx(14.59)
    assert row["Book_Value_Growth_Flag"] == True  # noqa: E712
    assert row["ROCE_Avg_10Y"] == pytest.approx(9.9)
    assert row["ROCE_Flag"] == False  # noqa: E712
    assert row["PB_Flag"] == True  # noqa: E712


def test_run_pipeline_quality_flags_none_when_no_fundamentals():
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=None, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    for col in sc.QUALITY_COLUMNS:
        assert pd.isna(row[col]) or row[col] is None


def test_signal_columns_includes_all_quality_columns():
    assert set(sc.QUALITY_COLUMNS) <= set(sc.SIGNAL_COLUMNS)
