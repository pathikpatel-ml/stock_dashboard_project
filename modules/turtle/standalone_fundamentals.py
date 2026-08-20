"""
Consolidated TTM + historical-annual Net Profit and Net Sales for the Turtle Strategy,
scraped from screener.in's ``/consolidated/`` company page.

Why this exists: comparing TTM profit against a historical max needs both figures on the
SAME table, SAME (Cr) units, SAME basis, so there's no EPS/shares-outstanding unit-conversion
needed: ATH_Profit_Flag and ATH_Sales_Flag both become a direct
``TTM >= max(all annual years, including the latest)`` comparison -- see
``modules.turtle.compute``. Consolidated (not standalone) was chosen 2026-08-19 -- a company
without subsidiaries has no real ``/consolidated/`` page and screener.in serves the same
(standalone) numbers either way, so this only actually changes anything for companies that do
have subsidiaries.

``https://www.screener.in/company/{symbol}/consolidated/`` -- its "Profit & Loss" table
already has a pre-computed **TTM column** -- no need to sum quarters ourselves -- plus every
annual year screener.in renders (typically ~12 years). Parsing is split from fetching
(``parse_profit_and_loss`` takes raw HTML) so it's unit-tested against real saved page
fixtures, no live network needed.

Some NSE tickers don't match their screener.in slug 1:1 (renames, etc. -- e.g. ZOMATO's
screener.in company is ETERNAL). ``resolve_screener_slug`` falls back to screener.in's own
search API (``/api/company/search/?q=...``) to find the right slug when the direct URL has no
usable Profit & Loss data.
"""
from __future__ import annotations

import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def new_session() -> requests.Session:
    """Public entry point for callers (e.g. generate_turtle_fundamentals.py) that want to
    reuse one warmed-up session across many fetch_profit_and_loss calls, for connection reuse
    across a full-universe batch run."""
    session = requests.Session()
    session.headers.update(_HEADERS)
    try:
        session.get("https://www.screener.in", timeout=15)
    except Exception:
        pass  # cookie warm-up is best-effort
    return session


_new_session = new_session  # internal alias -- kept for the module's own call sites below


