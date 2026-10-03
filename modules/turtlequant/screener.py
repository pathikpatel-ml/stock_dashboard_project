"""
Orchestration layer for the Turtle Quant screener.

2026-10-02: the original weekly RS/SuperTrend/ADX/RSI technical-signal system (and its
BUY/HOLD/SELL classification) was removed entirely per explicit user request -- the user does
not trade off it. What remains is a pure fundamental quality/valuation screen: per symbol,
Sector/Industry/Current_Price (from the same universe frame the Turtle Strategy pipeline
already uses) plus the 9 quality/valuation flags computed by
``generate_turtle_fundamentals.py``/``modules/turtle/quality_flags.py`` and read here from the
shared ``turtle_fundamentals`` table. No network I/O happens in this module anymore -- every
value comes from already-fetched upstream data, so ``run_pipeline`` is now a fast, pure
DataFrame transform.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from modules.turtle import quality_flags as qf
from modules.turtle import screener as tt_screener

# CamelCase CSV/display names for the 9 fundamental quality/valuation flags (2026-10-01) --
# same values generate_turtle_fundamentals.py already computed and wrote to turtle_fundamentals
# (via modules/turtle/quality_flags.py), just threaded through here into Turtle Quant's own
# signal rows. Order matches quality_flags.QUALITY_FIELD_NAMES (snake_case) 1:1.
QUALITY_COLUMNS = [
    "Book_Value_CAGR_10Y", "Book_Value_Growth_Flag", "EPS_CAGR_10Y", "EPS_Growth_Flag",
    "ROE_Avg_10Y", "ROE_Flag", "Sales_CAGR_10Y", "Sales_Growth_Flag",
    "Promoter_Holding_Change_3Y", "Promoter_Holding_Flag",
    "Interest_Coverage", "Interest_Coverage_Flag",
    "Quality_Of_Turnover_Pct", "Quality_Of_Turnover_Flag",
    "PB_Current", "PB_5Y_Avg", "PB_Flag",
    "PS_Current", "PS_5Y_Avg", "PS_Flag",
    "PCF_Current", "PCF_5Y_Avg", "PCF_Flag",
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
