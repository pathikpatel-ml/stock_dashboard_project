"""
Unit tests for data_manager.process_v20_signals's CMP-fetch guard.

process_v20_signals runs on every v20-auto-refresh-interval tick (every 5 min), not just on
button click. The original implementation spawned a brand-new daemon thread per call and gave
up waiting on it after 90s WITHOUT stopping it -- an abandoned thread doing native yfinance/curl
HTTP work keeps running in the background, so back-to-back ticks could leave two such threads
running concurrently in one process. That's the suspected cause of a SIGSEGV crash-loop seen on
Render. These tests exercise the fix: a module-level single-flight lock plus a persistent price
cache, with no live network (yf.download is stubbed).
"""
import os
import sys
import threading
import time

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import data_manager as dm


@pytest.fixture(autouse=True)
def _reset_cmp_fetch_state():
    """These tests share module-level state (_v20_cmp_cache/_v20_cmp_fetch_thread) -- reset
    it before and after every test so one test's fetch can't leak into the next."""
    dm._v20_cmp_cache = {}
    dm._v20_cmp_fetch_thread = None
    yield
    dm._v20_cmp_cache = {}
    dm._v20_cmp_fetch_thread = None


def _signals_df(symbols):
    return pd.DataFrame([
        {"Symbol": s, "Buy_Price_Low": 100.0, "Sell_Price_High": 150.0,
         "Sequence_Gain_Percent": 50.0, "Buy_Date": "2026-01-01"}
        for s in symbols
    ])


def _fake_download_returning(prices: dict):
    def _downloader(tickers, **kwargs):
        columns = pd.MultiIndex.from_product([tickers, ["Close"]])
        data = {(t, "Close"): [prices.get(t.replace(".NS", ""))] for t in tickers}
        return pd.DataFrame(data, columns=columns)
    return _downloader


def test_fetch_disables_yfinance_internal_threading(monkeypatch):
    # yfinance's own internal per-ticker thread pool (threads=True is its default) is nested
    # underneath our outer background thread -- on Render's constrained container this was the
    # real SIGSEGV source, reproducing even with only one outer fetch in flight. Must stay off.
    seen_kwargs = {}

    def _downloader(tickers, **kwargs):
        seen_kwargs.update(kwargs)
        columns = pd.MultiIndex.from_product([tickers, ["Close"]])
        return pd.DataFrame({(t, "Close"): [100.0] for t in tickers}, columns=columns)

    monkeypatch.setattr(dm.yf, "download", _downloader)
    dm.process_v20_signals(_signals_df(["TCS"]))

    assert seen_kwargs.get("threads") is False


def test_first_call_fetches_and_populates_prices(monkeypatch):
    monkeypatch.setattr(dm.yf, "download", _fake_download_returning({"TCS": 120.0}))

    result = dm.process_v20_signals(_signals_df(["TCS"]))

    assert list(result["Symbol"]) == ["TCS"]
    assert result.iloc[0]["Latest Close Price"] == 120.0
    assert dm._v20_cmp_cache == {"TCS": 120.0}


def test_second_call_does_not_start_a_second_thread_while_one_is_in_flight(monkeypatch):
    call_count = {"n": 0}
    release = threading.Event()

    def _slow_downloader(tickers, **kwargs):
        call_count["n"] += 1
        release.wait(timeout=2)  # block until the test releases it (or this cap trips)
        columns = pd.MultiIndex.from_product([tickers, ["Close"]])
        return pd.DataFrame({(t, "Close"): [100.0] for t in tickers}, columns=columns)

    monkeypatch.setattr(dm.yf, "download", _slow_downloader)

    # First call starts the fetch thread; give it a moment to actually enter yf.download.
    def _run_first():
        dm.process_v20_signals(_signals_df(["TCS"]))
    t1 = threading.Thread(target=_run_first)
    t1.start()
    time.sleep(0.2)

    # Second call (simulating the next auto-refresh tick) must see the in-flight thread and
    # NOT spawn a second one -- yf.download should only ever have been entered once so far.
    dm.process_v20_signals(_signals_df(["TCS"]))
    assert call_count["n"] == 1

    release.set()
    t1.join(timeout=5)


def test_cached_prices_served_when_fetch_times_out(monkeypatch):
    dm._v20_cmp_cache = {"TCS": 111.0}  # simulates a previous successful fetch

    def _never_returns(tickers, **kwargs):
        time.sleep(30)  # longer than the join timeout -- must not block the test itself
        return pd.DataFrame()

    monkeypatch.setattr(dm.yf, "download", _never_returns)
    monkeypatch.setattr(dm, "_v20_cmp_lock", dm._v20_cmp_lock)  # sanity: same lock object

    # Force a short join so this test doesn't actually wait out the real 20s timeout.
    orig_thread = threading.Thread

    class _ImmediateTimeoutThread(orig_thread):
        def join(self, timeout=None):
            super().join(timeout=0.05)

    monkeypatch.setattr(dm.threading, "Thread", _ImmediateTimeoutThread)

    result = dm.process_v20_signals(_signals_df(["TCS"]))

    assert list(result["Symbol"]) == ["TCS"]
    assert result.iloc[0]["Latest Close Price"] == 111.0


def test_empty_signals_returns_empty_without_touching_network(monkeypatch):
    calls = []
    monkeypatch.setattr(dm.yf, "download", lambda *a, **k: calls.append(1))

    result = dm.process_v20_signals(pd.DataFrame())

    assert result.empty
    assert calls == []
