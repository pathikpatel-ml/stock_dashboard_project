"""
Unit tests for modules/turtle/callbacks.py::_count_suffix (2026-11-08) -- the " — N of M
stocks" suffix appended to each of the Turtle Strategy tab's 3 freshness banners.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import callbacks as tc


def test_count_suffix_formats_with_thousands_separators():
    assert tc._count_suffix(1133, 2635) == " — 1,133 of 2,635 stocks"


def test_count_suffix_all_caught_up():
    assert tc._count_suffix(2244, 2244) == " — 2,244 of 2,244 stocks"


def test_count_suffix_empty_when_fresh_count_missing():
    assert tc._count_suffix(None, 2635) == ""


def test_count_suffix_empty_when_total_count_missing():
    assert tc._count_suffix(1133, None) == ""


def test_count_suffix_empty_when_both_missing():
    assert tc._count_suffix(None, None) == ""
