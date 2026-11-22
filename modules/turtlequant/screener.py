"""
Orchestration layer for the Turtle Quant screener.

2026-10-02: the original weekly RS/SuperTrend/ADX/RSI technical-signal system (and its
BUY/HOLD/SELL classification) was removed entirely per explicit user request -- the user does
not trade off it. 2026-11-22 (per explicit user request): the quality/valuation metrics that
briefly lived here afterward were also removed. What remains is Sector/Industry/Current_Price
(from the same universe frame the Turtle Strategy pipeline already uses) plus TTM Net
Profit/Sales and their ATH flags, read from the shared ``turtle_fundamentals`` table.
``run_pipeline`` itself is a fast, pure DataFrame transform with no network I/O.

2026-11-22 (per explicit user request): ``fetch_nifty50_reference``/``compute_universe_drawdown``
below DO reintroduce network I/O (yfinance), for a genuinely new, separate feature -- the
Nifty-50-anchored ATH/52-week-low drawdown comparison (see modules/turtlequant/benchmark_drawdown.py
for the actual math). Kept in this same orchestration module rather than a new one since it's
still "fetch real data, hand it to the pure compute layer", the same role this module already
plays for the fundamentals screen.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import yfinance as yf

from modules.breakout import data_feed
from modules.turtle import compute as tt_compute
from modules.turtle import constants as C
from modules.turtle import screener as tt_screener
from . import benchmark_drawdown as bd

# 2026-11-22 (per explicit user request): the 11 quality/valuation metrics (22 columns) that
# used to live here as QUALITY_COLUMNS -- Book Value/EPS/Sales CAGR, ROCE, Promoter Holding,
# Interest Coverage, Quality of Turnover, PB/PS/PFCF vs their own 5Y averages, plus each one's
# pass/fail flag -- were removed entirely from Turtle Quant (both this screener and
# turtlequant_signals_latest). They were never displayed on this tab's dashboard table anyway;
# Turtle Strategy/turtle_fundamentals still computes and stores them, untouched.

# TTM Profit/Sales + their ATH flags (2026-11-22, per explicit user request): "ATH" here means
# the SAME thing it does on the Turtle Strategy tab -- consolidated TTM Net Profit/Net Sales
# (screener.in) at/above the max annual figure on record, computed via the exact same pure
# functions (modules/turtle/compute.py::ath_profit_flag/ath_sales_flag) from the exact same
# shared turtle_fundamentals data both tabs already read -- not a separate computation, and not
# a cross-tab dependency on Turtle Strategy's own output table (turtle_signals_latest).
_ATH_COLUMNS = ["TTM_Net_Profit", "ATH_Profit_Flag", "TTM_Net_Sales", "ATH_Sales_Flag"]

SIGNAL_COLUMNS = [
    "Symbol", "Company", "Broad_Sector", "Sector", "Industry", "Current_Price",
] + _ATH_COLUMNS


def _is_valid_str(value) -> bool:
    """True for a real, non-blank string value -- False for None/NaN/empty. Local copy of
    modules.turtle.screener._is_valid_str (same tiny check, kept local rather than importing a
    private name across modules)."""
    if value is None:
        return False
    if isinstance(value, float) and pd.isna(value):
        return False
    return str(value).strip() != ""


def screen_symbol(
    symbol: str,
    company,
    sector,
    industry,
    current_price,
    broad_sector=None,
    ttm_net_profit=None,
    max_annual_net_profit=None,
    ttm_net_sales=None,
    max_annual_net_sales=None,
) -> Dict:
    """Build one symbol's Turtle Quant row -- pure, no I/O, never raises."""
    return {
        "Symbol": symbol,
        "Company": company,
        "Broad_Sector": broad_sector,
        "Sector": sector,
        "Industry": industry,
        "Current_Price": current_price,
        "TTM_Net_Profit": ttm_net_profit,
        "ATH_Profit_Flag": tt_compute.ath_profit_flag(ttm_net_profit, max_annual_net_profit),
        "TTM_Net_Sales": ttm_net_sales,
        "ATH_Sales_Flag": tt_compute.ath_sales_flag(ttm_net_sales, max_annual_net_sales),
    }


