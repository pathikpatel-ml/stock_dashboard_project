"""
Per-slice run tracking for the Sunday 7-slice turtle_fundamentals.yml job (2026-11-09, per
explicit user request).

``turtle_job_status``'s "fundamentals" row only ever holds ONE aggregate total across the
whole week (see job_status.py) -- there's no way to ask "did slice 3 specifically start,
finish, or fail THIS week", which is exactly what turtle_fundamentals_watchdog.py needs every
hour to decide whether a slice needs triggering/retriggering. This module is that per-slice
state: one row per ``day_of_week`` (0..6) in ``turtle_fundamentals_slice_status``, written by
generate_turtle_fundamentals.py itself (mark_slice_running at the start of a run,
mark_slice_finished at the end) and read by the watchdog (read_all_slice_status +
decide_slices_to_trigger, kept pure/DB-free here so every corner case is unit-testable without
touching Postgres or the network).

Reset each week by real elapsed time relative to the week's own anchor (the most recent
Saturday 00:00 UTC) -- not a day-of-week label -- the same lesson job_status.py's
STALE_AFTER_DAYS fix already learned: a row's age, not which slice happens to run first, is
what tells you whether it belongs to the current cycle.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd

from database import market_data_writer as mdw

TABLE = "turtle_fundamentals_slice_status"

# Each slice's scheduled trigger time, as (days after the cycle's anchor Saturday 00:00 UTC,
# hour, minute) -- mirrors turtle_fundamentals.yml's 7 cron entries exactly (see that file's own
# schedule comment for the IST-clock-time rationale). day_offset 0 = Saturday, 1 = the following
# Sunday.
SLICE_SCHEDULE_UTC = {
    0: (0, 19, 37),
    1: (0, 22, 37),
    2: (1, 1, 37),
    3: (1, 4, 37),
    4: (1, 7, 37),
    5: (1, 10, 37),
    6: (1, 13, 37),
}

# 2026-11-09, per explicit user request: original cron-triggered attempt + 2 watchdog retries,
# then stop retriggering and just let the dashboard show that slice as failed for the week --
# avoids hammering screener.in forever against a slice that's genuinely, not just unluckily, broken.
MAX_ATTEMPTS = 3

# How long past its scheduled time a slice gets before the watchdog considers it overdue.
GRACE_MINUTES = 20

# A "running" slice older than this is presumed killed by turtle_fundamentals.yml's own
# 90-minute job timeout without ever reaching its own mark_slice_finished call -- GitHub
# Actions' timeout kill is a hard process termination, which a Python try/finally often doesn't
# get to run for. Treated the same as a failure (eligible for retrigger), not left "running"
# forever.
STUCK_AFTER_MINUTES = 120


def week_anchor_utc(now: datetime) -> datetime:
    """Midnight UTC of the Saturday that starts the current (or most recently started) 7-slice
    cycle -- every SLICE_SCHEDULE_UTC offset is measured from this moment, and any stored row
    timestamped before it belongs to a previous, already-finished cycle."""
    days_since_saturday = (now.weekday() - 5) % 7  # Python: Mon=0 .. Sat=5, Sun=6
    anchor_date = (now - timedelta(days=days_since_saturday)).date()
    return datetime(anchor_date.year, anchor_date.month, anchor_date.day, tzinfo=timezone.utc)


def scheduled_time_utc(now: datetime, day_of_week: int) -> datetime:
    """This cycle's scheduled start time for ``day_of_week`` (0..6), as a UTC datetime."""
    day_offset, hour, minute = SLICE_SCHEDULE_UTC[day_of_week]
    return week_anchor_utc(now) + timedelta(days=day_offset, hours=hour, minutes=minute)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def mark_slice_running(day_of_week: int) -> None:
    """Call at the start of a slice's run (cron-triggered or watchdog-retriggered).

    Resets to a fresh attempt_count of 1 if the existing row belongs to an earlier cycle (its
    own started_at predates this cycle's anchor); otherwise increments this cycle's own count.
    Never raises -- a failed write here just means the watchdog can't see this slice's state
    this week (it will fall back to treating it as "never started" and may retrigger it even if
    it's actually running) -- a false-positive retrigger is far cheaper than crashing the actual
    data-fetch job over a status-table hiccup.
    """
    try:
        now = _now_utc()
        anchor = week_anchor_utc(now)
        conn = mdw.get_connection()
        try:
            existing = mdw.fetch_dataframe(conn, TABLE)
            row = existing[existing["day_of_week"] == day_of_week] if not existing.empty else existing

            attempt_count = 1
            if not row.empty:
                started_at = pd.to_datetime(row.iloc[0]["started_at"], errors="coerce", utc=True)
                if pd.notna(started_at) and started_at >= anchor:
                    attempt_count = int(row.iloc[0]["attempt_count"]) + 1

            df = pd.DataFrame([{
                "day_of_week": day_of_week, "status": "running", "attempt_count": attempt_count,
                "started_at": now, "finished_at": None, "ok_count": None, "fail_count": None,
            }])
            mdw.upsert_dataframe(conn, TABLE, df, conflict_columns=["day_of_week"], touch_updated_at=False)
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: failed to mark slice {day_of_week} running in {TABLE}: {exc}")


