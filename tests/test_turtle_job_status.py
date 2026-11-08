"""
Unit tests for modules/turtle/job_status.py (2026-11-08) -- the shared read/write helpers for
turtle_job_status, which the Turtle Strategy tab's 3 freshness banners read for their
"N of M stocks" + "left: reason breakdown" lines. No live network: database.market_data_writer
is stubbed.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import job_status as js


class _FakeConn:
    def close(self):
        pass


# ---------------------------------------------------------------------------
# parse_reason_breakdown
# ---------------------------------------------------------------------------
def test_parse_reason_breakdown_round_trips_json():
    assert js.parse_reason_breakdown('{"fetch_error": 5, "no_monthly_data": 3}') == {
        "fetch_error": 5, "no_monthly_data": 3,
    }


def test_parse_reason_breakdown_none_returns_empty_dict():
    assert js.parse_reason_breakdown(None) == {}


def test_parse_reason_breakdown_empty_string_returns_empty_dict():
    assert js.parse_reason_breakdown("") == {}


def test_parse_reason_breakdown_garbage_returns_empty_dict():
    assert js.parse_reason_breakdown("not json at all") == {}


def test_parse_reason_breakdown_non_dict_json_returns_empty_dict():
    assert js.parse_reason_breakdown("[1, 2, 3]") == {}


# ---------------------------------------------------------------------------
# write_job_status -- plain overwrite (signal, price)
# ---------------------------------------------------------------------------
def test_write_job_status_upserts_expected_row(monkeypatch):
    captured = {}

    def fake_upsert_dataframe(conn, table, df, conflict_columns):
        captured["table"] = table
        captured["row"] = df.iloc[0].to_dict()
        captured["conflict_columns"] = conflict_columns
        return 1

    monkeypatch.setattr(js.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(js.mdw, "upsert_dataframe", fake_upsert_dataframe)

    js.write_job_status("signal", 2244, {"insufficient_monthly_data": 11, "fetch_error": 386})

    assert captured["table"] == "turtle_job_status"
    assert captured["conflict_columns"] == ["job_name"]
    assert captured["row"]["job_name"] == "signal"
    assert captured["row"]["updated_count"] == 2244
    assert js.parse_reason_breakdown(captured["row"]["reason_breakdown"]) == {
        "insufficient_monthly_data": 11, "fetch_error": 386,
    }


def test_write_job_status_never_raises_on_db_failure(monkeypatch):
    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(js.mdw, "get_connection", boom)
    js.write_job_status("price", 100, {"never_fetched": 5})  # must not raise


def test_write_job_status_coerces_numpy_like_counts(monkeypatch):
    """pandas value_counts() hands back numpy int64, which json.dumps can't serialize on its
    own -- must not raise and must round-trip as a plain int."""
    import numpy as np
    captured = {}

    def fake_upsert_dataframe(conn, table, df, conflict_columns):
        captured["row"] = df.iloc[0].to_dict()
        return 1

    monkeypatch.setattr(js.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(js.mdw, "upsert_dataframe", fake_upsert_dataframe)

    js.write_job_status("signal", 10, {"fetch_error": np.int64(7)})

    assert js.parse_reason_breakdown(captured["row"]["reason_breakdown"]) == {"fetch_error": 7}


# ---------------------------------------------------------------------------
# accumulate_job_status -- read-modify-write (fundamentals, the weekly 7-slice job)
# ---------------------------------------------------------------------------
def test_accumulate_job_status_reset_starts_fresh(monkeypatch):
    captured = {}
    monkeypatch.setattr(js.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        js.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns: captured.setdefault("row", df.iloc[0].to_dict()),
    )
    # fetch_dataframe must NOT be consulted at all on a reset -- any prior-week leftovers
    # would otherwise leak into this week's fresh total.
    monkeypatch.setattr(js.mdw, "fetch_dataframe", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("reset=True must not read the existing row")
    ))

    js.accumulate_job_status("fundamentals", reset=True, updated_count_delta=375,
                              reason_counts_delta={"no_ttm_data": 20})

    assert captured["row"]["updated_count"] == 375
    assert js.parse_reason_breakdown(captured["row"]["reason_breakdown"]) == {"no_ttm_data": 20}


def test_accumulate_job_status_adds_onto_existing_total(monkeypatch):
    captured = {}
    monkeypatch.setattr(js.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        js.mdw, "fetch_dataframe",
        lambda conn, table: pd.DataFrame([{
            "job_name": "fundamentals", "updated_count": 1000,
            "reason_breakdown": '{"no_ttm_data": 50}',
        }]),
    )
    monkeypatch.setattr(
        js.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns: captured.setdefault("row", df.iloc[0].to_dict()),
    )

    js.accumulate_job_status("fundamentals", reset=False, updated_count_delta=375,
                              reason_counts_delta={"no_ttm_data": 20, "fetch_failed": 5})

    assert captured["row"]["updated_count"] == 1375
    assert js.parse_reason_breakdown(captured["row"]["reason_breakdown"]) == {
        "no_ttm_data": 70, "fetch_failed": 5,
    }


def test_accumulate_job_status_no_existing_row_starts_from_zero(monkeypatch):
    captured = {}
    monkeypatch.setattr(js.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(js.mdw, "fetch_dataframe", lambda conn, table: pd.DataFrame())
    monkeypatch.setattr(
        js.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns: captured.setdefault("row", df.iloc[0].to_dict()),
    )

    js.accumulate_job_status("fundamentals", reset=False, updated_count_delta=375,
                              reason_counts_delta={"no_ttm_data": 20})

    assert captured["row"]["updated_count"] == 375


def test_accumulate_job_status_never_raises_on_db_failure(monkeypatch):
    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(js.mdw, "get_connection", boom)
    js.accumulate_job_status("fundamentals", reset=True, updated_count_delta=10,
                              reason_counts_delta={})  # must not raise
