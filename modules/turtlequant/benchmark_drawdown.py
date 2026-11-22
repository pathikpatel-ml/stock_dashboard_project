"""
Pure compute functions for Turtle Quant's Nifty-50-anchored drawdown comparison (2026-11-22,
per explicit user request).

The idea: instead of a rolling 52-week window (what modules.turtle.compute.relative_strength
already does), anchor BOTH Nifty 50 and every stock to the exact same three calendar dates --
Nifty 50's own all-time-high date, its 52-week-low date, and today -- and compare how far each
has moved between them. If Nifty is down 30% from its ATH today but a stock is only down 20%
from ITS OWN price on that same ATH date, the stock has outperformed Nifty since that peak.

Convention (confirmed live against real Nifty 50 data, 2026-11-22): "all-time high"/"52-week
low" use the index's intraday HIGH/LOW respectively, not the closing price -- e.g. Nifty 50's
real ATH was 26,373.20 (High) on 2026-01-05, one trading day AFTER its highest CLOSE
(26,328.55 on 2026-01-02). "Today" uses the latest closing price, and every stock's own price
on each reference date is likewise its CLOSING price on (or, if that exact date is a holiday/
gap for that symbol, the nearest trading day before) that date.

No network I/O here -- modules/turtlequant/screener.py does the actual yfinance/data_feed
fetching and calls into this module with plain price series/dicts.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

# The 4 fields generate_turtlequant_benchmark_drawdown.py persists per stock (into
# turtlequant_signals_latest) -- the other 2 of the user's 6 requested output columns
# (Nifty's own ATH/52wk-low return to today) are the SAME value for every stock, so they're
# broadcast from the single turtlequant_nifty_benchmark row at render time instead of being
# stored redundantly ~2,600 times.
DRAWDOWN_FIELDS = [
    "stock_ath_return_pct", "stock_52wklow_return_pct", "rs_vs_nifty_ath", "rs_vs_nifty_52wklow",
]


def pct_return(start_price: Optional[float], end_price: Optional[float]) -> Optional[float]:
    """((end / start) - 1) * 100 -- None for any missing/NaN/zero-start input, never raises."""
    if start_price is None or end_price is None:
        return None
    if isinstance(start_price, float) and pd.isna(start_price):
        return None
    if isinstance(end_price, float) and pd.isna(end_price):
        return None
    if start_price == 0:
        return None
    return (end_price / start_price - 1.0) * 100.0


def nifty_reference_from_ohlc(ohlc: pd.DataFrame, window_weeks: int = 52) -> Optional[Dict]:
    """Derive Nifty 50's reference dict from its full daily OHLC history (DatetimeIndex,
    ``High``/``Low``/``Close`` columns -- a plain yfinance ``.history()`` frame).

    - ``ath_price``/``ath_date``: the highest ``High`` over the WHOLE given series (as close to
      a genuine all-time-high as the available history allows -- same pragmatic "longest
      history we can get" approach already used elsewhere in this codebase for index ATHs).
    - ``low_52wk_price``/``low_52wk_date``: the lowest ``Low`` over the trailing
      ``window_weeks`` weeks from the series' last date.
    - ``today_price``/``today_date``: the latest ``Close`` and its date.

    Returns None (never raises) if the input is empty or missing a required column.
    """
    if ohlc is None or ohlc.empty:
        return None
    if not {"High", "Low", "Close"}.issubset(ohlc.columns):
        return None

    frame = ohlc.dropna(subset=["High", "Low", "Close"])
    if frame.empty:
        return None

    ath_idx = frame["High"].idxmax()
    today_idx = frame.index[-1]

    window_start = today_idx - pd.Timedelta(weeks=window_weeks)
    trailing = frame[frame.index >= window_start]
    if trailing.empty:
        trailing = frame
    low_idx = trailing["Low"].idxmin()

    return {
        "ath_price": float(frame["High"].loc[ath_idx]),
        "ath_date": pd.Timestamp(ath_idx).date(),
        "low_52wk_price": float(trailing["Low"].loc[low_idx]),
        "low_52wk_date": pd.Timestamp(low_idx).date(),
        "today_price": float(frame["Close"].iloc[-1]),
        "today_date": pd.Timestamp(today_idx).date(),
    }


def price_on_or_before(close_series: Optional[pd.Series], target_date) -> Optional[float]:
    """The closing price on ``target_date``, or the nearest trading day BEFORE it if that exact
    date has no row (holiday, or the series doesn't cover it) -- e.g. a stock-specific holiday
    Nifty itself traded through. None (never raises) if there's no data at or before
    ``target_date`` at all (the series doesn't reach back that far -- e.g. a stock listed after
    Nifty's reference date)."""
    if close_series is None or len(close_series) == 0:
        return None
    series = close_series.dropna()
    if series.empty:
        return None
    target = pd.Timestamp(target_date)
    eligible = series[pd.DatetimeIndex(series.index) <= target]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1])


def compute_stock_drawdown(stock_close: Optional[pd.Series], nifty_ref: Optional[Dict]) -> Dict:
    """The 4 per-stock fields (see ``DRAWDOWN_FIELDS``): the stock's own return from its price
    on Nifty's ATH/52-week-low date to today, and how that compares to Nifty's own return over
    the same span (stock's return minus Nifty's -- positive means the stock outperformed Nifty
    since that reference point, same percentage-point-delta convention as RS_vs_Sector/
    RS_vs_Benchmark elsewhere in this app). Every field is None (never raises) if ``nifty_ref``
    is unavailable or the stock's own price history doesn't reach back to a given reference
    date (e.g. a recently-listed stock)."""
    empty = {field: None for field in DRAWDOWN_FIELDS}
    if nifty_ref is None:
        return empty

    price_on_ath_date = price_on_or_before(stock_close, nifty_ref["ath_date"])
    price_on_low_date = price_on_or_before(stock_close, nifty_ref["low_52wk_date"])
    price_today = price_on_or_before(stock_close, nifty_ref["today_date"])

    stock_ath_return = pct_return(price_on_ath_date, price_today)
    stock_low_return = pct_return(price_on_low_date, price_today)
    nifty_ath_return = pct_return(nifty_ref["ath_price"], nifty_ref["today_price"])
    nifty_low_return = pct_return(nifty_ref["low_52wk_price"], nifty_ref["today_price"])

    rs_vs_ath = (
        stock_ath_return - nifty_ath_return
        if stock_ath_return is not None and nifty_ath_return is not None else None
    )
    rs_vs_low = (
        stock_low_return - nifty_low_return
        if stock_low_return is not None and nifty_low_return is not None else None
    )

    return {
        "stock_ath_return_pct": round(stock_ath_return, 2) if stock_ath_return is not None else None,
        "stock_52wklow_return_pct": round(stock_low_return, 2) if stock_low_return is not None else None,
        "rs_vs_nifty_ath": round(rs_vs_ath, 2) if rs_vs_ath is not None else None,
        "rs_vs_nifty_52wklow": round(rs_vs_low, 2) if rs_vs_low is not None else None,
    }
