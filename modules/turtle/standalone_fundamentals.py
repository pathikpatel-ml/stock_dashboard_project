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
from typing import List, Optional, Tuple

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
    text = text.strip().replace(",", "").rstrip("%").strip()  # ROCE%/Promoter% rows carry a
    # trailing "%" -- harmless no-op for every other (non-percent) value already parsed here.
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


def _find_section_table(soup: BeautifulSoup, section_title: str):
    """Generic version of ``_find_pl_table`` -- locates the ``<table>`` under any named
    ``<h2>`` section (Balance Sheet, Ratios, Cash Flows, ...), not just Profit & Loss."""
    heading = None
    for h in soup.find_all("h2"):
        if h.get_text(strip=True) == section_title:
            heading = h
            break
    if heading is None:
        return None
    section = heading.find_parent("section")
    return section.find("table") if section else None


def _extract_annual_series(table, row_labels) -> Optional[Tuple[List[str], List[float]]]:
    """Returns ``(periods, values)`` for the first row whose label (trailing '+' stripped)
    is in ``row_labels``, positionally aligned to the header's period columns. The TTM column
    (present on Profit & Loss but not Balance Sheet/Ratios/Cash Flows) is excluded -- it isn't
    a real annual period, and including it would corrupt a CAGR/average computed over "the
    last N years". Unparseable cells are dropped together with their matching period so the
    two lists never drift out of alignment. Returns None if the row isn't found at all (not
    the same as "found but empty" -- see quality_flags.py for how an empty-but-found row and a
    genuinely-missing row are both treated as "insufficient data", just via different paths).
    """
    rows = table.find_all("tr")
    if not rows:
        return None
    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    periods = header_cells[1:]  # header_cells[0] is the blank corner cell
    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if not cells:
            continue
        label = re.sub(r"\+$", "", cells[0]).strip()
        if label in row_labels:
            values_raw = cells[1:]
            out_periods, out_values = [], []
            for i, v in enumerate(values_raw):
                if i >= len(periods) or periods[i] == "TTM":
                    continue
                num = _to_number(v)
                if num is not None:
                    out_periods.append(periods[i])
                    out_values.append(num)
            return out_periods, out_values
    return None


def parse_balance_sheet_history(html: str) -> Optional[dict]:
    """Equity Capital + Reserves annual history (Cr) from screener.in's "Balance Sheet" table
    -- (Equity Capital + Reserves) is total book value; see quality_flags.py for the per-share
    derivation and 10-year CAGR. None if the section itself can't be found; a found section
    missing one of the two rows degrades to that key being None, not the whole dict."""
    soup = BeautifulSoup(html, "html.parser")
    table = _find_section_table(soup, "Balance Sheet")
    if table is None:
        return None
    return {
        "equity_capital": _extract_annual_series(table, {"Equity Capital"}),
        "reserves": _extract_annual_series(table, {"Reserves"}),
    }


