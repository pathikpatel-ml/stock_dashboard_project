"""
Unit tests for modules/turtle/tickertape_feed.py -- the fallback daily-close fetch for the 7
sectoral indices verified stale on yfinance (see modules/turtle/constants.py::
TICKERTAPE_INDEX_SYMBOLS). No live network: requests.get is stubbed.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import tickertape_feed as ttf


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_index_daily_close_parses_points(monkeypatch):
    payload = {
        "success": True,
        "data": {
            ".NIFTYAUTO": {
                "points": [
                    {"ts": "2026-08-20T00:00:00.000Z", "lp": 29301.75, "v": 0},
                    {"ts": "2026-08-21T00:00:00.000Z", "lp": 29123.45, "v": 0},
                ],
                "sid": ".NIFTYAUTO",
            }
        },
        "error": None,
    }
    monkeypatch.setattr(ttf.requests, "get", lambda *a, **k: _FakeResponse(200, payload))

    series = ttf.fetch_index_daily_close(".NIFTYAUTO")

    assert isinstance(series, pd.Series)
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.index.tz is None
    assert list(series.values) == [29301.75, 29123.45]
    assert series.index.is_monotonic_increasing


def test_fetch_index_daily_close_empty_points_returns_none(monkeypatch):
    payload = {"success": True, "data": {".NIFTYAUTO": {"points": [], "sid": ".NIFTYAUTO"}}, "error": None}
    monkeypatch.setattr(ttf.requests, "get", lambda *a, **k: _FakeResponse(200, payload))

    assert ttf.fetch_index_daily_close(".NIFTYAUTO") is None


def test_fetch_index_daily_close_missing_symbol_key_returns_none(monkeypatch):
    payload = {"success": True, "data": {}, "error": None}
    monkeypatch.setattr(ttf.requests, "get", lambda *a, **k: _FakeResponse(200, payload))

    assert ttf.fetch_index_daily_close(".NIFTYAUTO") is None


def test_fetch_index_daily_close_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(ttf.requests, "get", lambda *a, **k: _FakeResponse(500, None))

    assert ttf.fetch_index_daily_close(".NIFTYAUTO") is None


def test_fetch_index_daily_close_connection_exception_returns_none(monkeypatch):
    def _raise(*a, **k):
        raise ConnectionError("simulated")

    monkeypatch.setattr(ttf.requests, "get", _raise)

    assert ttf.fetch_index_daily_close(".NIFTYAUTO") is None


def test_fetch_index_daily_close_malformed_point_returns_none(monkeypatch):
    payload = {"success": True, "data": {".NIFTYAUTO": {"points": [{"ts": "bad"}]}}, "error": None}
    monkeypatch.setattr(ttf.requests, "get", lambda *a, **k: _FakeResponse(200, payload))

    assert ttf.fetch_index_daily_close(".NIFTYAUTO") is None


def test_fetch_index_daily_close_uses_millisecond_epoch_params(monkeypatch):
    seen = {}

    def _fake_get(url, params=None, headers=None, timeout=None):
        seen.update(params)
        return _FakeResponse(200, {"data": {".NIFTYAUTO": {"points": []}}})

    monkeypatch.setattr(ttf.requests, "get", _fake_get)
    ttf.fetch_index_daily_close(".NIFTYAUTO", years=1.0)

    assert seen["end"] - seen["start"] == pytest.approx(365 * 24 * 3600 * 1000, rel=0.01)
    assert seen["start"] > 10**12  # sanity: looks like a millisecond epoch, not seconds
