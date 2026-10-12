"""
Unit tests for modules/turtle/http_utils.py's hard-timeout wrapper (2026-10-11).

Confirmed live in a real production batch run: a screener.in/NSE request can get stuck in a
slow-trickle state that never trips requests' own ``timeout=`` (which only bounds gaps between
received bytes, not total request duration) and hang for hours. ``get_with_hard_timeout`` runs
the real call on a background daemon thread and gives up waiting after ``hard_timeout`` --
these tests pass a tiny ``hard_timeout`` so a "hang" can be simulated with a short sleep
instead of actually waiting the real 30s ceiling, keeping the test suite fast. Mirrors
tests/test_breakout_data_feed.py's exact style for the sibling yfinance-side fix.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import http_utils


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _FakeSession:
    """Stands in for requests.Session -- .get() either returns instantly, sleeps past the
    (tiny, test-provided) hard timeout to simulate a real hang, or raises."""

    def __init__(self, hang_seconds=0, response=None, raise_exc=None):
        self.hang_seconds = hang_seconds
        self.response = response
        self.raise_exc = raise_exc
        self.calls = []

    def get(self, url, timeout=None, params=None):
        self.calls.append({"url": url, "timeout": timeout, "params": params})
        if self.hang_seconds:
            time.sleep(self.hang_seconds)
        if self.raise_exc:
            raise self.raise_exc
        return self.response


def test_fast_successful_get_returns_response():
    session = _FakeSession(response=_FakeResponse(200, "ok"))
    result = http_utils.get_with_hard_timeout(session, "https://example.com")
    assert result is not None
    assert result.status_code == 200
    assert result.text == "ok"


def test_hanging_get_is_abandoned_after_hard_timeout():
    # Real bug this guards against: a request that never goes fully silent (so requests' own
    # timeout= never fires) would otherwise block the caller indefinitely.
    session = _FakeSession(hang_seconds=5, response=_FakeResponse(200, "late"))
    t0 = time.time()
    result = http_utils.get_with_hard_timeout(session, "https://example.com", hard_timeout=0.2)
    elapsed = time.time() - t0
    assert result is None
    assert elapsed < 1.0  # abandoned well before the simulated 5s hang completes


def test_exception_returns_none_quickly():
    session = _FakeSession(raise_exc=ConnectionError("simulated"))
    t0 = time.time()
    result = http_utils.get_with_hard_timeout(session, "https://example.com")
    elapsed = time.time() - t0
    assert result is None
    assert elapsed < 1.0


def test_params_omitted_when_not_given():
    # Keeps the call shape identical to a plain session.get(url, timeout=...) for the common
    # (no-params) case -- a caller/mock with a narrower get(self, url, timeout=None) signature
    # (no **kwargs) must not break.
    session = _FakeSession(response=_FakeResponse(200, "ok"))
    http_utils.get_with_hard_timeout(session, "https://example.com")
    assert session.calls[0]["params"] is None


def test_params_passed_through_when_given():
    session = _FakeSession(response=_FakeResponse(200, "ok"))
    http_utils.get_with_hard_timeout(session, "https://example.com", params={"q": "RELIANCE"})
    assert session.calls[0]["params"] == {"q": "RELIANCE"}