def run_pipeline(
    universe_df: pd.DataFrame,
    fundamentals_df: Optional[pd.DataFrame] = None,
    limit: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, pd.DataFrame]:
    """Run the Turtle Quant screen over ``universe_df`` (NSE_EQ_All_Stocks_Analysis.csv shape).

    Returns {"signals": df, "rejections": df} (rejections is always empty now -- kept in the
    return shape for call-site compatibility -- every universe row has enough data to produce a
    row here, since no per-symbol network fetch happens anymore).

    ``fundamentals_df`` (``turtle_fundamentals`` shape, optional -- the SAME shared table the
    Turtle Strategy pipeline reads, not a separate Turtle-Quant-specific one, since this is
    company-attribute data, not a strategy-specific computation) supplies screener.in's real
    Sector/Broad_Sector classification and TTM Net Profit/Sales, preferred over the universe
    CSV's cruder Yahoo Finance "Sector" tag whenever screener.in has data for a symbol --
    mirrors modules/turtle/screener.py::run_pipeline's exact same preference/fallback rule, so
    both tabs' Sector columns and filters are consistent. Omitted/empty -> every stock falls back
    to the Yahoo tag and has no TTM Profit/Sales data (all None).
    """
    fundamentals_lookup = tt_screener.build_fundamentals_lookup(fundamentals_df)
    rows = universe_df.head(limit) if limit else universe_df

    signals = []
    for _, urow in rows.iterrows():
        symbol = str(urow.get("Symbol", "")).strip().upper()
        if not symbol:
            continue

        fundamentals = fundamentals_lookup.get(symbol, {})
        screener_sector = fundamentals.get("sector")
        sector = screener_sector if _is_valid_str(screener_sector) else urow.get("Sector")
        broad_sector = fundamentals.get("broad_sector")

        signals.append(screen_symbol(
            symbol,
            urow.get("Company Name", symbol),
            sector,
            urow.get("Industry"),
            urow.get("Current_Price"),
            broad_sector=broad_sector,
            ttm_net_profit=fundamentals.get("ttm_net_profit"),
            max_annual_net_profit=fundamentals.get("max_annual_net_profit"),
            ttm_net_sales=fundamentals.get("ttm_net_sales"),
            max_annual_net_sales=fundamentals.get("max_annual_net_sales"),
        ))

    if verbose:
        print(f"  turtlequant: built {len(signals)}/{len(rows)} symbol rows")

    signals_df = pd.DataFrame(signals).reindex(columns=SIGNAL_COLUMNS) if signals else pd.DataFrame(columns=SIGNAL_COLUMNS)
    return {"signals": signals_df, "rejections": pd.DataFrame(columns=["Symbol", "reason"])}


# Full history, not just 2y -- Nifty 50's genuine all-time-high could in principle be older
# than any fixed recent window; "max" is what the live check (2026-11-22) that pinned down the
# High/Low-vs-Close convention actually used, going back to 2007 on yfinance.
NIFTY50_REFERENCE_HISTORY_PERIOD = "max"


def fetch_nifty50_reference(ticker: Optional[str] = None) -> Optional[Dict]:
    """Fetch Nifty 50's full daily OHLC and derive its ATH/52-week-low/today reference dict
    (see benchmark_drawdown.nifty_reference_from_ohlc) -- the shared baseline every stock's
    drawdown comparison is anchored to. Returns None (never raises) on any fetch/parse failure.
    """
    ticker = ticker or C.NIFTY_50_INDEX_TICKER
    try:
        hist = yf.Ticker(ticker).history(
            period=NIFTY50_REFERENCE_HISTORY_PERIOD, interval="1d", auto_adjust=False, timeout=30
        )
    except Exception:
        return None
    if hist is None or hist.empty:
        return None
    hist = hist.copy()
    hist.index = pd.DatetimeIndex(hist.index).tz_localize(None)
    return bd.nifty_reference_from_ohlc(hist)


# Per-stock price-ATH flag (2026-11-22, per explicit user request, for the Sector Pulse panel
# below): True if a stock's OWN current price is at/within 5% of its OWN historical max close --
# same computation and threshold as Turtle Strategy's own ath_price_flag (modules/turtle/
# compute.py::ath_price_flag), reusing the exact same monthly+daily fetch/max-close convention
# (modules/turtle/screener.py::run_pipeline lines ~468-496) so a genuine multi-year high is used,
# not just the ~2y daily window alone. None (not False) when the monthly history is missing or
# too short (< C.MIN_MONTHLY_ROWS_FOR_ATH) -- computing from daily-only data here would risk
# reintroducing the exact degenerate-1-row-monthly-data corruption already fixed once for the
# sectoral-index version of this flag (see constants.py's MIN_MONTHLY_ROWS_FOR_ATH note).
PRICE_ATH_FIELD = "ath_price_flag"


def _compute_ath_price_flag(daily: Optional[pd.DataFrame], monthly: Optional[pd.DataFrame]) -> Optional[bool]:
    daily_close = None
    if daily is not None and not daily.empty and "Close" in daily.columns:
        daily_close = pd.to_numeric(daily["Close"], errors="coerce").dropna()
        if daily_close.empty:
            daily_close = None
    if daily_close is None:
        return None

    monthly_close = None
    if monthly is not None and not monthly.empty and "Close" in monthly.columns:
        monthly_close = pd.to_numeric(monthly["Close"], errors="coerce").dropna()
        if len(monthly_close) < C.MIN_MONTHLY_ROWS_FOR_ATH:
            monthly_close = None
    if monthly_close is None:
        return None

    historical_max_close = max(float(daily_close.max()), float(monthly_close.max()))
    current_price = float(daily_close.iloc[-1])
    return tt_compute.ath_price_flag(current_price, historical_max_close)


