"""
Unit tests for modules/turtle/nse_shareholding.py -- NSE's own promoter-holding history. No
live network: a fake session stands in for NSE's API, matching tests/test_nse_category_fetcher.py's style.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import nse_shareholding as nsh


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, payload=None, fail_times=0):
        self.payload = payload
        self.fail_times = fail_times
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            return _FakeResponse(status_code=500)
        return _FakeResponse(status_code=200, payload=self.payload)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# fetch_promoter_holding_history
# ---------------------------------------------------------------------------
SHAREHOLDING_PAYLOAD = [
    {"date": "31-MAR-2026", "pr_and_prgrp": "50.00"},
    {"date": "08-DEC-2021", "pr_and_prgrp": "48.00"},
    {"date": "30-JUN-2025", "pr_and_prgrp": "49.50"},
]


def test_fetch_promoter_holding_history_sorts_chronologically():
    session = _FakeSession(payload=SHAREHOLDING_PAYLOAD)
    result = nsh.fetch_promoter_holding_history("RELIANCE", session=session, retries=1, pause=0)
    assert result == (["08-DEC-2021", "30-JUN-2025", "31-MAR-2026"], [48.0, 49.5, 50.0])


def test_fetch_promoter_holding_history_none_on_empty_list():
    session = _FakeSession(payload=[])
    assert nsh.fetch_promoter_holding_history("X", session=session, retries=1, pause=0) is None


def test_fetch_promoter_holding_history_none_on_non_list_payload():
    session = _FakeSession(payload={"error": "not found"})
    assert nsh.fetch_promoter_holding_history("X", session=session, retries=1, pause=0) is None


def test_fetch_promoter_holding_history_retries_then_succeeds():
    session = _FakeSession(payload=SHAREHOLDING_PAYLOAD, fail_times=1)
    result = nsh.fetch_promoter_holding_history("RELIANCE", session=session, retries=2, pause=0)
    assert result is not None
    assert session.calls == 2


def test_fetch_promoter_holding_history_none_after_exhausting_retries():
    session = _FakeSession(payload=SHAREHOLDING_PAYLOAD, fail_times=5)
    assert nsh.fetch_promoter_holding_history("X", session=session, retries=2, pause=0) is None
