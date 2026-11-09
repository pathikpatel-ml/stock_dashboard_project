"""
Unit tests for generate_turtle_fundamentals.py::main()'s slice_status integration (2026-11-09)
-- the watchdog (turtle_fundamentals_watchdog.py) can only do its job if this script reliably
marks each slice running at the start and success/failed at the end, including on a genuine
crash. No live network/DB: every I/O boundary (universe loading, screener.in fetch, Postgres) is
stubbed.
"""
import os
import sys

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


def _stub_common_io(monkeypatch, symbols):
    monkeypatch.setattr(gtf, "load_universe_symbols_for_slicing", lambda day_of_week: symbols)
    monkeypatch.setattr(gtf, "slice_for_day", lambda syms, day_of_week: syms)  # the %7 slicing
    # itself is covered by test_generate_turtle_fundamentals_slicing.py -- irrelevant here, and
    # would otherwise silently drop this test's tiny fake universe for most day_of_week values.
    monkeypatch.setattr(gtf.sf, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.nse_sh, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(gtf.mdw, "upsert_dataframe", lambda conn, table, df, conflict_columns: len(df))
    monkeypatch.setattr(gtf.job_status, "accumulate_job_status", lambda *a, **k: None)
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda self, *a, **k: None)


def test_main_marks_slice_running_then_success(monkeypatch, tmp_path):
    _stub_common_io(monkeypatch, ["AAA", "BBB"])
    monkeypatch.setattr(gtf, "CHECKPOINT_FILE", str(tmp_path / "checkpoint.csv"))
    monkeypatch.setattr(
        gtf, "fetch_one",
        lambda symbol, session, retries, pause, nse_session=None: {
            "Symbol": symbol, "TTM_Net_Profit": 100, "TTM_Net_Sales": 200,
            **{c: None for c in gtf.OUTPUT_COLUMNS if c not in ("Symbol", "TTM_Net_Profit", "TTM_Net_Sales")},
        },
    )

    calls = {"running": [], "finished": []}
    monkeypatch.setattr(gtf.slice_status, "mark_slice_running", lambda dow: calls["running"].append(dow))
    monkeypatch.setattr(
        gtf.slice_status, "mark_slice_finished",
        lambda dow, success, ok_count=0, fail_count=0: calls["finished"].append((dow, success, ok_count, fail_count)),
    )

    monkeypatch.setattr(sys, "argv", ["generate_turtle_fundamentals.py", "--day-of-week", "3"])
    gtf.main()

    assert calls["running"] == [3]
    assert calls["finished"] == [(3, True, 2, 0)]


def test_main_marks_slice_failed_and_reraises_on_crash(monkeypatch, tmp_path):
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

    monkeypatch.setattr(sys, "argv", ["generate_turtle_fundamentals.py", "--day-of-week", "2"])
    with pytest.raises(RuntimeError, match="screener.in exploded"):
        gtf.main()

    assert calls["running"] == [2]
    assert calls["finished"] == [(2, False)]


def test_main_full_universe_never_touches_slice_status(monkeypatch, tmp_path):
    monkeypatch.setattr(gtf, "load_universe_symbols", lambda: ["AAA"])
    monkeypatch.setattr(gtf.sf, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.nse_sh, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(gtf.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(gtf.mdw, "upsert_dataframe", lambda conn, table, df, conflict_columns: len(df))
    monkeypatch.setattr(gtf.job_status, "accumulate_job_status", lambda *a, **k: None)
    monkeypatch.setattr(pd.DataFrame, "to_csv", lambda self, *a, **k: None)
    monkeypatch.setattr(gtf, "CHECKPOINT_FILE", str(tmp_path / "checkpoint.csv"))
    monkeypatch.setattr(
        gtf, "fetch_one",
        lambda symbol, session, retries, pause, nse_session=None: {
            "Symbol": symbol, "TTM_Net_Profit": 100, "TTM_Net_Sales": 200,
            **{c: None for c in gtf.OUTPUT_COLUMNS if c not in ("Symbol", "TTM_Net_Profit", "TTM_Net_Sales")},
        },
    )

    called = []
    monkeypatch.setattr(gtf.slice_status, "mark_slice_running", lambda dow: called.append("running"))
    monkeypatch.setattr(gtf.slice_status, "mark_slice_finished", lambda *a, **k: called.append("finished"))

    monkeypatch.setattr(sys, "argv", ["generate_turtle_fundamentals.py", "--full-universe"])
    gtf.main()

    assert called == []
