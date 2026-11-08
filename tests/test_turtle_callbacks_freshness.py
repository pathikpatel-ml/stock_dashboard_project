"""
Unit tests for modules/turtle/callbacks.py's turtle_job_status-based freshness-banner text
(2026-11-08) -- the "N of <universe total> stocks updated; left: reasons" clause shown on all
3 of the Turtle Strategy tab's banners.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import callbacks as tc


# ---------------------------------------------------------------------------
# _reason_breakdown_text
# ---------------------------------------------------------------------------
def test_reason_breakdown_text_empty_for_no_reasons():
    assert tc._reason_breakdown_text({}) == ""
    assert tc._reason_breakdown_text(None) == ""


def test_reason_breakdown_text_single_reason():
    assert tc._reason_breakdown_text({"fetch_error": 380}) == "; left: 380 fetch error"


def test_reason_breakdown_text_sorted_by_count_descending():
    text = tc._reason_breakdown_text({"insufficient_monthly_data": 11, "fetch_error": 380})
    assert text == "; left: 380 fetch error, 11 under 12 months listed"


def test_reason_breakdown_text_unknown_reason_falls_back_to_humanized_key():
    assert tc._reason_breakdown_text({"some_new_reason": 3}) == "; left: 3 some new reason"


def test_reason_breakdown_text_skips_zero_counts():
    assert tc._reason_breakdown_text({"fetch_error": 0}) == ""
    assert tc._reason_breakdown_text({"fetch_error": 0, "no_ttm_data": 5}) == "; left: 5 no TTM data available"


# ---------------------------------------------------------------------------
# _job_status_suffix
# ---------------------------------------------------------------------------
def test_job_status_suffix_full_example():
    suffix = tc._job_status_suffix(2655, {
        "updated_count": 2244,
        "reason_breakdown": {"fetch_error": 380, "insufficient_monthly_data": 11},
    })
    assert suffix == " — 2,244 of 2,655 stocks updated; left: 380 fetch error, 11 under 12 months listed"


def test_job_status_suffix_no_reasons_left_when_everything_updated():
    suffix = tc._job_status_suffix(100, {"updated_count": 100, "reason_breakdown": {}})
    assert suffix == " — 100 of 100 stocks updated"


def test_job_status_suffix_empty_when_job_status_missing():
    assert tc._job_status_suffix(2655, None) == ""
    assert tc._job_status_suffix(2655, {}) == ""


def test_job_status_suffix_empty_when_universe_total_missing():
    assert tc._job_status_suffix(None, {"updated_count": 100, "reason_breakdown": {}}) == ""


def test_job_status_suffix_empty_when_updated_count_missing():
    assert tc._job_status_suffix(2655, {"reason_breakdown": {}}) == ""
