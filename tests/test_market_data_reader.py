"""
Unit tests for database/market_data_reader.py -- the REST-based reader the live Dash app uses
to fetch market-data tables. No live network: requests.get is stubbed.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import market_data_reader as mdr


class _FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_table_single_page(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-key")

    rows = [{"symbol": "TCS", "price": 100.0}, {"symbol": "INFY", "price": 200.0}]

    def fake_get(url, headers=None, params=None, timeout=None):
        assert url == "https://example.supabase.co/rest/v1/some_table"
        assert headers["apikey"] == "fake-key"
        return _FakeResponse(200, rows)

    monkeypatch.setattr(mdr.requests, "get", fake_get)

    df = mdr.fetch_table("some_table")
    assert list(df["symbol"]) == ["TCS", "INFY"]


def test_fetch_table_paginates_past_page_size(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-key")
    monkeypatch.setattr(mdr, "_PAGE_SIZE", 2)  # force pagination with a tiny page size

    pages = [
        [{"symbol": "A"}, {"symbol": "B"}],  # full page -> keep going
        [{"symbol": "C"}],                    # short page -> last one
    ]
    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append(headers["Range"])
        return _FakeResponse(200, pages[len(calls) - 1])

    monkeypatch.setattr(mdr.requests, "get", fake_get)

    df = mdr.fetch_table("some_table")
    assert list(df["symbol"]) == ["A", "B", "C"]
    assert calls == ["0-1", "2-3"]


def test_fetch_table_returns_empty_df_on_missing_env_vars(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    df = mdr.fetch_table("some_table")
    assert df.empty


def test_fetch_table_returns_empty_df_on_http_error(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-key")

    def fake_get(url, headers=None, params=None, timeout=None):
        return _FakeResponse(500, None)

    monkeypatch.setattr(mdr.requests, "get", fake_get)

    df = mdr.fetch_table("some_table")
    assert df.empty


def test_fetch_table_returns_empty_df_on_connection_exception(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-key")

    def fake_get(*a, **k):
        raise ConnectionError("simulated")

    monkeypatch.setattr(mdr.requests, "get", fake_get)

    df = mdr.fetch_table("some_table")
    assert df.empty


def test_fetch_table_passes_order_param(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "fake-key")

    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen.update(params)
        return _FakeResponse(200, [])

    monkeypatch.setattr(mdr.requests, "get", fake_get)

    mdr.fetch_table("some_table", order_by="symbol.asc")
    assert seen["order"] == "symbol.asc"