def _to_number(text: str) -> Optional[float]:
    text = text.strip().replace(",", "")
    if not text or text in ("-", "--"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_ttm_net_profit(html: str) -> Optional[float]:
    """Extract the standalone TTM Net Profit (Cr) from a screener.in company page's
    "Profit & Loss" table. Returns None if the section/row/TTM column can't be found --
    callers should treat that as "no data for this symbol", not an error.
    """
    soup = BeautifulSoup(html, "html.parser")

    pl_heading = None
    for h in soup.find_all("h2"):
        if h.get_text(strip=True) == "Profit & Loss":
            pl_heading = h
            break
    if pl_heading is None:
        return None

    section = pl_heading.find_parent("section")
    table = section.find("table") if section else None
    if table is None:
        return None

    rows = table.find_all("tr")
    if not rows:
        return None

    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    periods = header_cells[1:]  # header_cells[0] is the blank corner cell
    if "TTM" not in periods:
        return None
    ttm_index = periods.index("TTM")

    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        label = re.sub(r"\+$", "", cells[0]).strip()
        if label != "Net Profit":
            continue
        values = cells[1:]
        if ttm_index >= len(values):
            return None
        return _to_number(values[ttm_index])

    return None


def fetch_ttm_net_profit(
    symbol: str,
    session: Optional[requests.Session] = None,
    retries: int = 3,
    pause: float = 1.5,
) -> Optional[float]:
    """Fetch + parse the standalone TTM Net Profit (Cr) for ``symbol``. Never raises --
    network/parse failures return None so a single bad symbol can't crash a batch run.
    """
    url = f"https://www.screener.in/company/{symbol}/"
    own_session = session is None
    session = session or _new_session()
    try:
        for attempt in range(retries):
            try:
                resp = session.get(url, timeout=20)
                if resp.status_code == 200 and resp.content:
                    value = parse_ttm_net_profit(resp.text)
                    if value is not None:
                        return value
                    return None  # page loaded fine, just no matching data -- don't retry
            except Exception:
                pass
            time.sleep(pause * (attempt + 1))
        return None
    finally:
        if own_session:
            session.close()


_SALES_ROW_LABELS = {"Sales", "Revenue"}  # screener.in uses "Revenue+" for banks/NBFCs, "Sales+" otherwise
_PROFIT_ROW_LABELS = {"Net Profit"}


def _find_pl_table(soup: BeautifulSoup):
    pl_heading = None
    for h in soup.find_all("h2"):
        if h.get_text(strip=True) == "Profit & Loss":
            pl_heading = h
            break
    if pl_heading is None:
        return None
    section = pl_heading.find_parent("section")
    return section.find("table") if section else None


def _extract_pl_row(rows, label_set) -> Optional[list]:
    """Returns the raw cell-text values (period columns only, header excluded) for the first
    row whose label (trailing '+' stripped) is in ``label_set``, or None if no such row."""
    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        label = re.sub(r"\+$", "", cells[0]).strip()
        if label in label_set:
            return cells[1:]
    return None


def parse_profit_and_loss(html: str) -> Optional[dict]:
    """Extract standalone TTM + historical-annual Net Profit and Net Sales (Cr) from a
    screener.in company page's "Profit & Loss" table.

    Returns ``{"ttm_net_profit", "annual_net_profit", "ttm_net_sales", "annual_net_sales"}``
    -- the two ``annual_*`` entries are lists of every non-TTM period column's value (screener.in
    typically renders ~12 years), including the latest/most-recent year. Returns None if the
    Profit & Loss section/table itself can't be found -- callers should treat that as "no data
    for this symbol" (e.g. wrong slug), not an error. A found table with a missing row/column
    (e.g. no TTM) degrades gracefully: that one field comes back None/empty, not the whole dict.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_pl_table(soup)
    if table is None:
        return None

    rows = table.find_all("tr")
    if not rows:
        return None

    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    periods = header_cells[1:]  # header_cells[0] is the blank corner cell
    ttm_index = periods.index("TTM") if "TTM" in periods else None

    def _split(values: Optional[list]):
        if not values:
            return None, []
        ttm = _to_number(values[ttm_index]) if ttm_index is not None and ttm_index < len(values) else None
        annual = [
            _to_number(v) for i, v in enumerate(values) if i != ttm_index
        ]
        annual = [v for v in annual if v is not None]
        return ttm, annual

    profit_values = _extract_pl_row(rows, _PROFIT_ROW_LABELS)
    sales_values = _extract_pl_row(rows, _SALES_ROW_LABELS)

    ttm_profit, annual_profit = _split(profit_values)
    ttm_sales, annual_sales = _split(sales_values)

    return {
        "ttm_net_profit": ttm_profit,
        "annual_net_profit": annual_profit,
        "ttm_net_sales": ttm_sales,
        "annual_net_sales": annual_sales,
    }


def resolve_screener_slug(symbol: str, session: Optional[requests.Session] = None) -> Optional[str]:
    """Look up ``symbol``'s screener.in slug via their company-search API, for the cases where
    the NSE ticker doesn't match the slug 1:1 (renames etc. -- e.g. ZOMATO -> ETERNAL). Returns
    the bare slug (e.g. ``"ETERNAL"``), or None if the search returned nothing usable. Never
    raises -- a lookup failure just means "can't resolve this one", not a batch-crashing error.
    """
    own_session = session is None
    session = session or _new_session()
    try:
        resp = session.get(
            "https://www.screener.in/api/company/search/", params={"q": symbol}, timeout=15
        )
        if resp.status_code != 200:
            return None
        results = resp.json()
        if not results:
            return None
        url = results[0].get("url", "")
        match = re.search(r"/company/([^/]+)/", url)
        return match.group(1) if match else None
    except Exception:
        return None
    finally:
        if own_session:
            session.close()


def _has_usable_data(result: Optional[dict]) -> bool:
    """True if a parse_profit_and_loss() result actually has at least one real figure.

    A company with no subsidiaries still returns a 200 OK for its ``/consolidated/`` URL --
    screener.in renders the full row-label shell of the Profit & Loss table but with every
    data cell empty (nothing to consolidate), which ``parse_profit_and_loss`` correctly parses
    as a non-None dict of all-None/empty fields. Treating that as "success" (as an earlier
    version of this function did) meant ~590 of 2,406 real symbols -- about a quarter of the
    universe -- silently got zero fundamentals data. This check is what triggers the
    standalone fallback below instead.
    """
    if not result:
        return False
    return result.get("ttm_net_profit") is not None or result.get("ttm_net_sales") is not None


def fetch_profit_and_loss(
    symbol: str,
    session: Optional[requests.Session] = None,
    retries: int = 3,
    pause: float = 1.5,
    use_search_fallback: bool = True,
) -> Optional[dict]:
    """Fetch + parse consolidated TTM/annual Net Profit + Net Sales (Cr) for ``symbol``,
    falling back to standalone for companies with no real consolidated statement.

    For each candidate slug (direct symbol, then the search-API-resolved slug for renamed
    tickers -- see ``_candidate_slugs``), tries ``/consolidated/`` first; if that loads but has
    no usable data (see ``_has_usable_data``'s docstring -- a company with no subsidiaries has
    nothing to consolidate), falls back to that same slug's plain (standalone) URL, since for
    such a company standalone IS the complete picture. Never raises -- network/parse/lookup
    failures all return None so a single bad symbol can't crash a full-universe batch run.
    """
    own_session = session is None
    session = session or _new_session()
    try:
        for candidate in _candidate_slugs(symbol, session, use_search_fallback):
            for url in (
                f"https://www.screener.in/company/{candidate}/consolidated/",
                f"https://www.screener.in/company/{candidate}/",
            ):
                for attempt in range(retries):
                    try:
                        resp = session.get(url, timeout=20)
                        if resp.status_code == 200 and resp.content:
                            result = parse_profit_and_loss(resp.text)
                            if _has_usable_data(result):
                                return result
                            break  # page loaded fine, just no usable data -- try next URL/candidate
                    except Exception:
                        pass
                    time.sleep(pause * (attempt + 1))
        return None
    finally:
        if own_session:
            session.close()


def _candidate_slugs(symbol: str, session: requests.Session, use_search_fallback: bool):
    """Yields the direct symbol first, then (if enabled) the search-API-resolved slug, lazily --
    the search call only happens if the direct slug's fetch fails, keeping the common case
    (direct slug works) to a single request."""
    yield symbol
    if use_search_fallback:
        resolved = resolve_screener_slug(symbol, session=session)
        if resolved and resolved.upper() != symbol.upper():
            yield resolved
