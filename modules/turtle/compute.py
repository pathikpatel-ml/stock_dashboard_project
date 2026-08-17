"""
Pure, injected-data functions for the Turtle Strategy classifier (docs/TURTLE_STRATEGY_PLAN.md).

Every function here takes plain values / pandas Series it's handed — no file I/O, no yfinance
calls, no global state — so each is directly unit-testable with synthetic data. ``screener.py``
is the orchestration layer that fetches real data and calls these.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from . import constants as C


def ath_price_flag(
    current_price: Optional[float],
    historical_max_close: Optional[float],
    threshold_pct: float = C.ATH_PRICE_THRESHOLD_PCT,
) -> bool:
    """True if ``current_price`` is at or within ``threshold_pct`` of ``historical_max_close``."""
    if current_price is None or historical_max_close is None:
        return False
    if pd.isna(current_price) or pd.isna(historical_max_close) or historical_max_close <= 0:
        return False
    return current_price >= historical_max_close * (1.0 - threshold_pct / 100.0)


def _ttm_ath_flag(ttm_value: Optional[float], historical_max_annual: Optional[float]) -> bool:
    """Shared shape for both ATH-Profit and ATH-Sales: True if a TTM figure is at/above the
    max of every annual figure on record (including the latest year -- a TTM window is always
    a different, more current period than any single fiscal year, so there's no trivial
    self-match risk in comparing against the full set).

    Both ``ttm_value`` and ``historical_max_annual`` must come from the SAME table (screener.in's
    standalone Profit & Loss page) so they're already same-units, same-basis -- no EPS/shares
    conversion needed the way the old ATH-Profit implementation required (see git history: that
    approach mixed a consolidated yfinance TTM figure against a standalone historical EPS
    series, which needed a shares-outstanding derivation to even compare; screener.in's own TTM
    + annual columns sidestep that mismatch entirely).
    """
    if ttm_value is None or historical_max_annual is None:
        return False
    if pd.isna(ttm_value) or pd.isna(historical_max_annual):
        return False
    return ttm_value >= historical_max_annual


def ath_profit_flag(
    ttm_net_profit: Optional[float],
    historical_max_annual_profit: Optional[float],
) -> bool:
    """True if standalone TTM Net Profit (Cr, screener.in) is at/above the max annual Net
    Profit on record (also screener.in, same table, same units -- see ``_ttm_ath_flag``)."""
    return _ttm_ath_flag(ttm_net_profit, historical_max_annual_profit)


def ath_sales_flag(
    ttm_net_sales: Optional[float],
    historical_max_annual_sales: Optional[float],
) -> bool:
    """True if standalone TTM Net Sales (Cr, screener.in) is at/above the max annual Net
    Sales on record (also screener.in, same table, same units -- see ``_ttm_ath_flag``)."""
    return _ttm_ath_flag(ttm_net_sales, historical_max_annual_sales)


def above_exit_flag(current_price: Optional[float], exit_ma: Optional[float]) -> bool:
    """True if Current_Price is above the exit-price proxy moving average
    (``constants.EXIT_MA_PERIOD``-day SMA; CSV MA200 used only as an emergency fallback)."""
    if current_price is None or exit_ma is None:
        return False
    if pd.isna(current_price) or pd.isna(exit_ma):
        return False
    return current_price > exit_ma


def relative_strength(
    close_series: Optional[pd.Series],
    window_weeks: int = C.RS_WINDOW_WEEKS,
) -> Optional[float]:
    """52-week (``window_weeks``) % return, using each week's HIGHEST daily close as that
    week's representative value -- NOT the last trading day of the week.

    ``close_series`` must have a DatetimeIndex sorted ascending. Daily closes are bucketed
    into Mon-Sun weeks (labelled by each week's Monday); each week's value is
    ``max(that week's daily closes)``. The result compares the latest available week's high
    to the week exactly ``window_weeks`` weeks before it -- falling back to the closest
    available week on/before that target if the exact week is missing (holidays, gaps).
    Returns None if the series is empty, undated, or doesn't reach far enough back.
    """
    if close_series is None or len(close_series) == 0:
        return None
    if not isinstance(close_series.index, pd.DatetimeIndex):
        return None

    series = close_series.dropna()
    if series.empty:
        return None

    week_start = pd.DatetimeIndex(series.index) - pd.to_timedelta(
        pd.DatetimeIndex(series.index).weekday, unit="D"
    )
    weekly_high = pd.Series(series.values, index=week_start).groupby(level=0).max().sort_index()
    if weekly_high.empty:
        return None

    latest_week = weekly_high.index[-1]
    latest_high = float(weekly_high.iloc[-1])
    base_week_target = latest_week - pd.Timedelta(weeks=window_weeks)

    eligible = weekly_high[weekly_high.index <= base_week_target]
    if eligible.empty:
        return None

    base_high = float(eligible.iloc[-1])
    if base_high == 0:
        return None

    return (latest_high / base_high - 1.0) * 100.0


def outperformance_flag(
    stock_rs: Optional[float],
    sector_rs: Optional[float],
    benchmark_rs: Optional[float],
) -> bool:
    """True if the stock's relative strength beats BOTH its sector basket and the benchmark."""
    values = [stock_rs, sector_rs, benchmark_rs]
    if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in values):
        return False
    return stock_rs > sector_rs and stock_rs > benchmark_rs


def classify(ath_price: bool, ath_profit: bool, above_exit: bool, outperformance: bool) -> str:
    """3-box classifier (plan §1, implemented exactly):

    ADD  — meets ALL 3: ATH Price + ATH Profit + Outperformance.
    HOLD — meets ANY 2 of: ATH Profit, Above Exit Price (MA212 proxy), Outperformance.
           (ATH Price is deliberately NOT part of this 2-of-3 set.)
    EXIT — meets NONE or ANY 1 of the HOLD set.
    """
    if ath_price and ath_profit and outperformance:
        return "ADD"
    if sum([ath_profit, above_exit, outperformance]) >= 2:
        return "HOLD"
    return "EXIT"


def sectoral_index_tag(categories_str: Optional[str]) -> Optional[str]:
    """Returns the NSE sectoral index tag (e.g. ``"NIFTY PHARMA"``) a stock belongs to, for
    use as its RS peer-group basket -- or None if it isn't in any sectoral index (only in the
    broad Nifty 50/100/200, or no index membership at all), in which case the caller should
    fall back to the broad ``Sector`` column instead.

    ``C.BROAD_INDEX_TAGS`` (Nifty 50/100/200) are market-cap groupings, not sector groupings,
    so they're excluded -- anything else in the comma-joined ``categories_str`` counts as
    sectoral. If a stock somehow has more than one sectoral tag (not expected in practice),
    the alphabetically-first one is used, for determinism.
    """
    if categories_str is None or (isinstance(categories_str, float) and pd.isna(categories_str)):
        return None
    tags = {t.strip().upper() for t in str(categories_str).split(",") if t.strip()}
    sectoral = sorted(tags - C.BROAD_INDEX_TAGS)
    return sectoral[0] if sectoral else None


def filter_by_index(categories_str: Optional[str], index_name: str) -> bool:
    """Membership test against a comma-joined ``NSE_Categories`` string (e.g. "NIFTY 50,NIFTY METAL").

    ``index_name == "All"`` always matches. Nifty 50 membership implies Nifty 100 and Nifty
    200 membership (NSE's indices nest), so "NIFTY 100" also matches a "NIFTY 50"-tagged row
    and "NIFTY 200" matches either.
    """
    if index_name == "All":
        return True
    if categories_str is None or (isinstance(categories_str, float) and pd.isna(categories_str)):
        return False

    tags = {t.strip().upper() for t in str(categories_str).split(",") if t.strip()}
    index_name = index_name.upper()

    if index_name == "NIFTY 50":
        return "NIFTY 50" in tags
    if index_name == "NIFTY 100":
        return bool(tags & {"NIFTY 50", "NIFTY 100"})
    if index_name == "NIFTY 200":
        return bool(tags & {"NIFTY 50", "NIFTY 100", "NIFTY 200"})
    return index_name in tags


def merge_live_prices(signals_df: pd.DataFrame, live_prices_df: pd.DataFrame) -> pd.DataFrame:
    """Overlay a fresher intraday price (from generate_turtle_live_prices.py's cache) onto
    the daily batch's ``Current_Price`` column.

    Only the displayed price is refreshed here -- ATH_Price_Flag, Above_MA212_Flag,
    RS_vs_Sector/Benchmark, Outperformance_Flag, and Signal all stay exactly as the daily
    batch computed them (they depend on 52-week trends that don't meaningfully change
    between intraday refreshes; recomputing them would require the full per-symbol pipeline
    this cache exists to avoid). A symbol missing from ``live_prices_df``, or with a NaN
    ``Live_Price``, keeps whatever price the daily batch already produced.
    """
    if signals_df is None or signals_df.empty:
        return signals_df
    if live_prices_df is None or live_prices_df.empty or "Symbol" not in live_prices_df.columns:
        return signals_df

    price_map = dict(zip(
        live_prices_df["Symbol"].astype(str).str.upper(),
        pd.to_numeric(live_prices_df["Live_Price"], errors="coerce"),
    ))

    df = signals_df.copy()
    live_values = df["Symbol"].astype(str).str.upper().map(price_map)
    df["Current_Price"] = live_values.where(live_values.notna(), df["Current_Price"])
    return df