def compute_universe_drawdown(
    universe_df: pd.DataFrame, nifty_ref: Optional[Dict],
    limit: Optional[int] = None, verbose: bool = True,
) -> pd.DataFrame:
    """For every symbol in ``universe_df``, fetch its own daily Close history and compute the 4
    drawdown-comparison fields (``benchmark_drawdown.DRAWDOWN_FIELDS``) anchored to
    ``nifty_ref``'s dates, PLUS (2026-11-22) its own price-ATH flag (``PRICE_ATH_FIELD``,
    fetched monthly history too -- see ``_compute_ath_price_flag``). Returns a DataFrame with
    ``Symbol`` + those 5 fields -- a symbol whose price history doesn't reach back far enough
    (or whose fetch fails outright) just gets all 5 fields as None, same "degrade gracefully,
    never drop the row" convention modules/turtle/screener.py::run_pipeline uses for its own
    per-symbol fetch failures.
    """
    columns = ["Symbol", PRICE_ATH_FIELD] + list(bd.DRAWDOWN_FIELDS)
    rows_df = universe_df.head(limit) if limit else universe_df

    out = []
    for i, (_, urow) in enumerate(rows_df.iterrows(), 1):
        symbol = str(urow.get("Symbol", "")).strip().upper()
        if not symbol:
            continue
        try:
            daily = data_feed.get_daily(symbol, period=C.DAILY_HISTORY_PERIOD)
        except Exception:
            daily = None
        try:
            monthly = data_feed.get_monthly(symbol, period=C.MONTHLY_HISTORY_PERIOD)
        except Exception:
            monthly = None

        out.append({
            "Symbol": symbol,
            PRICE_ATH_FIELD: _compute_ath_price_flag(daily, monthly),
            **bd.compute_stock_drawdown(daily, nifty_ref),
        })

        if verbose and i % 200 == 0:
            print(f"  turtlequant drawdown: {i}/{len(rows_df)} symbols")

    return pd.DataFrame(out, columns=columns) if out else pd.DataFrame(columns=columns)


# Sector Pulse (2026-11-22, per explicit user request): mirrors Turtle Strategy's own Sector
# Pulse panel in SHAPE (same 12 curated NSE sectoral index tags, from
# modules/turtle/constants.py::SECTORAL_INDEX_TICKERS, concatenated with a screener.in Sector
# breakdown into one combined list -- see modules/turtle/screener.py's
# fetch_sector_pulse_table/compute_sector_breadth_pulse) but is a PURE aggregation here: every
# member stock's own already-computed ATH_Price_Flag/RS_vs_Nifty_ATH/RS_vs_Nifty_52WkLow answers
# "how many stocks..." directly, with zero extra network I/O (unlike Turtle Strategy's version,
# which needs a separate index-level price/RS fetch) -- so this can run live, at render time,
# straight off data_manager.turtlequant_signals_df.
SECTOR_PULSE_COLUMNS = [
    "Sector", "ATH_Price_Stock", "Nifty50_Outperform_ATH", "Nifty50_Outperform_52WkLow", "Stock_Count",
]


def _sector_pulse_row(name: str, group: pd.DataFrame) -> Dict:
    ath_count = int((group["ATH_Price_Flag"] == True).sum()) if "ATH_Price_Flag" in group.columns else 0  # noqa: E712
    out_ath = int((group["RS_vs_Nifty_ATH"] > 0).sum()) if "RS_vs_Nifty_ATH" in group.columns else 0
    out_52wk = int((group["RS_vs_Nifty_52WkLow"] > 0).sum()) if "RS_vs_Nifty_52WkLow" in group.columns else 0
    return {
        "Sector": name,
        "ATH_Price_Stock": ath_count,
        "Nifty50_Outperform_ATH": out_ath,
        "Nifty50_Outperform_52WkLow": out_52wk,
        "Stock_Count": len(group),
    }


def compute_sector_pulse(
    signals_df: pd.DataFrame, categories_map: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """One row per curated NSE sectoral index tag PLUS one row per screener.in ``Sector`` value
    (see module-level comment above). ``categories_map`` (Symbol -> comma-joined NSE_Categories
    string, e.g. from ``nse_categories_df``) drives curated-index membership only -- the Sector
    rows use ``signals_df``'s own ``Sector`` column directly. Never raises; returns an empty
    (correctly-columned) DataFrame for empty/missing input.
    """
    empty = pd.DataFrame(columns=SECTOR_PULSE_COLUMNS)
    if signals_df is None or signals_df.empty or "Symbol" not in signals_df.columns:
        return empty

    df = signals_df.copy()
    categories_map = categories_map or {}
    df["_categories"] = df["Symbol"].map(categories_map)

    rows = [
        _sector_pulse_row(tag, df[df["_categories"].map(lambda v: tt_compute.filter_by_index(v, tag))])
        for tag in C.SECTORAL_INDEX_TICKERS.keys()
    ]

    if "Sector" in df.columns:
        sector_df = df.dropna(subset=["Sector"])
        sector_df = sector_df[sector_df["Sector"].astype(str).str.strip() != ""]
        for sector, group in sector_df.groupby("Sector"):
            rows.append(_sector_pulse_row(str(sector), group))

    return pd.DataFrame(rows, columns=SECTOR_PULSE_COLUMNS)
