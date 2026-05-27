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

from typing import Optional

import pandas as pd
import yfinance as yf

from . import constants as C

_OHLCV = ["Open", "High", "Low", "Close", "Volume"]

# Per-process cache: {(symbol, interval, period): DataFrame}
_cache: dict = {}


def _normalise(hist: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if hist is None or hist.empty:
        return None
    hist = hist.copy()
    hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
    cols = [c for c in _OHLCV if c in hist.columns]
    hist = hist[cols].apply(pd.to_numeric, errors="coerce").dropna(subset=["Close"])
    return hist if not hist.empty else None


def _fetch(symbol: str, interval: str, period: str, use_cache: bool) -> Optional[pd.DataFrame]:
    key = (symbol.upper(), interval, period)
    if use_cache and key in _cache:
        return _cache[key]
    try:
        hist = yf.Ticker(f"{symbol}.NS").history(
            period=period, interval=interval, auto_adjust=False, timeout=20
        )
    except Exception:
        hist = None
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
