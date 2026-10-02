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
# yoy_growth_values / level_values / all_years_above_threshold (2026-10-02 redesign:
# every individual year must clear the threshold, not just the overall CAGR/average)
# ---------------------------------------------------------------------------
def test_yoy_growth_values_hand_computed():
    # 100 -> 110 -> 121 -> 133.1 is exactly 10% YoY growth each year
    values = [100.0, 110.0, 121.0, 133.1]
    result = qf.yoy_growth_values(_series(values), min_years=1)
    assert result == pytest.approx([10.0, 10.0, 10.0])


def test_yoy_growth_values_none_when_fewer_than_min_years_plus_one():
    assert qf.yoy_growth_values(_series([100.0, 110.0]), min_years=5) is None


def test_yoy_growth_values_none_when_any_base_non_positive():
    values = [100.0, 0.0, 50.0, 1, 1, 1]
    assert qf.yoy_growth_values(_series(values), min_years=1) is None


def test_yoy_growth_values_uses_only_last_max_years_plus_one():
    junk_early = [1.0, 1.0]  # would imply enormous growth if included
    steady_10pct = [100.0 * (1.10 ** i) for i in range(6)]
    result = qf.yoy_growth_values(_series(junk_early + steady_10pct), max_years=5, min_years=1)
    assert result == pytest.approx([10.0] * 5)


def test_level_values_hand_computed():
    values = [8.0, 12.0, 15.0]
    assert qf.level_values(_series(values), min_years=1) == pytest.approx(values)


def test_level_values_none_when_fewer_than_min_years():
    assert qf.level_values(_series([10.0, 10.0]), min_years=5) is None


# ---------------------------------------------------------------------------
# roe_by_year (2026-10-02: derived ourselves, not screener.in's own ROCE/ROE row -- see
# quality_flags.py's module docstring for why)
# ---------------------------------------------------------------------------
def test_roe_by_year_hand_computed():
    net_profit = (["Mar 2024", "Mar 2025"], [1000.0, 1100.0])
    book_value = (["Mar 2024", "Mar 2025"], [10000.0, 10000.0])
    result = qf.roe_by_year(net_profit, book_value)
    assert result == (["Mar 2024", "Mar 2025"], [10.0, 11.0])


def test_roe_by_year_skips_zero_or_missing_book_value():
    net_profit = (["Mar 2024", "Mar 2025"], [1000.0, 1100.0])
    book_value = (["Mar 2024"], [10000.0])  # Mar 2025 missing
    result = qf.roe_by_year(net_profit, book_value)
    assert result == (["Mar 2024"], [10.0])


def test_roe_by_year_none_when_either_input_missing():
    assert qf.roe_by_year(None, (["Mar 2024"], [10000.0])) is None
    assert qf.roe_by_year((["Mar 2024"], [1000.0]), None) is None


def test_all_years_above_threshold_true_when_every_year_passes():
    assert qf.all_years_above_threshold([11.0, 15.0, 20.0], 10.0) is True


def test_all_years_above_threshold_false_when_one_year_fails():
    # A single weak year fails the whole metric, even if every other year is strongly above --
    # the core behavior change from the old overall-CAGR/average approach.
    assert qf.all_years_above_threshold([25.0, 25.0, 9.9, 25.0], 10.0) is False


def test_all_years_above_threshold_false_at_exact_boundary():
    assert qf.all_years_above_threshold([10.0, 20.0], 10.0) is False


def test_all_years_above_threshold_none_when_values_none():
    assert qf.all_years_above_threshold(None, 10.0) is None


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


# ---------------------------------------------------------------------------
# quality_of_turnover / quality_of_turnover_flag (2026-10-02)
# ---------------------------------------------------------------------------
def test_quality_of_turnover_hand_computed():
    other_income = (["Mar 2024", "Mar 2025"], [10.0, 20.0])
    sales = (["Mar 2024", "Mar 2025"], [90.0, 180.0])
    # latest year: 20 / (180 + 20) = 10%
    assert qf.quality_of_turnover(other_income, sales) == pytest.approx(10.0)


def test_quality_of_turnover_uses_latest_common_period():
    other_income = (["Mar 2023", "Mar 2024", "Mar 2025"], [5.0, 10.0, 20.0])
    sales = (["Mar 2023", "Mar 2024"], [95.0, 90.0])  # Mar 2025 missing from sales
    # falls back to the latest period BOTH sides have: Mar 2024 -> 10 / (90+10) = 10%
    assert qf.quality_of_turnover(other_income, sales) == pytest.approx(10.0)


def test_quality_of_turnover_none_when_missing_series():
    assert qf.quality_of_turnover(None, (["Mar 2024"], [90.0])) is None
    assert qf.quality_of_turnover((["Mar 2024"], [10.0]), None) is None


def test_quality_of_turnover_flag_boundary():
    assert qf.quality_of_turnover_flag(9.99) is True
    assert qf.quality_of_turnover_flag(10.0) is False
    assert qf.quality_of_turnover_flag(None) is None


# ---------------------------------------------------------------------------
# Category-aggregate flags (2026-10-02): the only 3 fields the dashboard displays.
# Never None -- missing/failed underlying data counts as "not fulfilled" (No).
# ---------------------------------------------------------------------------
def test_growth_category_flag_true_when_all_five_pass():
    assert qf.growth_category_flag(True, True, True, True, True) is True


def test_growth_category_flag_false_when_any_fails():
    assert qf.growth_category_flag(True, True, False, True, True) is False


def test_growth_category_flag_false_when_any_is_none():
    assert qf.growth_category_flag(True, True, None, True, True) is False


def test_red_flag_category_flag_true_when_all_three_pass():
    assert qf.red_flag_category_flag(True, True, True) is True


def test_red_flag_category_flag_false_when_any_fails_or_missing():
    assert qf.red_flag_category_flag(False, True, True) is False
    assert qf.red_flag_category_flag(True, False, True) is False
    assert qf.red_flag_category_flag(True, True, False) is False
    assert qf.red_flag_category_flag(None, True, True) is False


# ---------------------------------------------------------------------------
# promoter_pledge_flag (2026-10-02, sourced from NSE's own pledge disclosure --
# modules/turtle/nse_shareholding.py)
# ---------------------------------------------------------------------------
def test_promoter_pledge_flag_boundary():
    assert qf.promoter_pledge_flag(0.99) is True
    assert qf.promoter_pledge_flag(1.0) is False
    assert qf.promoter_pledge_flag(1.01) is False


def test_promoter_pledge_flag_zero_pledge_passes():
    assert qf.promoter_pledge_flag(0.0) is True


def test_promoter_pledge_flag_none_passthrough():
    assert qf.promoter_pledge_flag(None) is None


def test_value_category_flag_true_when_all_three_pass():
    assert qf.value_category_flag(True, True, True) is True


def test_value_category_flag_false_when_any_fails():
    assert qf.value_category_flag(True, False, True) is False
