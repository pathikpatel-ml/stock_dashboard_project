"""
Unit tests for modules/nse_category_fetcher.py -- Nifty 50/100/200 membership fetch/merge/write.

No live network: the HTTP layer is stubbed with a fake session so parsing/merging/writing are
exercised end-to-end without depending on NSE's archive endpoints being reachable in CI.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules import nse_category_fetcher as ncf

SAMPLE_NIFTY50_CSV = (
    b"Company Name,Industry,Symbol,Series,ISIN Code\n"
    b"Adani Enterprises Ltd.,Metals & Mining,ADANIENT,EQ,INE423A01024\n"
    b"Reliance Industries Ltd.,Oil & Gas,RELIANCE,EQ,INE002A01018\n"
)


class _FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeSession:
    """Simulates flaky NSE archives: fails ``fail_times`` times, then succeeds."""

    def __init__(self, content=SAMPLE_NIFTY50_CSV, fail_times=0):
        self.content = content
        self.fail_times = fail_times
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            return _FakeResponse(status_code=500, content=b"")
        return _FakeResponse(status_code=200, content=self.content)

    def close(self):
        pass


# ---------------------------------------------------------------------------
# fetch_index_constituents
# ---------------------------------------------------------------------------
def test_fetch_index_constituents_parses_symbols():
    session = _FakeSession()
    symbols = ncf.fetch_index_constituents("NIFTY 50", session=session, retries=1, pause=0)
    assert symbols == ["ADANIENT", "RELIANCE"]


def test_fetch_index_constituents_unknown_index_returns_none():
    assert ncf.fetch_index_constituents("NOT_AN_INDEX") is None


def test_fetch_index_constituents_retries_then_succeeds():
    session = _FakeSession(fail_times=1)
    symbols = ncf.fetch_index_constituents("NIFTY 50", session=session, retries=3, pause=0)
    assert symbols == ["ADANIENT", "RELIANCE"]
    assert session.calls == 2


def test_fetch_index_constituents_gives_up_after_retries_exhausted():
    session = _FakeSession(fail_times=99)
    symbols = ncf.fetch_index_constituents("NIFTY 50", session=session, retries=2, pause=0)
    assert symbols is None


# ---------------------------------------------------------------------------
# build_categories_map / merge_categories_maps
# ---------------------------------------------------------------------------
def test_build_categories_map_merges_multi_index_membership():
    result = ncf.build_categories_map({
        "NIFTY 50": ["ADANIENT", "RELIANCE"],
        "NIFTY 200": ["ADANIENT", "TCS"],
    })
    assert result["ADANIENT"] == ["NIFTY 200", "NIFTY 50"] or sorted(result["ADANIENT"]) == ["NIFTY 200", "NIFTY 50"]
    assert result["RELIANCE"] == ["NIFTY 50"]
    assert result["TCS"] == ["NIFTY 200"]


def test_merge_preserves_thematic_tags_not_in_replace_prefixes():
    existing = {"ABB": ["NIFTY ENERGY"], "ADANIENT": ["NIFTY 50", "NIFTY METAL"]}
    new = {"ADANIENT": ["NIFTY 50", "NIFTY 100"]}
    merged = ncf.merge_categories_maps(existing, new)
    assert merged["ABB"] == ["NIFTY ENERGY"]  # untouched -- no Nifty 50/100/200 tag to replace
    assert set(merged["ADANIENT"]) == {"NIFTY 50", "NIFTY 100", "NIFTY METAL"}


def test_merge_drops_stale_index_tags_that_fell_out_of_the_fresh_fetch():
    existing = {"STOCKX": ["NIFTY 50", "NIFTY PHARMA"]}
    # STOCKX fell out of Nifty 50 in the fresh fetch, but is now in Nifty 100 instead.
    new = {"NIFTY 100": ["STOCKX"]} and ncf.build_categories_map({"NIFTY 100": ["STOCKX"]})
    merged = ncf.merge_categories_maps(existing, new)
    assert set(merged["STOCKX"]) == {"NIFTY 100", "NIFTY PHARMA"}
    assert "NIFTY 50" not in merged["STOCKX"]


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------
def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / "nse_categories.csv")
    categories_map = {"ADANIENT": ["NIFTY 50", "NIFTY METAL"], "ABB": ["NIFTY ENERGY"]}
    ncf.save_nse_categories_to_csv(categories_map, path)

    raw = pd.read_csv(path)
    assert list(raw.columns) == ["Symbol", "NSE_Categories"]
    row = raw[raw["Symbol"] == "ADANIENT"].iloc[0]
    assert row["NSE_Categories"] == "NIFTY 50,NIFTY METAL"

    reloaded = ncf.load_categories_map_from_csv(path)
    assert reloaded == {"ADANIENT": ["NIFTY 50", "NIFTY METAL"], "ABB": ["NIFTY ENERGY"]}


def test_load_categories_map_from_missing_file_returns_empty():
    assert ncf.load_categories_map_from_csv("/no/such/file.csv") == {}


# ---------------------------------------------------------------------------
# refresh_nifty_membership -- the end-to-end entrypoint called from stock_screener
# ---------------------------------------------------------------------------
def test_refresh_nifty_membership_merges_into_existing_file(tmp_path, monkeypatch):
    path = str(tmp_path / "nse_categories.csv")
    ncf.save_nse_categories_to_csv({"ABB": ["NIFTY ENERGY"], "ADANIENT": ["NIFTY PHARMA"]}, path)

    def fake_fetch(index_name, session=None, retries=3, pause=1.5):
        return {"NIFTY 50": ["ADANIENT"], "NIFTY 100": ["ADANIENT", "ABB"]}.get(index_name)

    monkeypatch.setattr(ncf, "fetch_index_constituents", fake_fetch)
    monkeypatch.setattr(ncf, "_new_session", lambda: _FakeSession())

    refreshed = ncf.refresh_nifty_membership(path, index_names=["NIFTY 50", "NIFTY 100", "NIFTY 200"])
    assert refreshed is True

    result = ncf.load_categories_map_from_csv(path)
    assert set(result["ADANIENT"]) == {"NIFTY 50", "NIFTY 100", "NIFTY PHARMA"}
    assert set(result["ABB"]) == {"NIFTY 100", "NIFTY ENERGY"}


def test_refresh_nifty_membership_drops_stale_sectoral_tags_too(tmp_path, monkeypatch):
    # 2026-08-20: replace_tags now covers every index actually fetched this run, not just the
    # original Nifty 50/100/200 -- a stock that fell out of a sectoral index (e.g. NIFTY MEDIA)
    # must lose that stale tag on refresh, the same way Nifty 50/100/200 already did.
    path = str(tmp_path / "nse_categories.csv")
    ncf.save_nse_categories_to_csv({"STOCKX": ["NIFTY MEDIA", "NIFTY PHARMA"]}, path)

    def fake_fetch(index_name, session=None, retries=3, pause=1.5):
        return {"NIFTY MEDIA": ["OTHERSTOCK"]}.get(index_name)  # STOCKX fell out

    monkeypatch.setattr(ncf, "fetch_index_constituents", fake_fetch)
    monkeypatch.setattr(ncf, "_new_session", lambda: _FakeSession())

    refreshed = ncf.refresh_nifty_membership(path, index_names=["NIFTY MEDIA"])
    assert refreshed is True

    result = ncf.load_categories_map_from_csv(path)
    assert "NIFTY MEDIA" not in result.get("STOCKX", [])
    assert "NIFTY PHARMA" in result["STOCKX"]  # untouched -- not an index this run fetched


def test_index_urls_covers_expected_sectoral_and_size_indices():
    expected = {
        "NIFTY 50", "NIFTY 100", "NIFTY 200",
        "NIFTY AUTO", "NIFTY BANK", "NIFTY ENERGY", "NIFTY FMCG", "NIFTY IT", "NIFTY METAL",
        "NIFTY PHARMA", "NIFTY REALTY", "NIFTY MIDCAP 50", "NIFTY SMALLCAP 50",
        "NIFTY CONSUMER DURABLES", "NIFTY MEDIA", "NIFTY OIL AND GAS", "NIFTY PSU BANK",
    }
    assert expected == set(ncf.INDEX_URLS)


def test_refresh_nifty_membership_leaves_file_untouched_on_total_failure(tmp_path, monkeypatch):
    path = str(tmp_path / "nse_categories.csv")
    ncf.save_nse_categories_to_csv({"ABB": ["NIFTY ENERGY"]}, path)
    before = path and open(path, "rb").read()

    monkeypatch.setattr(ncf, "fetch_index_constituents", lambda *a, **k: None)
    monkeypatch.setattr(ncf, "_new_session", lambda: _FakeSession())

    refreshed = ncf.refresh_nifty_membership(path)
    assert refreshed is False
    after = open(path, "rb").read()
    assert before == after
