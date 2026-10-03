"""
Unit tests for modules/breakout/data_feed.py's hard-timeout protection (2026-10-02).

Confirmed live in a real production batch run: a small number of symbols can make yfinance's
underlying curl_cffi transport hang for 30-50 MINUTES before finally raising an exception --
yfinance's own ``timeout=`` parameter only bounds a single HTTP attempt, not whatever retry
happens internally around it. ``_fetch_raw`` runs the real call on a background daemon thread
and gives up waiting after ``_HARD_TIMEOUT_SECONDS`` -- these tests monkeypatch that constant
down to a tiny value so a "hang" can be simulated with a short sleep instead of actually waiting
the real 30s ceiling, keeping the test suite fast.
"""
import os
import sys
import threading
import time

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import data_feed


@pytest.fixture(autouse=True)
def _clear_cache():
    data_feed.clear_cache()
    yield
    data_feed.clear_cache()


class _FakeTicker:
    """Stands in for yf.Ticker(...) -- .history() either returns instantly or sleeps past the
    (monkeypatched, shortened) hard timeout to simulate the real hang."""

    def __init__(self, symbol, hang_seconds=0, frame=None):
        self.symbol = symbol
        self.hang_seconds = hang_seconds
        self.frame = frame

    def history(self, period=None, interval=None, auto_adjust=None, timeout=None):
        if self.hang_seconds:
            time.sleep(self.hang_seconds)
        if self.frame is not None:
            return self.frame
        raise RuntimeError("Failed to perform, curl: (16)")


def _sample_frame():
    dates = pd.date_range("2026-01-01", periods=3, freq="MS")
    return pd.DataFrame(
        {"Open": [1.0, 2.0, 3.0], "High": [1.5, 2.5, 3.5], "Low": [0.5, 1.5, 2.5],
         "Close": [1.2, 2.2, 3.2], "Volume": [100, 200, 300]},
        index=dates,
    )


def test_fast_successful_fetch_returns_normalised_frame(monkeypatch):
    monkeypatch.setattr(
        data_feed.yf, "Ticker", lambda t: _FakeTicker(t, hang_seconds=0, frame=_sample_frame())
    )
    result = data_feed.get_monthly("RELIANCE", period="1y", use_cache=False)
    assert result is not None
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(result) == 3


def test_hanging_fetch_is_abandoned_after_hard_timeout(monkeypatch):
    # Real bug this guards against: a symbol whose underlying call hangs far longer than
    # yfinance's own timeout= parameter would otherwise block the entire calling process.
    monkeypatch.setattr(data_feed, "_HARD_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(
        data_feed.yf, "Ticker", lambda t: _FakeTicker(t, hang_seconds=5, frame=_sample_frame())
    )
    t0 = time.time()
    result = data_feed.get_monthly("HANGSYMBOL", period="1y", use_cache=False)
    elapsed = time.time() - t0
    assert result is None
    assert elapsed < 1.0  # abandoned well before the simulated 5s hang completes


def test_normal_exception_returns_none_quickly(monkeypatch):
    monkeypatch.setattr(data_feed.yf, "Ticker", lambda t: _FakeTicker(t, hang_seconds=0, frame=None))
    t0 = time.time()
    result = data_feed.get_daily("BADSYMBOL", period="1y", use_cache=False)
    elapsed = time.time() - t0
    assert result is None
    assert elapsed < 1.0


def test_cache_stores_result_after_successful_fetch(monkeypatch):
    calls = {"count": 0}

    def fake_ticker(t):
        calls["count"] += 1
        return _FakeTicker(t, hang_seconds=0, frame=_sample_frame())

    monkeypatch.setattr(data_feed.yf, "Ticker", fake_ticker)
    first = data_feed.get_weekly("RELIANCE", period="1y", use_cache=True)
    second = data_feed.get_weekly("RELIANCE", period="1y", use_cache=True)
    assert first is not None and second is not None
    assert calls["count"] == 1  # second call served from cache, no new fetch


def test_cache_stores_none_for_abandoned_hang_too(monkeypatch):
    # A timed-out fetch's None result is cached same as any other -- avoids hammering the same
    # slow symbol repeatedly within one run (matches every other optional-field caching pattern
    # already established in this pipeline).
    monkeypatch.setattr(data_feed, "_HARD_TIMEOUT_SECONDS", 0.2)
    calls = {"count": 0}

    def fake_ticker(t):
        calls["count"] += 1
        return _FakeTicker(t, hang_seconds=5, frame=_sample_frame())

    monkeypatch.setattr(data_feed.yf, "Ticker", fake_ticker)
    first = data_feed.get_monthly("HANGSYMBOL2", period="1y", use_cache=True)
    second = data_feed.get_monthly("HANGSYMBOL2", period="1y", use_cache=True)
    assert first is None and second is None
    assert calls["count"] == 1
