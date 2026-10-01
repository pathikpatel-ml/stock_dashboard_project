"""
Unit tests for modules/turtle/quality_flags.py -- pure functions, no I/O, hand-computable
synthetic series throughout (matches modules/turtle/compute.py's testing style).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import quality_flags as qf


def _series(values):
    periods = [f"Mar {2015 + i}" for i in range(len(values))]
    return periods, values


# ---------------------------------------------------------------------------
# cagr
# ---------------------------------------------------------------------------
def test_cagr_known_doubling_over_10_years():
    # Doubling over 10 years -> CAGR = 2**(1/10) - 1 = 7.177%
    series = _series([100.0] + [None] * 0 + [100.0 * (2 ** (i / 10)) for i in range(1, 11)])
    result = qf.cagr(series)
    assert result == pytest.approx(7.177, abs=0.01)


def test_cagr_simple_hand_computed():
    # 11 values (10 year-over-year periods): 100 -> 259.374246 is exactly 10% CAGR
    values = [100.0 * (1.10 ** i) for i in range(11)]
    result = qf.cagr(_series(values))
    assert result == pytest.approx(10.0, abs=0.001)


def test_cagr_uses_only_last_max_years_plus_one():
    # 15 values; CAGR should only look at the last 11 (10-year window), ignoring the first 4
    # which would otherwise pull the result toward a much higher growth rate.
    junk_early = [1.0, 1.0, 1.0, 1.0]  # would imply enormous growth if included
    last_11 = [100.0 * (1.10 ** i) for i in range(11)]
    result = qf.cagr(_series(junk_early + last_11))
    assert result == pytest.approx(10.0, abs=0.001)


def test_cagr_none_when_fewer_than_min_years():
    values = [100.0, 110.0, 120.0]  # only 2 year-over-year periods, min_years default is 5
    assert qf.cagr(_series(values)) is None


def test_cagr_none_when_start_value_not_positive():
    values = [0.0] + [10.0] * 6
    assert qf.cagr(_series(values)) is None
    values2 = [-5.0] + [10.0] * 6
    assert qf.cagr(_series(values2)) is None


def test_cagr_none_when_end_value_not_positive():
    # Real production bug (2026-10-01): EPS swinging from positive 10 years ago to negative
    # (loss-making) today -- (negative/positive) ** (1/years) is a COMPLEX number in Python for
    # a fractional exponent, which crashed growth_flag's "> threshold" comparison on a real
    # company's live data. Must return None, not attempt the power operation at all.
    values = [10.0, 10.0, 10.0, 10.0, 10.0, -5.0]
    assert qf.cagr(_series(values)) is None


def test_cagr_zero_end_value_returns_none():
    values = [10.0, 10.0, 10.0, 10.0, 10.0, 0.0]
    assert qf.cagr(_series(values)) is None


def test_cagr_none_for_none_series():
    assert qf.cagr(None) is None


# ---------------------------------------------------------------------------
# average
# ---------------------------------------------------------------------------
def test_average_known_values():
    values = [8.0, 9.0, 10.0, 11.0, 12.0]
    assert qf.average(_series(values)) == pytest.approx(10.0)


def test_average_uses_only_last_max_years():
    junk_early = [1000.0, 1000.0]  # would skew the average heavily if included
    last_10 = [10.0] * 10
    result = qf.average(_series(junk_early + last_10), max_years=10)
    assert result == pytest.approx(10.0)


def test_average_none_when_fewer_than_min_years():
    assert qf.average(_series([10.0, 10.0]), min_years=5) is None


def test_average_none_for_none_series():
    assert qf.average(None) is None


# ---------------------------------------------------------------------------
# growth_flag / roce_flag
# ---------------------------------------------------------------------------
def test_growth_flag_above_threshold_true():
    assert qf.growth_flag(10.01) is True


def test_growth_flag_at_or_below_threshold_false():
    assert qf.growth_flag(10.0) is False
    assert qf.growth_flag(5.0) is False


def test_growth_flag_none_passthrough():
    assert qf.growth_flag(None) is None


def test_roce_flag_boundary():
    assert qf.roce_flag(10.01) is True
    assert qf.roce_flag(10.0) is False
    assert qf.roce_flag(None) is None


# ---------------------------------------------------------------------------
# interest_coverage / interest_coverage_flag
# ---------------------------------------------------------------------------
def test_interest_coverage_hand_computed():
    pbt = _series([100.0, 200.0])  # latest = 200
    interest = _series([10.0, 50.0])  # latest = 50 -> (200+50)/50 = 5.0
    assert qf.interest_coverage(pbt, interest) == pytest.approx(5.0)


def test_interest_coverage_flag_true_above_threshold():
    pbt = _series([100.0, 260.0])
    interest = _series([10.0, 50.0])  # (260+50)/50 = 6.2 > 5
    coverage = qf.interest_coverage(pbt, interest)
    assert qf.interest_coverage_flag(coverage, interest) is True


def test_interest_coverage_zero_interest_is_none_but_flag_is_true():
    pbt = _series([100.0, 200.0])
    interest = _series([10.0, 0.0])
    coverage = qf.interest_coverage(pbt, interest)
    assert coverage is None
    assert qf.interest_coverage_flag(coverage, interest) is True


def test_interest_coverage_none_when_missing_data():
    assert qf.interest_coverage(None, _series([10.0])) is None
    assert qf.interest_coverage(_series([10.0]), None) is None


def test_interest_coverage_flag_none_when_not_zero_interest_and_no_coverage():
    assert qf.interest_coverage_flag(None, None) is None


# ---------------------------------------------------------------------------
# promoter_holding_flag / promoter_holding_change
# ---------------------------------------------------------------------------
def test_promoter_holding_flag_increase_true():
    series = _series([45.0, 46.0, 47.0, 48.0])
    assert qf.promoter_holding_flag(series) is True


def test_promoter_holding_flag_constant_true():
    series = _series([50.0, 50.0, 50.0, 50.0])
    assert qf.promoter_holding_flag(series) is True


def test_promoter_holding_flag_decrease_false():
    series = _series([50.0, 49.0, 48.0, 45.0])
    assert qf.promoter_holding_flag(series) is False


def test_promoter_holding_flag_none_when_insufficient_data():
    assert qf.promoter_holding_flag(_series([50.0])) is None
    assert qf.promoter_holding_flag(None) is None


def test_promoter_holding_change_value():
    series = _series([45.0, 46.0, 48.5])
    assert qf.promoter_holding_change(series) == pytest.approx(3.5)


# ---------------------------------------------------------------------------
# shares_outstanding_by_year / per_share_by_year / valuation_ratio_by_year / valuation_flag
# ---------------------------------------------------------------------------
def test_shares_outstanding_by_year_hand_computed():
    net_profit = (["Mar 2024", "Mar 2025"], [1000.0, 1100.0])
    eps = (["Mar 2024", "Mar 2025"], [10.0, 11.0])
    result = qf.shares_outstanding_by_year(net_profit, eps)
    assert result == {"Mar 2024": 100.0, "Mar 2025": 100.0}


def test_shares_outstanding_by_year_skips_zero_or_missing_eps():
    net_profit = (["Mar 2024", "Mar 2025"], [1000.0, 1100.0])
    eps = (["Mar 2024", "Mar 2025"], [0.0, 11.0])
    result = qf.shares_outstanding_by_year(net_profit, eps)
    assert result == {"Mar 2025": 100.0}


def test_per_share_by_year_hand_computed():
    book_value = (["Mar 2024", "Mar 2025"], [50000.0, 55000.0])
    shares = {"Mar 2024": 100.0, "Mar 2025": 100.0}
    result = qf.per_share_by_year(book_value, shares)
    assert result == {"Mar 2024": 500.0, "Mar 2025": 550.0}


def test_per_share_by_year_skips_periods_without_share_count():
    book_value = (["Mar 2024", "Mar 2025"], [50000.0, 55000.0])
    shares = {"Mar 2024": 100.0}  # Mar 2025 missing
    result = qf.per_share_by_year(book_value, shares)
    assert result == {"Mar 2024": 500.0}


def test_valuation_ratio_by_year_hand_computed():
    per_share = {"Mar 2024": 500.0, "Mar 2025": 550.0}
    price = {"Mar 2024": 1000.0, "Mar 2025": 1100.0}
    result = qf.valuation_ratio_by_year(per_share, price)
    assert result == {"Mar 2024": pytest.approx(2.0), "Mar 2025": pytest.approx(2.0)}


def test_valuation_flag_cheaper_than_average_is_true():
    # current ratio (1.5) below 5yr avg (2.0) -> stock is cheaper than its own history -> True
    assert qf.valuation_flag(five_year_avg_ratio=2.0, current_ratio=1.5) is True


def test_valuation_flag_more_expensive_than_average_is_false():
    assert qf.valuation_flag(five_year_avg_ratio=2.0, current_ratio=2.5) is False


def test_valuation_flag_none_when_either_missing():
    assert qf.valuation_flag(None, 2.0) is None
    assert qf.valuation_flag(2.0, None) is None