def mark_slice_finished(day_of_week: int, success: bool, ok_count: int = 0, fail_count: int = 0) -> None:
    """Call at the end of a slice's run, success or failure. Never raises -- a status-table
    write hiccup here can't mask the real success/failure of the data fetch itself (the caller
    still propagates its own exception/exit code independently of this)."""
    try:
        conn = mdw.get_connection()
        try:
            df = pd.DataFrame([{
                "day_of_week": day_of_week, "status": "success" if success else "failed",
                "finished_at": _now_utc(), "ok_count": ok_count, "fail_count": fail_count,
            }])
            mdw.upsert_dataframe(conn, TABLE, df, conflict_columns=["day_of_week"], touch_updated_at=False)
        finally:
            conn.close()
    except Exception as exc:
        status = "success" if success else "failed"
        print(f"WARNING: failed to mark slice {day_of_week} {status} in {TABLE}: {exc}")


def read_all_slice_status() -> Dict[int, dict]:
    """Every tracked slice's current row, keyed by day_of_week -- {} on any read failure (the
    watchdog treats that as "can't see anything, do nothing this check" rather than guessing)."""
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, TABLE)
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: failed to read {TABLE}: {exc}")
        return {}
    if df.empty:
        return {}
    return {int(row["day_of_week"]): row.to_dict() for _, row in df.iterrows()}


def decide_slices_to_trigger(now: datetime, status_rows: Dict[int, dict]) -> List[int]:
    """Pure decision logic, no I/O -- for each slice whose scheduled time + GRACE_MINUTES has
    already passed this cycle, decide whether it needs a workflow_dispatch trigger right now.

    Per slice:
    - Not due yet (now < scheduled time + grace) -> skip.
    - No row this cycle (never started, or only a previous week's stale row survives) -> trigger.
    - status == "success" -> skip, done.
    - status == "running" and started recently (within STUCK_AFTER_MINUTES) -> skip, still in flight.
    - status == "running" but stuck past STUCK_AFTER_MINUTES, or status == "failed" -> trigger,
      unless attempt_count has already reached MAX_ATTEMPTS (give up, let it show as failed).

    Returns the sorted list of day_of_week values to trigger; empty if nothing needs it.
    """
    anchor = week_anchor_utc(now)
    to_trigger: List[int] = []

    for day_of_week in sorted(SLICE_SCHEDULE_UTC):
        due_at = scheduled_time_utc(now, day_of_week) + timedelta(minutes=GRACE_MINUTES)
        if now < due_at:
            continue

        row = status_rows.get(day_of_week)
        started_at = _parse_ts(row.get("started_at")) if row else None
        belongs_to_this_cycle = started_at is not None and started_at >= anchor

        if not belongs_to_this_cycle:
            to_trigger.append(day_of_week)
            continue

        status = row.get("status")
        attempt_count = int(row.get("attempt_count") or 0)

        if status == "success":
            continue
        if status == "running":
            if now - started_at <= timedelta(minutes=STUCK_AFTER_MINUTES):
                continue  # still legitimately in flight
            # else: stuck past its own timeout -- fall through, treated like a failure below

        if attempt_count >= MAX_ATTEMPTS:
            continue  # already retried enough this cycle -- give up

        to_trigger.append(day_of_week)

    return to_trigger


def _parse_ts(value) -> Optional[datetime]:
    if value is None:
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime()
