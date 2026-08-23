"""
Tickertape daily-close fetch for the sectoral indices yfinance serves badly.

Verified live (2026-08-22/23): 7 of the 10 SECTORAL_INDEX_TICKERS (see constants.py --
TICKERTAPE_INDEX_SYMBOLS lists exactly which ones) have gone stale on yfinance -- both the
daily AND monthly endpoints stopped updating in mid-July, over a month before this was caught.
Tickertape's own (undocumented, reverse-engineered) chart API returns fresh, accurate data for
every one of them, matching NSE's own official daily archive exactly. Only used for those 7 --
the other 3 sectoral indices, Nifty 50, and the benchmark still get fresh data from yfinance and
are left alone (see modules/turtle/screener.py's _fetch_index_daily_close).

No official API/auth: this is the same style of endpoint community scrapers for this site use.
Kept isolated in its own module so it's the one place to fix if Tickertape ever changes shape.
"""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd
import requests

_BASE_URL = "https://api.tickertape.in/stocks/charts/{symbol}"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_index_daily_close(symbol: str, years: float = 2.0, timeout: int = 20) -> Optional[pd.Series]:
    """Daily close series for a Tickertape index symbol (e.g. ``".NIFTYAUTO"``), covering the
    last ``years`` years. Returns a float Series with a tz-naive, sorted-ascending DatetimeIndex
    -- same shape ``modules/turtle/screener.py`` already expects from a yfinance ``Close``
    column, so it drops into the same downstream code (relative_strength, ATH comparison, etc.)
    unchanged. Never raises; returns None on any network/parse failure or empty response.
    """
    now = int(time.time())
    start = now - int(years * 365 * 24 * 3600)
    try:
        resp = requests.get(
            _BASE_URL.format(symbol=symbol),
            params={"start": start * 1000, "end": now * 1000},
            headers=_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return None

    points = payload.get("data", {}).get(symbol, {}).get("points")
    if not points:
        return None

    try:
        dates = pd.to_datetime([p["ts"] for p in points]).tz_localize(None)
        closes = pd.to_numeric([p["lp"] for p in points], errors="coerce")
    except Exception:
        return None

    series = pd.Series(closes, index=dates).dropna()
    if series.empty:
        return None
    return series.sort_index()
