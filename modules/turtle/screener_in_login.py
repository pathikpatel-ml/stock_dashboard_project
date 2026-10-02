"""
screener.in's own real Promoter Pledge data, via a logged-in account's custom screening query.

2026-10-02, after two other sources were tried and rejected:
  * NSE's own ``/api/corporate-pledgedata`` -- caught returning STALE data as if current
    (verified live on Suzlon: showed a historical 59.37%% pledge via a CDN-cached snapshot, when
    the real current figure, independently confirmed, is 0%% -- fully resolved years ago).
  * Moneycontrol's per-symbol shareholding-pattern page -- data itself was accurate, but ~50%%
    of requests hit a 20s timeout before succeeding on retry, making a full-universe run take
    an estimated ~12 hours; infeasible for a single CI job.

screener.in's own free-tier query language has a real "Pledged percentage" field -- confirmed
live, exact matches against independent reporting (JSW Steel 11.60%%, Asian Paints 9.54%%,
the latter also an exact match against Moneycontrol's own figure). Running a CUSTOM query
(``/screen/raw/``) requires a logged-in account (the user's own, provided and stored in
SCREENER_IN_EMAIL/SCREENER_IN_PASSWORD).

PAGINATION IS CURSOR-BASED (``Market Capitalization < <last_seen>``, sorted by market cap
descending), NOT offset-based (``page=N``) -- this was a real, hard-won fix, not a style choice.
Offset pagination (``page=N``) was confirmed LIVE to be unreliable specifically when "Pledged
percentage" is part of the query: the exact same page number could return a full page of data on
one request and an empty/truncated one moments later, with retries sometimes not even
recovering it (one real run stopped after only ~54 of ~2,600 companies despite 3 retries per
page). The likely cause: "Pledged percentage" is an expensive, live-computed (not indexed)
field, and offset pagination over such a field typically forces the database to recompute and
discard every prior page's worth of that field just to reach a later page -- a well-known
performance anti-pattern that gets more likely to time out/truncate the deeper you page.
Cursor-based pagination (filtering on the real, presumably-indexed "Market Capitalization"
column, which is used for ordering, not the expensive field) sidesteps this entirely -- each
request only ever needs to compute Pledged %% for the specific rows it returns. Confirmed live:
10 consecutive cursor-paginated requests returned exactly 50/50/50... rows with zero truncation,
covering the market-cap range from Reliance Industries (largest) down through ~500 companies,
where the EXACT SAME underlying query via offset pagination was unreliable past ~50-150 rows.

Login triggers a real anti-brute-force rate limit after repeated rapid attempts ("Exceeded
maximum attempts. You can try again after 5 minutes.") -- confirmed temporary, not a lockout.
This is a non-issue in production (one login per batch run), but matters for testing: don't
hammer ``login()`` in a tight loop.

Results are keyed by WHATEVER identifier the row's own company-name link uses -- confirmed live
this is INCONSISTENT across companies, not a single scheme: large/well-known companies link as
``/company/RELIANCE/consolidated/`` (the exact same NSE-symbol slug used for the per-symbol P&L
fetch elsewhere in this app), while others link as ``/company/523222/`` (a numeric BSE code).
Missing this cost a real debugging cycle: an early version's regex only matched the numeric
form, silently dropping every row using the symbol form -- including Reliance Industries, the
very first result when sorted by market cap. The caller should try an NSE-symbol lookup first,
falling back to BSE code (see ``modules/turtle/standalone_fundamentals.py::parse_bse_code`` for
where each row's own BSE code comes from -- zero extra network cost, already on the per-symbol
page) for rows that used the numeric form.
"""
from __future__ import annotations

import re
import time
import urllib.parse
from typing import Dict, Optional, Tuple

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

_LOGIN_URL = "https://www.screener.in/login/"
_QUERY_URL = "https://www.screener.in/screen/raw/"
_CSRF_RE = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
# Matches BOTH link forms -- /company/523222/ (BSE code) and /company/RELIANCE/consolidated/
# (NSE symbol slug) -- capturing whatever identifier is in the first path segment either way.
_COMPANY_HREF_RE = re.compile(r"^/company/([^/]+)/?")

PAGE_SIZE = 50
_MCAP_COLUMN_HEADER = "Mar CapRs.Cr."
_PLEDGE_COLUMN_HEADER = "Pledged%"


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    return session


