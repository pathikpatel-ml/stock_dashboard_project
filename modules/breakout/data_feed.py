"""
OHLCV data feed for the Multi-Year Breakout strategy.

Thin wrappers over yfinance providing the three timeframes the strategy needs (doc §10.1):
  * monthly  (10+ years)  — multi-year resistance detection, breakout candle analysis
  * weekly   (5+ years)   — 21-EMA trailing stop
  * daily    (1 year)     — SL monitoring on a daily-close basis

Mirrors the existing fetch style in ``modules/v20_callbacks._fetch_price_history_for_backtesting``
(``.NS`` suffix, ``auto_adjust=False``, tz-naive normalised index). Includes a small in-memory
cache so a single screening pass re-uses each symbol's frames.
"""
from __future__ import annotations

import threading
from typing import Optional

import pandas as pd
import yfinance as yf

from . import constants as C

_OHLCV = ["Open", "High", "Low", "Close", "Volume"]

# Per-process cache: {(symbol, interval, period): DataFrame}
_cache: dict = {}

# 2026-10-02: a hard ceiling on top of yfinance's own ``timeout=`` parameter. Confirmed live in
# a real production batch run that a small number of symbols (observed: GICHSGFIN, MOHITIND,
# PACEDIGITK) can make the underlying curl_cffi transport hang for 30-50 MINUTES before finally
# raising a "curl: (16)" HTTP/2 framing error -- ``timeout=20`` only bounds a single HTTP
# attempt, not whatever retry/backoff yfinance does internally around it. A handful of these
# hangs blew a full-universe batch job's budget from its usual ~70-90 min past a 4-hour workflow
# timeout, THREE times in one day, before being root-caused. Mirrors the exact pattern already
# established in data_manager.py for the V20 Render SIGSEGV fix: run the risky native-networking
# call in a background daemon thread and give up waiting after a short, fixed ceiling -- an
# abandoned thread may keep running, but it can never again block the calling code for more than
# this many seconds. A genuinely slow-but-working fetch is rare at this length (typical real
# fetches take 1-3s); this trades a very occasional false "unavailable" for immunity from an
# indefinite hang, which is the right tradeoff for an already-None-safe pipeline.
_HARD_TIMEOUT_SECONDS = 30


def _normalise(hist: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if hist is None or hist.empty:
        return None
    hist = hist.copy()
    hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
    cols = [c for c in _OHLCV if c in hist.columns]
    hist = hist[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["Close"])
    return hist if not hist.empty else None


def _fetch_raw(symbol: str, interval: str, period: str) -> Optional[pd.DataFrame]:
    """The actual yfinance call, run on a background thread by ``_fetch`` below -- never called
    directly so every caller gets the hard-timeout protection."""
    result_holder: dict = {}

    def _do_fetch():
        try:
            result_holder["hist"] = yf.Ticker(f"{symbol}.NS").history(
                period=period, interval=interval, auto_adjust=False, timeout=20
            )
        except Exception:
            result_holder["hist"] = None

    thread = threading.Thread(target=_do_fetch, daemon=True)
    thread.start()
    thread.join(timeout=_HARD_TIMEOUT_SECONDS)
    if thread.is_alive():
        return None  # still running -- abandon it (daemon thread), move on with no data for now
    return result_holder.get("hist")


def _fetch(symbol: str, interval: str, period: str, use_cache: bool) -> Optional[pd.DataFrame]:
    key = (symbol.upper(), interval, period)
    if use_cache and key in _cache:
        return _cache[key]
    hist = _fetch_raw(symbol, interval, period)
    result = _normalise(hist)
    if use_cache:
        _cache[key] = result
    return result


def get_monthly(symbol: str, period: str = C.MONTHLY_HISTORY_PERIOD, use_cache: bool = True):
    """10+ years of monthly OHLCV. Index = month-end timestamps."""
    return _fetch(symbol, "1mo", period, use_cache)


def get_weekly(symbol: str, period: str = C.WEEKLY_HISTORY_PERIOD, use_cache: bool = True):
    """5+ years of weekly OHLCV (for the 21-EMA weekly trailing stop)."""
    return _fetch(symbol, "1wk", period, use_cache)


def get_daily(symbol: str, period: str = C.DAILY_HISTORY_PERIOD, use_cache: bool = True):
    """1 year of daily OHLCV (for daily-close SL monitoring)."""
    return _fetch(symbol, "1d", period, use_cache)


def clear_cache() -> None:
    _cache.clear()
