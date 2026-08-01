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
    current_price: Optional[float],
    historical_max_eps: Optional[float],
) -> bool:
    """True if the TTM-profit-derived current EPS is at/above the historical max EPS.

    LOCKED decision (ATH-Profit source = EPS-ATH proxy) resolved for the units mismatch
    between TTM profit (Cr) and historical EPS (Rs/share) by deriving current shares
    outstanding from data already on hand: ``shares = market_cap / current_price``, then
    ``current_eps = current_ttm_profit_cr * 1e7 / shares``.
    """
    values = [current_ttm_profit_cr, market_cap, current_price, historical_max_eps]
    if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in values):
        return False
    if market_cap <= 0 or current_price <= 0:
        return False

    shares_outstanding = market_cap / current_price
    if shares_outstanding <= 0:
        return False

    current_eps = (current_ttm_profit_cr * 1e7) / shares_outstanding
    return current_eps >= historical_max_eps


def above_exit_flag(current_price: Optional[float], ma200: Optional[float]) -> bool:
    """True if Current_Price > MA200 (reused exit-price proxy, not a new 212-day SMA)."""
    if current_price is None or ma200 is None:
        return False
    if pd.isna(current_price) or pd.isna(ma200):
        return False
    return current_price > ma200


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
    HOLD — meets ANY 2 of: ATH Profit, Above Exit Price (MA200), Outperformance.
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
