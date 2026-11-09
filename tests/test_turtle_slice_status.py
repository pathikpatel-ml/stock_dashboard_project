"""
Unit tests for modules/turtle/slice_status.py (2026-11-09) -- per-slice run tracking for the
Sunday 7-slice turtle_fundamentals.yml job, read by turtle_fundamentals_watchdog.py to decide
whether a slice is overdue and needs a workflow_dispatch retrigger.

No live network/DB: database.market_data_writer is stubbed for mark_slice_running/
mark_slice_finished/read_all_slice_status. decide_slices_to_trigger is pure (no I/O) and tested
directly against constructed status dicts.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtle import slice_status as ss


class _FakeConn:
    def close(self):
        pass


# ---------------------------------------------------------------------------
# week_anchor_utc / scheduled_time_utc -- pin the exact schedule, since
# decide_slices_to_trigger's correctness depends entirely on these being right.
# ---------------------------------------------------------------------------
def test_week_anchor_utc_from_saturday_itself():
    now = datetime(2026, 11, 14, 23, 0, tzinfo=timezone.utc)  # a Saturday
    assert ss.week_anchor_utc(now) == datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)


def test_week_anchor_utc_from_sunday():
    now = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)  # the following Sunday
    assert ss.week_anchor_utc(now) == datetime(2026, 11, 14, 0, 0, tzinfo=timezone.utc)


def test_week_anchor_utc_from_midweek():
    now = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)  # a Wednesday
    assert ss.week_anchor_utc(now) == datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)


def test_scheduled_time_utc_slice_0_matches_cron():
    # turtle_fundamentals.yml: cron '37 19 * * 6' (Saturday 19:37 UTC) -- slice 0.
    now = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
    assert ss.scheduled_time_utc(now, 0) == datetime(2026, 11, 14, 19, 37, tzinfo=timezone.utc)


def test_scheduled_time_utc_slice_6_matches_cron():
    # turtle_fundamentals.yml: cron '37 13 * * 0' (Sunday 13:37 UTC) -- slice 6.
    now = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
    assert ss.scheduled_time_utc(now, 6) == datetime(2026, 11, 15, 13, 37, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# mark_slice_running
# ---------------------------------------------------------------------------
def test_mark_slice_running_first_time_sets_attempt_count_1(monkeypatch):
    captured = {}
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(ss.mdw, "fetch_dataframe", lambda conn, table: pd.DataFrame())
    monkeypatch.setattr(
        ss.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns, touch_updated_at=True: captured.setdefault(
            "row", df.iloc[0].to_dict()
        ),
    )

    ss.mark_slice_running(3)

    assert captured["row"]["day_of_week"] == 3
    assert captured["row"]["status"] == "running"
    assert captured["row"]["attempt_count"] == 1


def test_mark_slice_running_same_cycle_increments_attempt_count(monkeypatch):
    now = datetime.now(timezone.utc)
    anchor = ss.week_anchor_utc(now)
    captured = {}
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        ss.mdw, "fetch_dataframe",
        lambda conn, table: pd.DataFrame([{
            "day_of_week": 3, "status": "failed", "attempt_count": 1,
            "started_at": anchor + timedelta(hours=5), "finished_at": None,
            "ok_count": None, "fail_count": None,
        }]),
    )
    monkeypatch.setattr(
        ss.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns, touch_updated_at=True: captured.setdefault(
            "row", df.iloc[0].to_dict()
        ),
    )

    ss.mark_slice_running(3)

    assert captured["row"]["attempt_count"] == 2
    assert captured["row"]["status"] == "running"


def test_mark_slice_running_previous_cycle_row_resets_attempt_count(monkeypatch):
    now = datetime.now(timezone.utc)
    anchor = ss.week_anchor_utc(now)
    captured = {}
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        ss.mdw, "fetch_dataframe",
        lambda conn, table: pd.DataFrame([{
            "day_of_week": 3, "status": "success", "attempt_count": 3,
            "started_at": anchor - timedelta(days=1),  # last week's leftover row
            "finished_at": anchor - timedelta(hours=23), "ok_count": 375, "fail_count": 10,
        }]),
    )
    monkeypatch.setattr(
        ss.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns, touch_updated_at=True: captured.setdefault(
            "row", df.iloc[0].to_dict()
        ),
    )

    ss.mark_slice_running(3)

    assert captured["row"]["attempt_count"] == 1


def test_mark_slice_running_never_raises_on_db_failure(monkeypatch):
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    ss.mark_slice_running(0)  # must not raise


# ---------------------------------------------------------------------------
# mark_slice_finished
# ---------------------------------------------------------------------------
def test_mark_slice_finished_success(monkeypatch):
    captured = {}
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        ss.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns, touch_updated_at=True: captured.setdefault(
            "row", df.iloc[0].to_dict()
        ),
    )

    ss.mark_slice_finished(2, success=True, ok_count=380, fail_count=5)

    assert captured["row"]["status"] == "success"
    assert captured["row"]["ok_count"] == 380
    assert captured["row"]["fail_count"] == 5


def test_mark_slice_finished_failure(monkeypatch):
    captured = {}
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        ss.mdw, "upsert_dataframe",
        lambda conn, table, df, conflict_columns, touch_updated_at=True: captured.setdefault(
            "row", df.iloc[0].to_dict()
        ),
    )

    ss.mark_slice_finished(2, success=False)

    assert captured["row"]["status"] == "failed"


def test_mark_slice_finished_never_raises_on_db_failure(monkeypatch):
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    ss.mark_slice_finished(2, success=False)  # must not raise


# ---------------------------------------------------------------------------
# read_all_slice_status
# ---------------------------------------------------------------------------
def test_read_all_slice_status_keys_by_day_of_week(monkeypatch):
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(
        ss.mdw, "fetch_dataframe",
        lambda conn, table: pd.DataFrame([
            {"day_of_week": 0, "status": "success", "attempt_count": 1},
            {"day_of_week": 1, "status": "running", "attempt_count": 1},
        ]),
    )

    result = ss.read_all_slice_status()

    assert set(result) == {0, 1}
    assert result[0]["status"] == "success"


def test_read_all_slice_status_empty_table_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: _FakeConn())
    monkeypatch.setattr(ss.mdw, "fetch_dataframe", lambda conn, table: pd.DataFrame())
    assert ss.read_all_slice_status() == {}


def test_read_all_slice_status_never_raises_on_db_failure(monkeypatch):
    monkeypatch.setattr(ss.mdw, "get_connection", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ss.read_all_slice_status() == {}


# ---------------------------------------------------------------------------
# decide_slices_to_trigger -- the actual watchdog decision logic (pure, no I/O)
# ---------------------------------------------------------------------------
_NOW = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)  # a Sunday, mid-way through the cycle
_ANCHOR = ss.week_anchor_utc(_NOW)


def _due_time(day_of_week: int, minutes_after: int = 0) -> datetime:
    return ss.scheduled_time_utc(_NOW, day_of_week) + timedelta(minutes=minutes_after)


def _already_succeeded(now: datetime) -> dict:
    """A settled row for any OTHER slice that's already due by ``now`` -- used so a test
    focused on one particular slice's behavior isn't also tripped up by earlier slices showing
    up as "no row -> pending" in the same result."""
    return {"status": "success", "attempt_count": 1, "started_at": now - timedelta(hours=1)}


def test_not_due_yet_is_never_triggered():
    # _NOW is 10:00 UTC Sunday -- slices 5 (10:37) and 6 (13:37) haven't reached their scheduled
    # time + grace yet, so only slices 0-4 (19:37/22:37 Sat, 01:37/04:37/07:37 Sun) show up.
    assert ss.decide_slices_to_trigger(_NOW, {}) == [0, 1, 2, 3, 4]


def test_due_with_no_row_at_all_triggers():
    now = _due_time(0, minutes_after=ss.GRACE_MINUTES + 1)
    assert ss.decide_slices_to_trigger(now, {}) == [0]


def test_due_but_within_grace_period_does_not_trigger():
    now = _due_time(0, minutes_after=ss.GRACE_MINUTES - 1)
    assert ss.decide_slices_to_trigger(now, {}) == []


def test_due_with_stale_previous_cycle_row_triggers():
    now = _due_time(0, minutes_after=ss.GRACE_MINUTES + 1)
    stale_row = {
        "status": "success", "attempt_count": 1,
        "started_at": _ANCHOR - timedelta(days=1),  # belongs to last week, not this cycle
    }
    assert ss.decide_slices_to_trigger(now, {0: stale_row}) == [0]


def test_running_recently_does_not_trigger():
    now = _due_time(2, minutes_after=ss.GRACE_MINUTES + 1)
    row = {"status": "running", "attempt_count": 1, "started_at": now - timedelta(minutes=10)}
    rows = {0: _already_succeeded(now), 1: _already_succeeded(now), 2: row}
    assert ss.decide_slices_to_trigger(now, rows) == []


def test_running_stuck_past_timeout_triggers_if_attempts_remain():
    now = _due_time(2, minutes_after=ss.GRACE_MINUTES + 1)
    row = {
        "status": "running", "attempt_count": 1,
        "started_at": now - timedelta(minutes=ss.STUCK_AFTER_MINUTES + 1),
    }
    rows = {0: _already_succeeded(now), 1: _already_succeeded(now), 2: row}
    assert ss.decide_slices_to_trigger(now, rows) == [2]


def test_running_stuck_past_timeout_does_not_trigger_if_attempts_exhausted():
    now = _due_time(2, minutes_after=ss.GRACE_MINUTES + 1)
    row = {
        "status": "running", "attempt_count": ss.MAX_ATTEMPTS,
        "started_at": now - timedelta(minutes=ss.STUCK_AFTER_MINUTES + 1),
    }
    rows = {0: _already_succeeded(now), 1: _already_succeeded(now), 2: row}
    assert ss.decide_slices_to_trigger(now, rows) == []


def test_failed_with_attempts_remaining_triggers():
    now = _due_time(1, minutes_after=ss.GRACE_MINUTES + 1)
    row = {"status": "failed", "attempt_count": 1, "started_at": now - timedelta(minutes=30)}
    rows = {0: _already_succeeded(now), 1: row}
    assert ss.decide_slices_to_trigger(now, rows) == [1]


def test_failed_at_max_attempts_does_not_trigger():
    now = _due_time(1, minutes_after=ss.GRACE_MINUTES + 1)
    row = {
        "status": "failed", "attempt_count": ss.MAX_ATTEMPTS,
        "started_at": now - timedelta(minutes=30),
    }
    rows = {0: _already_succeeded(now), 1: row}
    assert ss.decide_slices_to_trigger(now, rows) == []


def test_success_never_triggers_regardless_of_attempt_count():
    now = _due_time(1, minutes_after=ss.GRACE_MINUTES + 1)
    row = {"status": "success", "attempt_count": 1, "started_at": now - timedelta(minutes=30)}
    rows = {0: _already_succeeded(now), 1: row}
    assert ss.decide_slices_to_trigger(now, rows) == []


def test_mixed_slices_returns_sorted_list_of_only_the_ones_needing_action():
    now = _due_time(3, minutes_after=ss.GRACE_MINUTES + 1)  # slices 0,1,2,3 are due by now
    rows = {
        0: {"status": "success", "attempt_count": 1, "started_at": now - timedelta(hours=10)},
        1: {"status": "running", "attempt_count": 1, "started_at": now - timedelta(minutes=5)},
        2: {"status": "failed", "attempt_count": 1, "started_at": now - timedelta(minutes=40)},
        # slice 3 has no row at all -- never started.
    }
    assert ss.decide_slices_to_trigger(now, rows) == [2, 3]


def test_attempt_count_missing_or_none_treated_as_zero():
    now = _due_time(1, minutes_after=ss.GRACE_MINUTES + 1)
    row = {"status": "failed", "attempt_count": None, "started_at": now - timedelta(minutes=30)}
    rows = {0: _already_succeeded(now), 1: row}
    assert ss.decide_slices_to_trigger(now, rows) == [1]
