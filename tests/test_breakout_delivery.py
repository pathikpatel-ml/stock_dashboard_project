"""Unit tests for delivery-volume parsing, aggregation, and the Filter-4/5 rules."""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import delivery_data as dd


def _raw_bhav():
    """Mimic the NSE sec_bhavdata_full layout: spaced column names, '-' for non-deliverable."""
    return pd.DataFrame(
        {
            "SYMBOL": ["APOLLOHOSP", "APOLLOHOSP", "TATAMOTORS", "SOMEFUT"],
            " SERIES": [" EQ", " EQ", " EQ", " FO"],
            " DATE1": [" 02-Jan-2026", " 05-Jan-2026", " 02-Jan-2026", " 02-Jan-2026"],
            " TTL_TRD_QNTY": [" 1000", " 2000", " 5000", " 100"],
            " DELIV_QTY": [" 800", " 1400", " 1900", " -"],
            " DELIV_PER": [" 80.00", " 70.00", " 38.00", " -"],
        }
    )


def test_parse_delivery_eq_only_and_numeric():
    parsed = dd.parse_delivery(_raw_bhav(), series="EQ")
    assert set(parsed["Symbol"]) == {"APOLLOHOSP", "TATAMOTORS"}  # FO row dropped
    apollo = parsed[parsed["Symbol"] == "APOLLOHOSP"].sort_values("Date")
    assert list(apollo["DeliveryPct"]) == [80.0, 70.0]
    assert list(apollo["TotalVolume"]) == [1000, 2000]


def test_aggregate_monthly_is_volume_weighted():
    parsed = dd.parse_delivery(_raw_bhav(), series="EQ")
    monthly = dd.aggregate_monthly(parsed)
    apollo = monthly[monthly["Symbol"] == "APOLLOHOSP"].iloc[0]
    # Volume-weighted: (800+1400)/(1000+2000) = 2200/3000 = 73.33% (not the simple mean 75%)
    assert apollo["DeliveryPct"] == pytest.approx(73.33, abs=0.01)
    assert apollo["Days"] == 2


def test_delivery_rising():
    assert dd.delivery_rising([60, 64, 69, 77, 80]) is True
    assert dd.delivery_rising([60, 55, 70]) is False


def test_evaluate_delivery_filter_rules():
    # Strong & rising -> pass with rising flag (doc ideal pattern 60->64->69->77->80)
    ok, reason, m = dd.evaluate_delivery_filter([60, 64, 69, 77, 80])
    assert ok is True and m["rising"] is True and m["latest"] == 80

    # Latest below 50 -> reject
    ok, reason, _ = dd.evaluate_delivery_filter([55, 52, 48])
    assert ok is False and "below_min" in reason

    # Latest below 30 -> hard reject
    ok, reason, _ = dd.evaluate_delivery_filter([45, 38, 28])
    assert ok is False and "hard_reject" in reason

    # All below 40 -> consistently weak reject
    ok, reason, _ = dd.evaluate_delivery_filter([35, 36, 38])
    assert ok is False and "consistently_weak" in reason

    # Moderate 50-60 single point -> valid (doc: 50-60% proceed with caution)
    ok, reason, _ = dd.evaluate_delivery_filter([52])
    assert ok is True
