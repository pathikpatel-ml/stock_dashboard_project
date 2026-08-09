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


def ath_profit_flag(
    current_ttm_profit_cr: Optional[float],
    market_cap: Optional[float],
    market_cap_price: Optional[float],
    historical_max_eps: Optional[float],
) -> bool:
    """True if the TTM-profit-derived current EPS is at/above the historical max EPS.

    LOCKED decision (ATH-Profit source = EPS-ATH proxy) resolved for the units mismatch
    between TTM profit (Cr) and historical EPS (Rs/share) by deriving current shares
    outstanding from data already on hand: ``shares = market_cap / market_cap_price``, then
    ``current_eps = current_ttm_profit_cr * 1e7 / shares``.

    ``market_cap_price`` MUST be the same-snapshot price ``market_cap`` was itself computed
    from (i.e. the weekly-cron CSV's own Current_Price), never a live/intraday price paired
    with a market cap from an earlier date. Market Cap is *defined* as shares x price at one
    moment -- dividing it by a price from a *different* moment doesn't recover the real share
    count, it just returns shares scaled by (old_price / new_price), which drifts with every
    price tick even though the real share count and profit haven't changed. This produced a
    real bug: EPS silently changing day to day purely from live-price movement, when the only
    things that should move EPS are a genuine profit change (quarterly) or a genuine share
    count change (buyback/issuance/split -- reflected in the next weekly CSV refresh).
    """
    values = [current_ttm_profit_cr, market_cap, market_cap_price, historical_max_eps]
    if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in values):
        return False
    if market_cap <= 0 or market_cap_price <= 0:
        return False

    shares_outstanding = market_cap / market_cap_price
    if shares_outstanding <= 0:
        return False

    current_eps = (current_ttm_profit_cr * 1e7) / shares_outstanding
    return current_eps >= historical_max_eps


def ath_sales_flag(
    latest_annual_sales: Optional[float],
    historical_max_sales_excl_latest: Optional[float],
) -> bool:
    """True if the most recent fiscal year's sales set a new all-time high (i.e. beat every
    prior year on record).

    There's no TTM/quarterly sales figure anywhere in the data (the same gap that got TTM
    Net Sales dropped from v1 entirely) — only the annual series in
    ``stock_fundamentals_yearly.csv``. So unlike ATH-Profit (which has a real TTM figure to
    compare), this is a same-frequency comparison: latest annual sales vs. the max of every
    *prior* year for that ticker (excluding the latest year itself, or it would trivially
    match whenever the latest year happens to also be the record year).
    """
    if latest_annual_sales is None or historical_max_sales_excl_latest is None:
        return False
    if pd.isna(latest_annual_sales) or pd.isna(historical_max_sales_excl_latest):
        return False
    return latest_annual_sales >= historical_max_sales_excl_latest


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
    window_days: int = C.RS_WINDOW_DAYS,
) -> Optional[float]:
    """365-day (``window_days``) close-to-close % return.

    ``close_series`` must have a DatetimeIndex sorted ascending. Uses the closest available
    trading day on or before ``latest_date - window_days`` as the base. Returns None if the
    series is empty, undated, or doesn't reach far enough back.
    """
    if close_series is None or len(close_series) == 0:
        return None
    if not isinstance(close_series.index, pd.DatetimeIndex):
        return None

    series = close_series.dropna()
    if series.empty:
        return None

    latest_date = series.index[-1]
    latest_close = float(series.iloc[-1])
    base_date = latest_date - pd.Timedelta(days=window_days)

    eligible = series[series.index <= base_date]
    if eligible.empty:
        return None

    base_close = float(eligible.iloc[-1])
    if base_close == 0:
        return None

    return (latest_close / base_close - 1.0) * 100.0


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
    batch computed them (they depend on 365-day trends that don't meaningfully change
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
