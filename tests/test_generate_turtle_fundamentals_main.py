"""
Unit tests for generate_turtle_fundamentals.py::main()'s slice_status integration (2026-11-09,
extended 2026-11-22) -- the watchdog (turtle_fundamentals_watchdog.py) can only do its job if
this script reliably marks each slice running at the start and success/failed at the end,
including on a genuine crash. The dashboard's "N of M stocks" total (turtle_job_status) must be
DERIVED from every slice's own latest row (slice_status.compute_week_totals), not accumulated
per-run, so a slice the watchdog retriggers can't get double-counted -- see that function's
docstring for the live incident this replaced. No live network/DB: every I/O boundary (universe
loading, screener.in fetch, Postgres) is stubbed.
"""
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_turtle_fundamentals as gtf


class _FakeConn:
    def close(self):
        pass


class _FakeSession:
    def close(self):
        pass


def _fetch_one_stub(symbol, session, retries, pause, nse_session=None):
    return {
        "Symbol": symbol, "TTM_Net_Profit": 100, "TTM_Net_Sales": 200,
        **{c: None for c in gtf.OUTPUT_COLUMNS if c not in ("Symbol", "TTM_Net_Profit", "TTM_Net_Sales")},
    }


def _stub_common_io(monkeypatch, symbols):
    monkeypatch.setattr(gtf, "load_universe_symbols_for_slicing", lambda day_of_week: symbols)
    monkeypatch.setattr(gtf, "slice_for_day", lambda syms, day_of_week: syms)  # the %7 slicing
    # itself is covered by test_generate_turtle_fundamentals_slicing.py -- irrelevant here, and
    # would otherwise silently drop this test's tiny fake universe for most day_of_week values.
    monkeypatch.setattr(gtf.sf, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.nse_sh, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(gtf.mdw, "upsert_dataframe", lambda conn, table, df, conflict_columns: len(df))
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda self, *a, **k: None)


def test_main_marks_slice_running_then_success_and_writes_derived_total(monkeypatch, tmp_path):
    _stub_common_io(monkeypatch, ["AAA", "BBB"])
    monkeypatch.setattr(gtf, "CHECKPOINT_FILE", str(tmp_path / "checkpoint.csv"))
    monkeypatch.setattr(gtf, "fetch_one", _fetch_one_stub)

    calls = {"running": [], "finished": []}
    monkeypatch.setattr(gtf.slice_status, "mark_slice_running", lambda dow: calls["running"].append(dow))
    monkeypatch.setattr(
        gtf.slice_status, "mark_slice_finished",
        lambda dow, success, ok_count=0, fail_count=0: calls["finished"].append((dow, success, ok_count, fail_count)),
    )
    # Simulates the DB already reflecting this slice's own just-written row (ok=2,fail=0 --
    # this run's 2 symbols) alongside an unrelated slice 0 already done earlier this week --
    # the derived total written to turtle_job_status must be the SUM of both.
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        gtf.slice_status, "read_all_slice_status",
        lambda: {
            0: {"status": "success", "attempt_count": 1, "started_at": now, "ok_count": 300, "fail_count": 10},
            3: {"status": "success", "attempt_count": 1, "started_at": now, "ok_count": 2, "fail_count": 0},
        },
    )
    written = {}
    monkeypatch.setattr(
        gtf.job_status, "write_job_status",
        lambda job_name, count, reasons: written.update(job_name=job_name, count=count, reasons=reasons),
    )

    monkeypatch.setattr(sys, "argv", ["generate_turtle_fundamentals.py", "--day-of-week", "3"])
    gtf.main()

    assert calls["running"] == [3]
    assert calls["finished"] == [(3, True, 2, 0)]
    assert written == {"job_name": "fundamentals", "count": 302, "reasons": {"no_ttm_data": 10}}


def test_main_marks_slice_failed_and_reraises_on_crash_without_writing_job_status(monkeypatch, tmp_path):
    _stub_common_io(monkeypatch, ["AAA"])
    monkeypatch.setattr(gtf, "CHECKPOINT_FILE", str(tmp_path / "checkpoint.csv"))

    def boom(symbol, session, retries, pause, nse_session=None):
        raise RuntimeError("screener.in exploded")

    monkeypatch.setattr(gtf, "fetch_one", boom)

    calls = {"running": [], "finished": []}
    monkeypatch.setattr(gtf.slice_status, "mark_slice_running", lambda dow: calls["running"].append(dow))
    monkeypatch.setattr(
        gtf.slice_status, "mark_slice_finished",
        lambda dow, success, ok_count=0, fail_count=0: calls["finished"].append((dow, success)),
    )
    written = []
    monkeypatch.setattr(gtf.job_status, "write_job_status", lambda *a, **k: written.append((a, k)))

    monkeypatch.setattr(sys, "argv", ["generate_turtle_fundamentals.py", "--day-of-week", "2"])
    with pytest.raises(RuntimeError, match="screener.in exploded"):
        gtf.main()

    assert calls["running"] == [2]
    assert calls["finished"] == [(2, False)]
    assert written == []  # a crashed slice must never contribute to the dashboard's total


def test_main_full_universe_never_touches_slice_status_and_writes_its_own_total(monkeypatch, tmp_path):
    monkeypatch.setattr(gtf, "load_universe_symbols", lambda: ["AAA"])
    monkeypatch.setattr(gtf.sf, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.nse_sh, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(gtf.mdw, "upsert_dataframe", lambda conn, table, df, conflict_columns: len(df))
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda self, *a, **k: None)
    monkeypatch.setattr(gtf, "CHECKPOINT_FILE", str(tmp_path / "checkpoint.csv"))
    monkeypatch.setattr(gtf, "fetch_one", _fetch_one_stub)

    called = []
    monkeypatch.setattr(gtf.slice_status, "mark_slice_running", lambda dow: called.append("running"))
    monkeypatch.setattr(gtf.slice_status, "mark_slice_finished", lambda *a, **k: called.append("finished"))
    written = {}
    monkeypatch.setattr(
        gtf.job_status, "write_job_status",
        lambda job_name, count, reasons: written.update(job_name=job_name, count=count, reasons=reasons),
    )

    monkeypatch.setattr(sys, "argv", ["generate_turtle_fundamentals.py", "--full-universe"])
    gtf.main()

    assert called == []
    assert written == {"job_name": "fundamentals", "count": 1, "reasons": {"no_ttm_data": 0}}
