"""
NSE's own (not screener.in's) promoter-holding history.

2026-10-02: screener.in's free Shareholding Pattern table only has ~3 years (12 quarters) of
promoter-holding history. NSE itself -- the primary regulatory source, keyed by the exact same
NSE symbol already used everywhere in this app, no name/code mapping needed -- publishes
``/api/corporate-share-holdings-master``: quarterly promoter-holding % (``pr_and_prgrp``),
confirmed live to go back to ~Dec 2021 (~5.5 years, better than screener.in's ~3) and no
further; NSE's own digitized archive for this disclosure type simply starts there. Reverse-
engineered live from NSE's own JS bundle (``corporate-filings.js``) since it's undocumented;
confirmed with a 100-symbol stress test (mixed large/mid/small-cap, including distressed names)
-- zero failures, consistent across repeated fetches (the CDN cache here serves a stable,
correct snapshot).

This module ONLY covers promoter HOLDING now. An earlier version also covered promoter PLEDGE
via NSE's ``/api/corporate-pledgedata`` -- removed 2026-10-02 after it was caught returning
stale data as if current (verified live: showed Suzlon at a historical 59.37%% pledge, via a
CDN-cached snapshot, when the real current figure -- independently confirmed -- is 0%%, fully
resolved). A Moneycontrol-based replacement and a screener.in login-gated screening query were
also each tried in turn and ultimately dropped entirely per the user's own final decision
(2026-10-02) -- Promoter Pledge is no longer computed anywhere in this pipeline; see
modules/turtle/quality_flags.py's module docstring for the full history.
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple

import requests

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-pledged-data",
}

_MONTH_NUM = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

Series = Tuple[List[str], List[float]]


def new_session() -> requests.Session:
    """Public entry point for callers wanting to reuse one warmed-up session across many
    fetch calls (connection reuse across a full-universe batch run) -- mirrors
    modules/turtle/standalone_fundamentals.py::new_session's exact shape."""
    session = requests.Session()
    session.headers.update(_HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=15)
    except Exception:
        pass  # cookie warm-up is best-effort
    return session


def _sort_key(date_str: str):
    # NSE dates look like "30-JUN-2026" -- sort chronologically, not alphabetically.
    try:
        day, mon, year = date_str.split("-")
        return (int(year), _MONTH_NUM.get(mon.upper(), 0), int(day))
    except Exception:
        return (0, 0, 0)


def fetch_promoter_holding_history(
    symbol: str, session: Optional[requests.Session] = None, retries: int = 3, pause: float = 1.0,
) -> Optional[Series]:
    """Quarterly promoter holding %% history, oldest to newest, as a (periods, values) tuple
    matching modules/turtle/standalone_fundamentals.py's Series shape -- directly interchangeable
    with quality_flags.py's promoter_holding_flag/promoter_holding_change. None on any
    network/parse failure or an empty result (never raises)."""
    url = f"https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol={symbol}"
    own_session = session is None
    session = session or new_session()
    try:
        for attempt in range(retries):
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    if not isinstance(data, list) or not data:
                        return None
                    rows = sorted(data, key=lambda r: _sort_key(r.get("date", "")))
                    periods, values = [], []
                    for row in rows:
                        date = row.get("date")
                        pct = row.get("pr_and_prgrp")
                        if date is None or pct is None:
                            continue
                        try:
                            values.append(float(pct))
                            periods.append(date)
                        except (TypeError, ValueError):
                            continue
                    return (periods, values) if periods else None
            except Exception:
                pass
            time.sleep(pause * (attempt + 1))
        return None
    finally:
        if own_session:
            session.close()
