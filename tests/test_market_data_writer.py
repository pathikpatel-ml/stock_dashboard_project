"""
Unit tests for database/market_data_writer.py -- the shared bulk-upsert helper the batch/cron
scripts use to write to Postgres. No live network/DB: psycopg2's execute_values is stubbed so
the SQL-building logic is exercised without touching a real database.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import market_data_writer as mdw


class _FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConnection:
    def __init__(self):
        self.committed = False

    def cursor(self):
        return _FakeCursor()

    def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def _capture_execute_values(monkeypatch):
    calls = []

    def fake_execute_values(cur, sql, values, page_size=None):
        calls.append({"sql": sql, "values": values, "page_size": page_size})

    monkeypatch.setattr(mdw, "execute_values", fake_execute_values)
    return calls


def test_upsert_dataframe_builds_insert_and_update_clause(_capture_execute_values):
    conn = _FakeConnection()
    df = pd.DataFrame([{"symbol": "TCS", "price": 100.0}, {"symbol": "INFY", "price": 200.0}])

    n = mdw.upsert_dataframe(conn, "some_table", df, conflict_columns=["symbol"])

    assert n == 2
    assert conn.committed is True
    call = _capture_execute_values[0]
    assert "INSERT INTO some_table (symbol, price) VALUES %s" in call["sql"]
    assert "ON CONFLICT (symbol) DO UPDATE SET" in call["sql"]
    assert "price = EXCLUDED.price" in call["sql"]
    assert "updated_at = NOW()" in call["sql"]  # touch_updated_at defaults True
    assert call["values"] == [("TCS", 100.0), ("INFY", 200.0)]


def test_upsert_dataframe_touch_updated_at_false_omits_it(_capture_execute_values):
    conn = _FakeConnection()
    df = pd.DataFrame([{"symbol": "TCS", "signal_date": "2026-08-20"}])

    mdw.upsert_dataframe(
        conn, "history_table", df, conflict_columns=["symbol", "signal_date"], touch_updated_at=False
    )

    call = _capture_execute_values[0]
    assert "updated_at" not in call["sql"]


def test_upsert_dataframe_explicit_update_columns_excludes_others(_capture_execute_values):
    conn = _FakeConnection()
    df = pd.DataFrame([{"symbol": "TCS", "price": 100.0, "immutable_col": "X"}])

    mdw.upsert_dataframe(
        conn, "some_table", df, conflict_columns=["symbol"], update_columns=["price"]
    )

    call = _capture_execute_values[0]
    assert "price = EXCLUDED.price" in call["sql"]
    assert "immutable_col = EXCLUDED.immutable_col" not in call["sql"]


def test_upsert_dataframe_converts_nan_to_none(_capture_execute_values):
    conn = _FakeConnection()
    df = pd.DataFrame([{"symbol": "TCS", "price": np.nan}])

    mdw.upsert_dataframe(conn, "some_table", df, conflict_columns=["symbol"])

    call = _capture_execute_values[0]
    assert call["values"] == [("TCS", None)]


def test_upsert_dataframe_empty_df_is_noop(_capture_execute_values):
    conn = _FakeConnection()
    n = mdw.upsert_dataframe(conn, "some_table", pd.DataFrame(), conflict_columns=["symbol"])
    assert n == 0
    assert _capture_execute_values == []
    assert conn.committed is False


def test_upsert_dataframe_none_df_is_noop(_capture_execute_values):
    conn = _FakeConnection()
    n = mdw.upsert_dataframe(conn, "some_table", None, conflict_columns=["symbol"])
    assert n == 0
    assert _capture_execute_values == []


def test_upsert_dataframe_no_update_columns_uses_do_nothing(_capture_execute_values):
    conn = _FakeConnection()
    df = pd.DataFrame([{"symbol": "TCS"}])

    mdw.upsert_dataframe(
        conn, "some_table", df, conflict_columns=["symbol"], touch_updated_at=False
    )

    call = _capture_execute_values[0]
    assert "DO NOTHING" in call["sql"]


# ---------------------------------------------------------------------------
# replace_table_contents -- delete-all + bulk-insert, for tables needing REPLACE not upsert
# ---------------------------------------------------------------------------
class _FakeCursorRecordingExecute(_FakeCursor):
    def __init__(self, log):
        self._log = log

    def execute(self, sql, params=None):
        self._log.append(("execute", sql))


class _FakeConnectionWithExecute(_FakeConnection):
    def __init__(self):
        super().__init__()
        self.log = []

    def cursor(self):
        return _FakeCursorRecordingExecute(self.log)


def test_replace_table_contents_deletes_then_inserts(_capture_execute_values):
    conn = _FakeConnectionWithExecute()
    df = pd.DataFrame([{"symbol": "TCS", "buy_date": "2026-01-01"}])

    n = mdw.replace_table_contents(conn, "v20_signals_latest", df)

    assert n == 1
    assert conn.committed is True
    assert conn.log == [("execute", "DELETE FROM v20_signals_latest")]
    call = _capture_execute_values[0]
    assert "INSERT INTO v20_signals_latest (symbol, buy_date) VALUES %s" in call["sql"]
    assert call["values"] == [("TCS", "2026-01-01")]


def test_replace_table_contents_empty_df_still_deletes(_capture_execute_values):
    # Unlike upsert_dataframe, an empty/None df is NOT a no-op here -- "nothing currently
    # qualifies" is a real, legitimate result that must clear out yesterday's stale rows.
    conn = _FakeConnectionWithExecute()

    n = mdw.replace_table_contents(conn, "v20_signals_latest", pd.DataFrame())

    assert n == 0
    assert conn.committed is True
    assert conn.log == [("execute", "DELETE FROM v20_signals_latest")]
    assert _capture_execute_values == []  # no INSERT issued for an empty frame


def test_replace_table_contents_none_df_still_deletes(_capture_execute_values):
    conn = _FakeConnectionWithExecute()
    n = mdw.replace_table_contents(conn, "v20_signals_latest", None)
    assert n == 0
    assert conn.log == [("execute", "DELETE FROM v20_signals_latest")]


def test_get_connection_raises_clear_error_without_env_var(monkeypatch):
    monkeypatch.delenv("MARKET_DATA_DB_URL", raising=False)
    with pytest.raises(RuntimeError, match="MARKET_DATA_DB_URL"):
        mdw.get_connection()
