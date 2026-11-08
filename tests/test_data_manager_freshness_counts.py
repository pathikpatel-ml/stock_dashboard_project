"""
Unit tests for data_manager.py::_freshness_counts_from_series (2026-11-08) -- "N of M stocks
caught up to the latest run" for already-loaded DataFrame columns (turtle_signals_latest,
turtle_live_prices), used by the Turtle Strategy tab's freshness banners.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_manager as dm


def test_separates_fresh_rows_from_a_week_old_leftover():
    series = pd.Series([
        "2026-11-08T08:00:00Z",
        "2026-11-07T23:00:00Z",
        "2026-11-01T18:30:00Z",  # last week's leftover, well outside the 24h window
    ])
    fresh, total = dm._freshness_counts_from_series(series)
    assert (fresh, total) == (2, 3)


def test_all_fresh_when_every_row_just_ran():
    series = pd.Series(["2026-11-08T08:00:00Z", "2026-11-08T07:00:00Z"])
    assert dm._freshness_counts_from_series(series) == (2, 2)


def test_ignores_unparseable_values_in_the_total():
    series = pd.Series(["2026-11-08T08:00:00Z", "not-a-timestamp", None])
    fresh, total = dm._freshness_counts_from_series(series)
    assert total == 1
    assert fresh == 1


def test_returns_none_none_for_empty_series():
    assert dm._freshness_counts_from_series(pd.Series([], dtype=object)) == (None, None)


def test_returns_none_none_when_nothing_parses():
    assert dm._freshness_counts_from_series(pd.Series(["garbage", None])) == (None, None)