def parse_cash_flow_history(html: str) -> Optional[dict]:
    """Cash from Operating Activity annual history (Cr) from screener.in's "Cash Flows" table
    -- feeds the Price-to-Cash-Flow valuation check. None if the section or row can't be found.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_section_table(soup, "Cash Flows")
    if table is None:
        return None
    cfo = _extract_annual_series(table, {"Cash from Operating Activity"})
    if cfo is None:
        return None
    return {"cfo": cfo}


def parse_pl_history_extra(html: str) -> Optional[dict]:
    """EPS / Interest / Profit-before-tax / Sales annual history from the SAME Profit & Loss
    table ``parse_profit_and_loss`` already reads -- a separate function (not merged into that
    one, which has its own established contract/tests for ATH_Profit_Flag/ATH_Sales_Flag) since
    these feed the NEW quality-flags computation (EPS/Sales growth CAGR, interest coverage, and
    -- via Net Profit/EPS -- derived shares outstanding for the valuation-ratio checks). ``sales``
    is period-aligned (unlike ``parse_profit_and_loss``'s plain-list ``annual_net_sales``)
    specifically so it can be safely zipped with ``eps``'s periods for per-share/valuation-ratio
    computation -- pairing two INDEPENDENTLY-filtered plain lists by position would silently
    misalign if either row had an occasional missing/unparseable cell. None if the Profit & Loss
    section itself can't be found; a found table missing one of the four rows degrades to that
    key being None.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_pl_table(soup)
    if table is None:
        return None
    return {
        "eps": _extract_annual_series(table, {"EPS in Rs"}),
        "interest": _extract_annual_series(table, {"Interest"}),
        "profit_before_tax": _extract_annual_series(table, {"Profit before tax"}),
        "sales": _extract_annual_series(table, _SALES_ROW_LABELS),
        "net_profit": _extract_annual_series(table, _PROFIT_ROW_LABELS),
        # 2026-10-02: Quality of Turnover red-flag check (Other Income / Total Revenue).
        "other_income": _extract_annual_series(table, {"Other Income"}),
    }


def parse_promoter_holding_history(html: str) -> Optional[dict]:
    """Promoter holding % history from screener.in's "Shareholding Pattern" table -- QUARTERLY
    columns, and only ~3 years of them (12 quarters), confirmed live 2026-10-01 -- screener.in's
    free tier does not expose a real 10-year promoter-holding series. The "Promoters" label
    cell is a JS button (``<button>Promoters&nbsp;<span>+</span></button>``), not plain text --
    ``_extract_annual_series``'s ``get_text(strip=True)`` already concatenates that into
    "Promoters+", which the existing trailing-'+' strip handles the same as every other row.
    None if the section or row can't be found.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = _find_section_table(soup, "Shareholding Pattern")
    if table is None:
        return None
    promoters = _extract_annual_series(table, {"Promoters"})
    if promoters is None:
        return None
    return {"promoter_pct": promoters}


_SECTOR_TAG_TITLES = (
    ("broad_sector", "Broad Sector"),
    ("sector", "Sector"),
    ("broad_industry", "Broad Industry"),
    ("industry", "Industry"),
)


def parse_sector_classification(html: str) -> Optional[dict]:
    """Extract screener.in's own 4-tier sector/industry classification (Broad Sector -> Sector
    -> Broad Industry -> Industry -- e.g. Energy -> Oil, Gas & Consumable Fuels -> Petroleum
    Products -> Refineries & Marketing for RELIANCE, verified live 2026-09) from a company
    page's "Peer comparison" block: ``<a title="Broad Sector">Energy</a>`` etc, right next to
    each other. This is a company-attribute lookup, unrelated to the Profit & Loss financials
    table elsewhere on the same page -- present (or absent) independent of whether the company
    has any usable consolidated/standalone P&L data. Returns None only if NONE of the four tags
    are found (e.g. a symbol with no real screener.in listing); a page with some but not all
    four tags present returns a dict with the missing ones as None, never raises.
    """
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for key, title in _SECTOR_TAG_TITLES:
        tag = soup.find("a", title=title)
        result[key] = tag.get_text(strip=True) if tag else None
    if not any(result.values()):
        return None
    return result


_BSE_CODE_RE = re.compile(r"BSE:\s*(\d{5,6})")


def parse_bse_code(html: str) -> Optional[str]:
    """Extract the company's BSE scrip code (e.g. "500325" for RELIANCE) from the "BSE: XXXXXX"
    link in the page header -- present on the same already-fetched page used for every other
    quality-flag field, zero extra network cost. 2026-10-02: needed to join this symbol against
    screener.in's own SCREENING query results (modules/turtle/screener_in_login.py), which link
    each row by BSE code, not NSE symbol. None if not found (not every company has this tag
    rendered, or the page has no usable data at all)."""
    m = _BSE_CODE_RE.search(html)
    return m.group(1) if m else None


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

    Also extracts screener.in's own sector/industry classification (``broad_sector``,
    ``sector``, ``broad_industry``, ``industry`` -- see ``parse_sector_classification``) from
    whichever page response ends up used, at zero extra network cost: it's the same "Peer
    comparison" block rendered on every company page regardless of financial-data usability.
    Keeps the first classification found across candidates/URLs as a fallback in case the page
    that finally has usable P&L data doesn't itself carry the tags (or the reverse -- no usable
    P&L found anywhere, but a sector classification was) so this function still returns
    something useful for the sector-only case rather than None.

    2026-10-01: ALSO extracts the Balance Sheet/Cash Flows/extra P&L rows/Shareholding
    Pattern history needed for the Turtle Quant quality flags (``balance_sheet``,
    ``cash_flow``, ``pl_extra``, ``promoter_holding`` keys -- see the matching
    ``parse_*_history`` functions above) from the SAME usable-P&L page, again at zero extra
    network cost. Unlike sector classification, these are only attempted on the page that
    actually has usable P&L data (not accumulated as a fallback across every candidate/URL
    tried) -- the no-usable-P&L-anywhere case is rare enough that this extra complexity wasn't
    worth it; that case's quality-related keys are simply absent from the returned dict.
    """
    own_session = session is None
    session = session or _new_session()
    best_sector = None
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
                            sector = parse_sector_classification(resp.text)
                            if sector and best_sector is None:
                                best_sector = sector
                            if _has_usable_data(result):
                                result.update(sector or best_sector or {})
                                result["balance_sheet"] = parse_balance_sheet_history(resp.text)
                                result["cash_flow"] = parse_cash_flow_history(resp.text)
                                result["pl_extra"] = parse_pl_history_extra(resp.text)
                                result["promoter_holding"] = parse_promoter_holding_history(resp.text)
                                result["bse_code"] = parse_bse_code(resp.text)
                                return result
                            break  # page loaded fine, just no usable data -- try next URL/candidate
                    except Exception:
                        pass
                    time.sleep(pause * (attempt + 1))
        if best_sector:
            return {
                "ttm_net_profit": None, "annual_net_profit": [],
                "ttm_net_sales": None, "annual_net_sales": [],
                **best_sector,
            }
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