def login(session: requests.Session, email: str, password: str) -> bool:
    """Log ``session`` into screener.in. Returns True on success. Never raises -- a login
    failure (wrong credentials, network issue, or the temporary rate limit after repeated rapid
    attempts) just means the caller gets no pledge data this run, not a crashed batch."""
    try:
        resp = session.get(_LOGIN_URL, timeout=20)
        m = _CSRF_RE.search(resp.text)
        if m is None:
            return False
        session.headers["Referer"] = _LOGIN_URL
        resp = session.post(_LOGIN_URL, data={
            "csrfmiddlewaretoken": m.group(1),
            "username": email,
            "password": password,
            "next": "",
        }, timeout=20)
        return "Logout" in resp.text
    except Exception:
        return False


def _build_query(cursor_mcap: Optional[float]) -> str:
    if cursor_mcap is None:
        return "Market Capitalization > 0 AND\nPledged percentage >= 0"
    return (
        f"Market Capitalization > 0 AND\n"
        f"Market Capitalization < {cursor_mcap} AND\n"
        f"Pledged percentage >= 0"
    )


def _fetch_cursor_page(
    session: requests.Session, cursor_mcap: Optional[float],
) -> Tuple[list, Optional[float]]:
    """One page's [(identifier, pledge_pct), ...] plus the market-cap value to use as the NEXT
    cursor (the smallest market cap seen on this page -- the next page asks for strictly less
    than this). ``identifier`` is EITHER an NSE symbol (e.g. "RELIANCE") or a numeric BSE code
    (e.g. "523222"), whichever that row's own company-name link used (see module docstring).
    Returns ([], None) on any failure or a genuinely empty result."""
    params = {
        "query": _build_query(cursor_mcap), "limit": str(PAGE_SIZE),
        "sort": "market capitalization", "order": "desc",
    }
    url = _QUERY_URL + "?" + urllib.parse.urlencode(params)
    try:
        resp = session.get(url, timeout=30)
    except Exception:
        return [], None
    if resp.status_code != 200:
        return [], None
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if table is None:
        return [], None
    tbody = table.find("tbody")
    if tbody is None:
        return [], None
    header_cells = [th.get_text(strip=True) for th in table.find_all("th")]
    try:
        pledge_col = header_cells.index(_PLEDGE_COLUMN_HEADER)
        mcap_col = header_cells.index(_MCAP_COLUMN_HEADER)
    except ValueError:
        return [], None

    pairs = []
    next_cursor = None
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) <= max(pledge_col, mcap_col):
            continue
        name_link = tds[1].find("a") if len(tds) > 1 else None
        href = name_link.get("href", "") if name_link else ""
        m = _COMPANY_HREF_RE.match(href)
        try:
            mcap = float(tds[mcap_col].get_text(strip=True).replace(",", ""))
        except ValueError:
            continue
        if next_cursor is None or mcap < next_cursor:
            next_cursor = mcap
        if m is None:
            continue
        pledge_text = tds[pledge_col].get_text(strip=True)
        try:
            pairs.append((m.group(1).upper(), float(pledge_text)))
        except ValueError:
            continue
    return pairs, next_cursor


def fetch_all_pledge_data(
    session: requests.Session, max_iterations: int = 100, pause: float = 0.3,
) -> Dict[str, float]:
    """(identifier -> pledge %%) for every company screener.in's query returns -- identifier is
    EITHER an NSE symbol or a numeric BSE code, whichever that row happened to use (see module
    docstring) -- walking down the market-cap range via cursor-based pagination (see module
    docstring for why -- offset pagination was confirmed unreliable for this specific
    expensive-to-compute field).
    ``max_iterations`` * ``PAGE_SIZE`` = 5,000 companies, comfortably above this app's
    ~2,600-symbol universe, as a safety cap against an infinite loop. Never raises -- a failure
    partway through just means whatever pages succeeded so far are returned; the caller treats
    any symbol missing from the result as unknown pledge data (None), same as any other optional
    field in this pipeline.
    """
    result: Dict[str, float] = {}
    cursor: Optional[float] = None
    for _ in range(max_iterations):
        pairs, next_cursor = _fetch_cursor_page(session, cursor)
        if not pairs or next_cursor is None:
            break
        for bse_code, pledge_pct in pairs:
            result[bse_code] = pledge_pct
        if len(pairs) < PAGE_SIZE:
            break  # fewer than a full page -- genuine end of the result set
        cursor = next_cursor
        if pause:
            time.sleep(pause)
    return result
