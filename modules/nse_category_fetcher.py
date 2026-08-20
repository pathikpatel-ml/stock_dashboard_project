"""
NSE index-membership fetcher — populates ``nse_categories.csv`` (Symbol, NSE_Categories).

NSE publishes each index's constituent list as a small CSV under its index archive
(``archives.nseindia.com/content/indices/ind_nifty{50,100,200}list.csv``), same domain
already used for the full equity list in ``modules/stock_screener.get_nse_stock_list``.

Download uses a browser-like session + retry pattern (NSE's archive endpoints reject bare,
header-less requests). Parsing/merging/writing are pure functions, unit-tested without
touching the network.
"""
from __future__ import annotations

import io
import time
from typing import Dict, Iterable, List, Optional

import pandas as pd
import requests

INDEX_URLS = {
    "NIFTY 50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "NIFTY 100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "NIFTY 200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    # Sectoral + market-cap-tier indices (added 2026-08-20) -- each URL individually verified
    # live before adding (NSE's archive doesn't follow one predictable slug-from-name rule;
    # about 16 other guessed names 404'd and were dropped rather than included unverified --
    # see docs/TURTLE_STRATEGY_PLAN.md for the full list of names still unresolved).
    "NIFTY AUTO": "https://archives.nseindia.com/content/indices/ind_niftyautolist.csv",
    "NIFTY BANK": "https://archives.nseindia.com/content/indices/ind_niftybanklist.csv",
    "NIFTY ENERGY": "https://archives.nseindia.com/content/indices/ind_niftyenergylist.csv",
    "NIFTY FMCG": "https://archives.nseindia.com/content/indices/ind_niftyfmcglist.csv",
    "NIFTY IT": "https://archives.nseindia.com/content/indices/ind_niftyitlist.csv",
    "NIFTY METAL": "https://archives.nseindia.com/content/indices/ind_niftymetallist.csv",
    "NIFTY PHARMA": "https://archives.nseindia.com/content/indices/ind_niftypharmalist.csv",
    "NIFTY REALTY": "https://archives.nseindia.com/content/indices/ind_niftyrealtylist.csv",
    "NIFTY MIDCAP 50": "https://archives.nseindia.com/content/indices/ind_niftymidcap50list.csv",
    "NIFTY SMALLCAP 50": "https://archives.nseindia.com/content/indices/ind_niftysmallcap50list.csv",
    "NIFTY CONSUMER DURABLES": "https://archives.nseindia.com/content/indices/ind_niftyconsumerdurableslist.csv",
    "NIFTY MEDIA": "https://archives.nseindia.com/content/indices/ind_niftymedialist.csv",
    "NIFTY OIL AND GAS": "https://archives.nseindia.com/content/indices/ind_niftyoilgaslist.csv",
    "NIFTY PSU BANK": "https://archives.nseindia.com/content/indices/ind_niftypsubanklist.csv",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _new_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=15)
    except Exception:
        pass  # cookie warm-up is best-effort
    return session


def fetch_index_constituents(
    index_name: str,
    session: Optional[requests.Session] = None,
    retries: int = 3,
    pause: float = 1.5,
) -> Optional[List[str]]:
    """Fetch the constituent Symbol list for ``index_name`` (a key of ``INDEX_URLS``).

    Returns None if the index is unknown or every attempt fails — callers must treat
    None as "could not refresh this index" and keep whatever data they already have,
    never as "this index is empty".
    """
    url = INDEX_URLS.get(index_name)
    if not url:
        return None

    own_session = session is None
    session = session or _new_session()
    try:
        for attempt in range(retries):
            try:
                resp = session.get(url, timeout=30)
                if resp.status_code == 200 and resp.content and b"Symbol" in resp.content[:200]:
                    df = pd.read_csv(io.StringIO(resp.content.decode("utf-8", "ignore")))
                    df.columns = [str(c).strip() for c in df.columns]
                    if "Symbol" not in df.columns:
                        continue
                    symbols = (
                        df["Symbol"].dropna().astype(str).str.strip().str.upper().unique().tolist()
                    )
                    if symbols:
                        return sorted(symbols)
            except Exception:
                pass
            time.sleep(pause * (attempt + 1))
        return None
    finally:
        if own_session:
            session.close()


