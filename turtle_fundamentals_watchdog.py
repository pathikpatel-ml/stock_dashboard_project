#!/usr/bin/env python
"""
Hourly watchdog for the Sunday 7-slice turtle_fundamentals.yml run (2026-11-09, per explicit
user request).

GitHub Actions' own schedule triggers are well documented elsewhere in this repo as occasionally
landing hours late or skipping outright (see turtle_fundamentals.yml's and
weekly_stock_screening.yml's own schedule comments) -- so instead of trusting each of those 7
cron entries to fire cleanly on its own, this runs independently every hour across the whole
window those 7 slices occupy. For each slice whose scheduled time has already passed, it checks
turtle_fundamentals_slice_status (written by generate_turtle_fundamentals.py itself) to see
whether that slice actually started/finished/succeeded this week, and fires a workflow_dispatch
retrigger if it didn't -- up to modules.turtle.slice_status.MAX_ATTEMPTS total attempts per slice
per week. This never replaces the 7 native cron triggers, only fills whatever gap they leave.

All the actual decision logic (pending/running/stuck/failed/success, the retry cap, previous-week
staleness) lives in modules/turtle/slice_status.py::decide_slices_to_trigger -- kept pure and
DB-free there so every corner case is unit-tested without touching Postgres or the network. This
script is just: read status -> decide -> dispatch.

Usage
-----
    python turtle_fundamentals_watchdog.py              # the normal hourly check
    python turtle_fundamentals_watchdog.py --dry-run     # log decisions only, never dispatch
"""
import argparse
import os
import sys
from datetime import datetime, timezone

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from modules.turtle import slice_status

WORKFLOW_FILE = "turtle_fundamentals.yml"


def trigger_workflow_dispatch(day_of_week: int, token: str, repo: str,
                               workflow: str = WORKFLOW_FILE, ref: str = "main") -> bool:
    """Fires the same workflow_dispatch a human clicking "Run workflow" would, with this one
    slice's day_of_week input. Returns True on success (HTTP 204), False on anything else --
    never raises, so one failed dispatch can't stop the watchdog from trying the others this
    same check."""
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"ref": ref, "inputs": {"day_of_week": str(day_of_week)}}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 204:
            return True
        print(f"WARNING: workflow_dispatch for day_of_week={day_of_week} failed: "
              f"HTTP {resp.status_code} {resp.text[:300]}")
        return False
    except Exception as exc:
        print(f"WARNING: workflow_dispatch for day_of_week={day_of_week} raised: {exc}")
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="log decisions only, never dispatch")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    status_rows = slice_status.read_all_slice_status()
    to_trigger = slice_status.decide_slices_to_trigger(now, status_rows)

    print(f"Watchdog check at {now.isoformat()}")
    print(f"  slice_status: {status_rows}")
    if not to_trigger:
        print("Nothing overdue -- every due slice is pending-not-yet-due, running, succeeded, "
              "or already exhausted its retry budget this week.")
        return

    print(f"Slices needing a trigger this check: {to_trigger}")
    if args.dry_run:
        print("--dry-run given: not actually dispatching.")
        return

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("ERROR: GITHUB_TOKEN/GITHUB_REPOSITORY not set -- cannot dispatch.")
        sys.exit(1)

    any_failed = False
    for day_of_week in to_trigger:
        ok = trigger_workflow_dispatch(day_of_week, token, repo)
        print(f"  day_of_week={day_of_week}: {'dispatched' if ok else 'FAILED to dispatch'}")
        any_failed = any_failed or not ok

    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
