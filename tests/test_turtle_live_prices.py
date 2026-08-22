"""
Unit tests for generate_turtle_live_prices.py -- the batched intraday price refresh that
sits alongside generate_turtle_signals.py's once-daily full classification.

No live network: yfinance's ``download`` is stubbed with a fake function that mimics its
real MultiIndex-columns return shape, so parsing/merging/persistence are exercised without
depending on Yahoo being reachable in CI.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_turtle_live_prices as tlp


def _raise_no_db():
    raise RuntimeError("no DB in tests")


@pytest.fixture(autouse=True)
def _no_live_db(monkeypatch):
    """load_universe_symbols/load_existing_cache try Postgres before falling back to the CSV
    path these tests exercise -- block the DB call so it always falls through to CSV, keeping
    this file's declared "no live network" isolation instead of hitting the real DB via
    whatever MARKET_DATA_DB_URL happens to be in the environment (e.g. from a local .env)."""
    monkeypatch.setattr(tlp.mdw, "get_connection", _raise_no_db)


def _fake_multi_download(prices: dict):
    """Build a fake ``yf.download`` matching its real group_by="ticker" MultiIndex shape."""
    def _downloader(tickers, **kwargs):
        columns = pd.MultiIndex.from_product(
            [tickers, ["Open", "High", "Low", "Close", "Volume"]]
        )
        data = {}
        for ticker in tickers:
            symbol = ticker.replace(".NS", "")
            close = prices.get(symbol)
            for field in ["Open", "High", "Low", "Close", "Volume"]:
                data[(ticker, field)] = [close if field == "Close" else 1.0]
        return pd.DataFrame(data, columns=columns)
    return _downloader


def _fake_single_download(price):
    def _downloader(tickers, **kwargs):
        return pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0],
                              "Close": [price], "Volume": [1.0]})
    return _downloader


def _raising_downloader(tickers, **kwargs):
    raise ConnectionError("simulated network failure")


# ---------------------------------------------------------------------------
# load_universe_symbols
# ---------------------------------------------------------------------------
def test_load_universe_symbols_dedupes_normalises_and_sorts(tmp_path):
    path = tmp_path / "universe.csv"
    pd.DataFrame({"Symbol": [" reliance ", "TCS", "tcs", None, ""]}).to_csv(path, index=False)
    symbols = tlp.load_universe_symbols(str(path))
    assert symbols == ["RELIANCE", "TCS"]


def test_load_universe_symbols_missing_file_raises(tmp_path):
    with pytest.raises(SystemExit):
        tlp.load_universe_symbols(str(tmp_path / "does_not_exist.csv"))


# ---------------------------------------------------------------------------
# fetch_batch_prices
# ---------------------------------------------------------------------------
def test_fetch_batch_prices_multi_ticker():
    downloader = _fake_multi_download({"RELIANCE": 1400.5, "TCS": 3500.0})
    prices = tlp.fetch_batch_prices(["RELIANCE", "TCS"], downloader=downloader)
    assert prices == {"RELIANCE": 1400.5, "TCS": 3500.0}


def test_fetch_batch_prices_single_symbol():
    downloader = _fake_single_download(999.9)
    prices = tlp.fetch_batch_prices(["ONLYONE"], downloader=downloader)
    assert prices == {"ONLYONE": 999.9}


def test_fetch_batch_prices_missing_ticker_in_response_is_skipped():
    # RELIANCE has no Close data in the response at all -- must be silently skipped, not KeyError.
    downloader = _fake_multi_download({"TCS": 3500.0})
    prices = tlp.fetch_batch_prices(["RELIANCE", "TCS"], downloader=downloader)
    assert prices == {"TCS": 3500.0}


def test_fetch_batch_prices_download_exception_returns_empty():
    prices = tlp.fetch_batch_prices(["RELIANCE"], downloader=_raising_downloader)
    assert prices == {}


def test_fetch_batch_prices_empty_symbols_short_circuits():
    calls = []
    def _tracking_downloader(tickers, **kwargs):
        calls.append(tickers)
        return pd.DataFrame()
    assert tlp.fetch_batch_prices([], downloader=_tracking_downloader) == {}
    assert calls == []  # never even called the downloader


def test_fetch_batch_prices_none_or_empty_response():
    assert tlp.fetch_batch_prices(["X"], downloader=lambda tickers, **kw: None) == {}
    assert tlp.fetch_batch_prices(["X"], downloader=lambda tickers, **kw: pd.DataFrame()) == {}


# ---------------------------------------------------------------------------
# load_existing_cache
# ---------------------------------------------------------------------------
def test_load_existing_cache_round_trip(tmp_path):
    path = tmp_path / "cache.csv"
    pd.DataFrame([
        {"Symbol": "RELIANCE", "Live_Price": 1400.5, "Price_As_Of": "2026-08-02T10:00:00+00:00"},
    ]).to_csv(path, index=False)
    cache = tlp.load_existing_cache(str(path))
    assert cache == {"RELIANCE": {"Live_Price": 1400.5, "Price_As_Of": "2026-08-02T10:00:00+00:00"}}


def test_load_existing_cache_missing_file_returns_empty(tmp_path):
    assert tlp.load_existing_cache(str(tmp_path / "nope.csv")) == {}


# ---------------------------------------------------------------------------
# refresh_live_prices -- the merge behaviour tests care most about
# ---------------------------------------------------------------------------
def test_refresh_live_prices_updates_only_fetched_symbols():
    existing = {"OLDSYM": {"Live_Price": 50.0, "Price_As_Of": "2026-08-01T09:00:00+00:00"}}
    downloader = _fake_multi_download({"NEWSYM": 100.0})

    merged, updated = tlp.refresh_live_prices(["NEWSYM"], existing, downloader=downloader, batch_size=100)

    assert updated == {"NEWSYM"}
    assert merged["NEWSYM"]["Live_Price"] == 100.0
    # OLDSYM wasn't in this run's symbol list at all -- untouched, still present.
    assert merged["OLDSYM"] == existing["OLDSYM"]


def test_refresh_live_prices_partial_batch_failure_keeps_stale_value_for_failed_symbol():
    existing = {
        "RELIANCE": {"Live_Price": 1300.0, "Price_As_Of": "2026-08-01T09:00:00+00:00"},
        "TCS": {"Live_Price": 3400.0, "Price_As_Of": "2026-08-01T09:00:00+00:00"},
    }
    # This run's fetch only succeeds for TCS -- RELIANCE is in the requested batch but
    # absent from the response (e.g. a transient per-symbol gap in the batch response).
    downloader = _fake_multi_download({"TCS": 3500.0})

    merged, updated = tlp.refresh_live_prices(
        ["RELIANCE", "TCS"], existing, downloader=downloader, batch_size=100
    )

    assert updated == {"TCS"}
    assert merged["TCS"]["Live_Price"] == 3500.0
    assert merged["RELIANCE"] == existing["RELIANCE"]  # stale value kept, not dropped


def test_refresh_live_prices_multiple_batches():
    symbols = [f"SYM{i}" for i in range(5)]
    downloader = _fake_multi_download({s: float(i) for i, s in enumerate(symbols)})

    merged, updated = tlp.refresh_live_prices(symbols, {}, downloader=downloader, batch_size=2)

    assert updated == set(symbols)
    assert merged["SYM3"]["Live_Price"] == 3.0


def test_refresh_live_prices_total_failure_returns_no_updates():
    existing = {"RELIANCE": {"Live_Price": 1300.0, "Price_As_Of": "2026-08-01T09:00:00+00:00"}}
    merged, updated = tlp.refresh_live_prices(
        ["RELIANCE"], existing, downloader=_raising_downloader, batch_size=100
    )
    assert updated == set()
    assert merged == existing  # completely untouched


# ---------------------------------------------------------------------------
# main() end-to-end -- writes the file, and skips writing on total failure
# ---------------------------------------------------------------------------
def test_main_writes_expected_schema(tmp_path, monkeypatch):
    universe_path = tmp_path / "universe.csv"
    pd.DataFrame({"Symbol": ["RELIANCE", "TCS"]}).to_csv(universe_path, index=False)
    live_prices_path = tmp_path / "turtle_live_prices.csv"

    monkeypatch.setattr(tlp, "UNIVERSE_FILE", str(universe_path))
    monkeypatch.setattr(tlp, "LIVE_PRICES_FILE", str(live_prices_path))
    monkeypatch.setattr(
        tlp, "fetch_batch_prices",
        lambda symbols, downloader=None: {s: 100.0 + i for i, s in enumerate(symbols)},
    )
    monkeypatch.setattr(sys, "argv", ["generate_turtle_live_prices.py", "--pause", "0"])

    tlp.main()

    assert live_prices_path.exists()
    result = pd.read_csv(live_prices_path)
    assert set(result.columns) == {"Symbol", "Live_Price", "Price_As_Of"}
    assert set(result["Symbol"]) == {"RELIANCE", "TCS"}


def test_main_leaves_existing_file_untouched_on_total_failure(tmp_path, monkeypatch, capsys):
    universe_path = tmp_path / "universe.csv"
    pd.DataFrame({"Symbol": ["RELIANCE"]}).to_csv(universe_path, index=False)
    live_prices_path = tmp_path / "turtle_live_prices.csv"
    pd.DataFrame([{"Symbol": "RELIANCE", "Live_Price": 1300.0, "Price_As_Of": "2026-08-01T09:00:00+00:00"}]
                 ).to_csv(live_prices_path, index=False)
    before = live_prices_path.read_bytes()

    monkeypatch.setattr(tlp, "UNIVERSE_FILE", str(universe_path))
    monkeypatch.setattr(tlp, "LIVE_PRICES_FILE", str(live_prices_path))
    monkeypatch.setattr(tlp, "fetch_batch_prices", lambda symbols, downloader=None: {})
    monkeypatch.setattr(sys, "argv", ["generate_turtle_live_prices.py", "--pause", "0"])

    tlp.main()

    assert live_prices_path.read_bytes() == before
    assert "leaving existing cache untouched" in capsys.readouterr().out


def test_main_respects_limit(tmp_path, monkeypatch):
    universe_path = tmp_path / "universe.csv"
    pd.DataFrame({"Symbol": [f"SYM{i}" for i in range(10)]}).to_csv(universe_path, index=False)
    live_prices_path = tmp_path / "turtle_live_prices.csv"

    monkeypatch.setattr(tlp, "UNIVERSE_FILE", str(universe_path))
    monkeypatch.setattr(tlp, "LIVE_PRICES_FILE", str(live_prices_path))
    monkeypatch.setattr(
        tlp, "fetch_batch_prices",
        lambda symbols, downloader=None: {s: 1.0 for s in symbols},
    )
    monkeypatch.setattr(sys, "argv", ["generate_turtle_live_prices.py", "--limit", "3", "--pause", "0"])

    tlp.main()

    result = pd.read_csv(live_prices_path)
    assert len(result) == 3
