"""
Orchestration layer for the Turtle Quant screener.

2026-10-02: the original weekly RS/SuperTrend/ADX/RSI technical-signal system (and its
BUY/HOLD/SELL classification) was removed entirely per explicit user request -- the user does
not trade off it. What remains is a pure fundamental quality/valuation screen: per symbol,
Sector/Industry/Current_Price (from the same universe frame the Turtle Strategy pipeline
already uses) plus the 9 quality/valuation flags computed by
``generate_turtle_fundamentals.py``/``modules/turtle/quality_flags.py`` and read here from the
shared ``turtle_fundamentals`` table. ``run_pipeline`` itself is a fast, pure DataFrame
transform with no network I/O.

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
from modules.turtle import constants as C
from modules.turtle import quality_flags as qf
from modules.turtle import screener as tt_screener
from . import benchmark_drawdown as bd

# CamelCase CSV/display names for the 9 fundamental quality/valuation flags (2026-10-01) --
# same values generate_turtle_fundamentals.py already computed and wrote to turtle_fundamentals
# (via modules/turtle/quality_flags.py), just threaded through here into Turtle Quant's own
# signal rows. Order matches quality_flags.QUALITY_FIELD_NAMES (snake_case) 1:1.
QUALITY_COLUMNS = [
    "Book_Value_CAGR_10Y", "Book_Value_Growth_Flag", "EPS_CAGR_10Y", "EPS_Growth_Flag",
    "ROCE_Avg_10Y", "ROCE_Flag", "Sales_CAGR_10Y", "Sales_Growth_Flag",
    "Promoter_Holding_Change_3Y", "Promoter_Holding_Flag",
    "Interest_Coverage", "Interest_Coverage_Flag",
    "Quality_Of_Turnover_Pct", "Quality_Of_Turnover_Flag",
    "PB_Current", "PB_5Y_Avg", "PB_Flag",
    "PS_Current", "PS_5Y_Avg", "PS_Flag",
    "PFCF_Current", "PFCF_5Y_Avg", "PFCF_Flag",
    "Growth_Category_Flag", "Red_Flag_Category_Flag", "Value_Category_Flag",
]

SIGNAL_COLUMNS = [
    "Symbol", "Company", "Broad_Sector", "Sector", "Industry", "Current_Price",
] + QUALITY_COLUMNS


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
    quality: Optional[dict] = None,
) -> Dict:
    """Build one symbol's Turtle Quant row -- pure, no I/O, never raises."""
    quality = quality or {}
    quality_row = {
        camel: quality.get(snake) for camel, snake in zip(QUALITY_COLUMNS, qf.QUALITY_FIELD_NAMES)
    }
    return {
        "Symbol": symbol,
        "Company": company,
        "Broad_Sector": broad_sector,
        "Sector": sector,
        "Industry": industry,
        "Current_Price": current_price,
        **quality_row,
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
    Sector/Broad_Sector classification and the 9 quality/valuation flags, preferred over the
    universe CSV's cruder Yahoo Finance "Sector" tag whenever screener.in has data for a symbol --
    mirrors modules/turtle/screener.py::run_pipeline's exact same preference/fallback rule, so
    both tabs' Sector columns and filters are consistent. Omitted/empty -> every stock falls back
    to the Yahoo tag and has no quality flags (all None).
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
        quality = {field: fundamentals.get(field) for field in qf.QUALITY_FIELD_NAMES}

        signals.append(screen_symbol(
            symbol,
            urow.get("Company Name", symbol),
            sector,
            urow.get("Industry"),
            urow.get("Current_Price"),
            broad_sector=broad_sector,
            quality=quality,
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


def compute_universe_drawdown(
    universe_df: pd.DataFrame, nifty_ref: Optional[Dict],
    limit: Optional[int] = None, verbose: bool = True,
) -> pd.DataFrame:
    """For every symbol in ``universe_df``, fetch its own daily Close history and compute the 4
    drawdown-comparison fields (``benchmark_drawdown.DRAWDOWN_FIELDS``) anchored to
    ``nifty_ref``'s dates. Returns a DataFrame with ``Symbol`` + those 4 fields -- a symbol
    whose price history doesn't reach back far enough (or whose fetch fails outright) just gets
    all 4 fields as None, same "degrade gracefully, never drop the row" convention
    modules/turtle/screener.py::run_pipeline uses for its own per-symbol fetch failures.
    """
    columns = ["Symbol"] + list(bd.DRAWDOWN_FIELDS)
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
        close = daily["Close"] if daily is not None and not daily.empty and "Close" in daily.columns else None

        out.append({"Symbol": symbol, **bd.compute_stock_drawdown(close, nifty_ref)})

        if verbose and i % 200 == 0:
            print(f"  turtlequant drawdown: {i}/{len(rows_df)} symbols")

    return pd.DataFrame(out, columns=columns) if out else pd.DataFrame(columns=columns)
