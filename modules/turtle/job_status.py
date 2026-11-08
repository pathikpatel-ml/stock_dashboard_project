"""
Shared read/write helpers for turtle_job_status (2026-11-08, per explicit user request).

One row per Turtle Strategy batch job (job_name = "signal" | "price" | "fundamentals"),
holding that job's own "how many of the universe got updated this run, and why not the rest"
summary -- the Turtle Strategy tab's 3 freshness banners read this for their "N of M stocks"
+ "left: reason breakdown" lines.

``fundamentals`` (the weekly 7-slice job) is the one case that ACCUMULATES across several
separate process runs instead of being a single self-contained write: each of the week's 7
slices only sees its own ~1/7 of the universe, so ``accumulate_job_status`` reads whatever's
already there, adds this slice's own counts on top, and writes the total back -- reset to a
fresh start at the week's first slice (``reset=True``, day_of_week 0) so last week's totals
don't leak into this week's. ``signal``/``price`` are both single, full-universe runs, so they
always use the simpler ``write_job_status`` (a plain overwrite, not an accumulation).
"""
from __future__ import annotations

import json
from typing import Dict, Optional

import pandas as pd

from database import market_data_writer as mdw


def _reasons_to_json(reason_counts: Dict[str, int]) -> str:
    # int(...) -- defensive against numpy int64 (e.g. straight from a pandas value_counts()),
    # which json.dumps can't serialize on its own.
    return json.dumps({str(k): int(v) for k, v in reason_counts.items()})


def parse_reason_breakdown(reason_breakdown_json: Optional[str]) -> Dict[str, int]:
    """The stored JSON string -> a plain dict, {} for None/unparseable (never raises) --
    used both internally (accumulate_job_status's read-modify-write) and by the dashboard
    callbacks that display this as a human-readable "left: reason=count, ..." line."""
    if not reason_breakdown_json:
        return {}
    try:
        parsed = json.loads(reason_breakdown_json)
        return {str(k): int(v) for k, v in parsed.items()} if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def write_job_status(job_name: str, updated_count: int, reason_counts: Dict[str, int]) -> None:
    """Plain overwrite -- for a job that's always a single, self-contained, full-universe run
    (``signal``, ``price``). Never raises; a failed write just means the dashboard falls back
    to "no count available" for that banner, same as every other optional freshness signal in
    this app."""
    try:
        conn = mdw.get_connection()
        try:
            df = pd.DataFrame([{
                "job_name": job_name,
                "updated_count": updated_count,
                "reason_breakdown": _reasons_to_json(reason_counts),
            }])
            mdw.upsert_dataframe(conn, "turtle_job_status", df, conflict_columns=["job_name"])
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: failed to write turtle_job_status for '{job_name}': {exc}")


def accumulate_job_status(job_name: str, reset: bool, updated_count_delta: int,
                           reason_counts_delta: Dict[str, int]) -> None:
    """Read-modify-write for the weekly multi-slice job (``fundamentals``) -- ``reset=True``
    (the week's first slice, day_of_week 0) starts a fresh total from just this slice's own
    numbers; every later slice that same week adds its own delta on top of whatever's already
    stored. Never raises."""
    try:
        conn = mdw.get_connection()
        try:
            if reset:
                total_count, total_reasons = updated_count_delta, dict(reason_counts_delta)
            else:
                existing = mdw.fetch_dataframe(conn, "turtle_job_status")
                row = existing[existing["job_name"] == job_name] if not existing.empty else existing
                prev_count = int(row.iloc[0]["updated_count"]) if not row.empty else 0
                prev_reasons = parse_reason_breakdown(row.iloc[0]["reason_breakdown"]) if not row.empty else {}
                total_count = prev_count + updated_count_delta
                total_reasons = dict(prev_reasons)
                for reason, count in reason_counts_delta.items():
                    total_reasons[reason] = total_reasons.get(reason, 0) + count

            df = pd.DataFrame([{
                "job_name": job_name,
                "updated_count": total_count,
                "reason_breakdown": _reasons_to_json(total_reasons),
            }])
            mdw.upsert_dataframe(conn, "turtle_job_status", df, conflict_columns=["job_name"])
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: failed to accumulate turtle_job_status for '{job_name}': {exc}")
