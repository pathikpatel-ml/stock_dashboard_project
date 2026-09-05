"""
Orchestration layer for the Turtle Quant screener.

Wires the pure functions in ``compute.py`` to real data:
  * Weekly OHLCV per stock via ``modules.breakout.data_feed.get_weekly`` (reused, not
    rewritten -- same cached yfinance wrapper the Turtle Strategy tab already uses for
    monthly/daily, just its weekly variant, previously unused anywhere in this app).
  * The comparative index (NSE:NIFTY, ``^NSEI``) via a direct yfinance call -- NOT through
    ``data_feed``, which always appends ``.NS`` and is NSE-equity-only. Mirrors
    ``modules/turtle/screener.py::_fetch_index_daily_close``'s approach, just weekly interval.
  * The pre-computed universe (Sector/Industry/Current_Price) from the same
    ``NSE_EQ_All_Stocks_Analysis.csv``-shaped frame the Turtle Strategy pipeline already uses --
    no separate universe download, no fundamental pre-filter (this is a purely technical screen).

``run_pipeline`` fetches the comparative index once, then iterates the universe.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from modules.breakout import data_feed
from . import compute
from . import constants as C

SIGNAL_COLUMNS = [
    "Symbol", "Company", "Sector", "Industry", "Current_Price",
    "RS_Long_Term", "RS_Short_Term", "ADX", "RSI",
    "SuperTrend_Direction", "Volume_Building", "Price_Above_MA13", "Signal",
]


def _fetch_index_weekly_close(ticker: str = C.COMPARATIVE_TICKER) -> Optional[pd.Series]:
    """Weekly close series for the comparative index. Returns None (never raises) on any
    fetch/parse failure -- callers decide what that means. ``^NSEI`` is not one of the tickers
    that went stale on yfinance this session (only sectoral indices were affected), so no
    Tickertape fallback is needed here.
    """
    try:
        hist = yf.Ticker(ticker).history(
            period=C.WEEKLY_HISTORY_PERIOD, interval="1wk", auto_adjust=False, timeout=20
        )
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None

    # Assign the index BEFORE dropna(), not after -- see modules/turtle/screener.py's
    # identical comment for the real bug this avoids (a length-mismatch ValueError when a raw
    # NaN close is present and the original, undropped index is reassigned onto a now-shorter
    # series).
    close = pd.to_numeric(hist["Close"], errors="coerce")
    close.index = pd.DatetimeIndex(hist.index).tz_localize(None)
    close = close.dropna()
    return close if not close.empty else None


def screen_symbol(
    symbol: str,
    company,
    sector,
    industry,
    index_weekly_close: pd.Series,
) -> Dict:
    """Fetch one symbol's weekly OHLCV and compute its full Turtle Quant signal row. Never
    raises -- returns a REJECT-style dict with a ``reason`` key if data is missing/insufficient,
    mirroring modules/turtle/screener.py::run_pipeline's per-symbol resilience.
    """
    try:
        weekly = data_feed.get_weekly(symbol, period=C.WEEKLY_HISTORY_PERIOD)
    except Exception as exc:  # network resilience -- never crash the batch
        return {"Symbol": symbol, "reason": f"fetch_error:{exc}"}

    if weekly is None or weekly.empty or "Close" not in weekly.columns:
        return {"Symbol": symbol, "reason": "no_weekly_data"}
    if len(weekly) < C.MIN_WEEKLY_ROWS:
        return {"Symbol": symbol, "reason": "insufficient_weekly_data"}

    high, low, close, volume = weekly["High"], weekly["Low"], weekly["Close"], weekly["Volume"]

    rs_long = compute.relative_strength_vs_index(close, index_weekly_close, C.RS_LONG_TERM_WEEKS)
    rs_short = compute.relative_strength_vs_index(close, index_weekly_close, C.RS_SHORT_TERM_WEEKS)
    adx_series = compute.adx(high, low, close, C.DMI_LENGTH)
    rsi_series = compute.rsi(close, C.RSI_LENGTH)
    supertrend_series = compute.supertrend(high, low, close, C.SUPERTREND_ATR_LENGTH, C.SUPERTREND_ATR_FACTOR)
    volume_ok = compute.volume_building(volume, C.MA_LENGTH)
    price_ok = compute.price_trend_ok(close, C.MA_LENGTH)

    adx_value = float(adx_series.iloc[-1]) if pd.notna(adx_series.iloc[-1]) else None
    rsi_value = float(rsi_series.iloc[-1]) if pd.notna(rsi_series.iloc[-1]) else None
    supertrend_bullish = bool(supertrend_series.iloc[-1] == 1)

    signal = compute.classify(rs_long, rs_short, adx_value, volume_ok, price_ok, rsi_value, supertrend_bullish)

    return {
        "Symbol": symbol,
        "Company": company,
        "Sector": sector,
        "Industry": industry,
        "Current_Price": float(close.iloc[-1]),
        "RS_Long_Term": round(rs_long, 4) if rs_long is not None else None,
        "RS_Short_Term": round(rs_short, 4) if rs_short is not None else None,
        "ADX": round(adx_value, 2) if adx_value is not None else None,
        "RSI": round(rsi_value, 2) if rsi_value is not None else None,
        "SuperTrend_Direction": "BULLISH" if supertrend_bullish else "BEARISH",
        "Volume_Building": volume_ok,
        "Price_Above_MA13": price_ok,
        "Signal": signal,
    }


def run_pipeline(
    universe_df: pd.DataFrame,
    limit: Optional[int] = None,
    verbose: bool = True,
    pause_seconds: float = 0.1,
) -> Dict[str, pd.DataFrame]:
    """Run the Turtle Quant screen over ``universe_df`` (NSE_EQ_All_Stocks_Analysis.csv shape).

    Returns {"signals": df, "rejections": df}. Fetches the comparative index once; raises
    RuntimeError if it can't be fetched at all (a run without a benchmark is meaningless -- same
    "stop, don't silently degrade" rule as modules/turtle/screener.py::fetch_benchmark_rs).

    ``pause_seconds`` (default 0.1) adds a light delay after each symbol's fetch -- cheap
    insurance against Yahoo Finance throttling across the full universe. Left at 0 for tests,
    which stub the fetch entirely and don't need pacing.
    """
    index_weekly_close = _fetch_index_weekly_close()
    if index_weekly_close is None:
        raise RuntimeError(
            f"Could not fetch comparative index ({C.COMPARATIVE_TICKER}) weekly close. "
            "Refusing to run without it -- every signal depends on it."
        )

    rows = universe_df.head(limit) if limit else universe_df

    signals: List[dict] = []
    rejects: List[dict] = []

    for i, (_, urow) in enumerate(rows.iterrows(), 1):
        symbol = str(urow.get("Symbol", "")).strip().upper()
        if not symbol:
            continue

        result = screen_symbol(
            symbol,
            urow.get("Company Name", symbol),
            urow.get("Sector"),
            urow.get("Industry"),
            index_weekly_close,
        )
        if pause_seconds:
            time.sleep(pause_seconds)

        if "reason" in result:
            rejects.append(result)
        else:
            signals.append(result)

        if verbose and i % 100 == 0:
            print(f"  turtlequant: fetched {i}/{len(rows)} symbols")

    signals_df = pd.DataFrame(signals).reindex(columns=SIGNAL_COLUMNS) if signals else pd.DataFrame(columns=SIGNAL_COLUMNS)
    return {"signals": signals_df, "rejections": pd.DataFrame(rejects)}