def build_categories_map(index_symbol_lists: Dict[str, Iterable[str]]) -> Dict[str, List[str]]:
    """Invert ``{index_name: [symbols]}`` into ``{symbol: [index_names]}`` (sorted, deduped)."""
    categories_map: Dict[str, List[str]] = {}
    for index_name, symbols in index_symbol_lists.items():
        for symbol in symbols:
            symbol = str(symbol).strip().upper()
            if not symbol:
                continue
            tags = categories_map.setdefault(symbol, [])
            if index_name not in tags:
                tags.append(index_name)
    return {symbol: sorted(tags) for symbol, tags in categories_map.items()}


def merge_categories_maps(
    existing_map: Dict[str, List[str]],
    new_map: Dict[str, List[str]],
    replace_tags: Iterable[str] = ("NIFTY 50", "NIFTY 100", "NIFTY 200"),
) -> Dict[str, List[str]]:
    """Merge ``new_map`` into ``existing_map`` without discarding unrelated tags.

    Any tag exactly matching one in ``replace_tags`` is dropped from every symbol before
    merging in the freshly fetched membership, so a stock that fell out of Nifty 100/200
    loses the stale tag instead of keeping it forever. Tags not in ``replace_tags``
    (e.g. thematic indices already in ``nse_categories.csv`` like "NIFTY PHARMA")
    are always preserved.
    """
    merged: Dict[str, List[str]] = {}
    for symbol, tags in existing_map.items():
        kept = [t for t in tags if t not in replace_tags]
        if kept:
            merged[symbol] = kept

    for symbol, tags in new_map.items():
        combined = set(merged.get(symbol, [])) | set(tags)
        merged[symbol] = sorted(combined)

    return {symbol: tags for symbol, tags in merged.items() if tags}


def load_categories_map_from_csv(path: str) -> Dict[str, List[str]]:
    """Read an existing ``nse_categories.csv`` into ``{symbol: [tags]}``. Missing file -> {}."""
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    if "Symbol" not in df.columns or "NSE_Categories" not in df.columns:
        return {}

    result: Dict[str, List[str]] = {}
    for _, row in df.iterrows():
        symbol = str(row["Symbol"]).strip().upper()
        raw = row["NSE_Categories"]
        if not symbol or pd.isna(raw):
            continue
        tags = [t.strip() for t in str(raw).split(",") if t.strip()]
        if tags:
            result[symbol] = tags
    return result


def save_nse_categories_to_csv(categories_map: Dict[str, List[str]], output_path: str) -> None:
    """Write ``{symbol: [tags]}`` to ``output_path`` as ``Symbol,NSE_Categories`` (sorted by symbol)."""
    rows = [
        {"Symbol": symbol, "NSE_Categories": ",".join(tags)}
        for symbol, tags in sorted(categories_map.items())
        if tags
    ]
    pd.DataFrame(rows, columns=["Symbol", "NSE_Categories"]).to_csv(output_path, index=False)


def refresh_nifty_membership(output_path: str, index_names: Iterable[str] = tuple(INDEX_URLS)) -> bool:
    """Fetch the given indices and merge them into ``output_path``. Returns True iff at least
    one index was successfully refreshed (the file is still written/merged in that case);
    returns False (and leaves the existing file untouched) if every fetch failed.
    """
    session = _new_session()
    try:
        fetched = {}
        for index_name in index_names:
            symbols = fetch_index_constituents(index_name, session=session)
            if symbols:
                fetched[index_name] = symbols
    finally:
        session.close()

    if not fetched:
        return False

    existing_map = load_categories_map_from_csv(output_path)
    new_map = build_categories_map(fetched)
    # replace_tags = every index actually attempted this run (not just the original Nifty
    # 50/100/200 default) -- now that this fetcher covers 14 sectoral/size indices too, their
    # membership needs the same "drop the stale tag if the stock fell out" treatment on every
    # refresh, or a symbol that leaves e.g. NIFTY MEDIA would keep that tag forever. Only
    # indices that were actually fetched THIS run (in `fetched`, not all of `index_names` --
    # some may have failed) get replaced, so a transient fetch failure for one index doesn't
    # wipe its existing membership.
    merged_map = merge_categories_maps(existing_map, new_map, replace_tags=set(fetched))
    save_nse_categories_to_csv(merged_map, output_path)
    return True
