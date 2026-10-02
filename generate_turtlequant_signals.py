#!/usr/bin/env python
"""
Generate Turtle Quant signals (fundamental quality/valuation screen).

2026-10-02: the original weekly RS/SuperTrend/ADX/RSI technical-signal system was removed per
explicit user request. This script now just projects the shared NSE universe + the quality/
valuation flags already computed by generate_turtle_fundamentals.py (turtle_fundamentals) into
one dated CSV + Postgres table the dashboard loads:

    turtlequant_signals_<YYYYMMDD>.csv

Universe source: same as generate_turtle_signals.py -- NSE_EQ_All_Stocks_Analysis.csv (Postgres
``nse_universe`` first, local CSV fallback).

Usage
-----
    python generate_turtlequant_signals.py                # full universe
    python generate_turtlequant_signals.py --limit 25      # quick subset (testing)
"""
import argparse
import os

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw
from modules.turtle import quality_flags as qf
from modules.turtlequant import screener as sc

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")
SIGNALS_TEMPLATE = "turtlequant_signals_{date_str}.csv"

# CSV column name -> Postgres column name -- kept explicit here (not a shared implicit
# convention) so the mapping is visible right next to the write call it feeds, matching
# generate_turtle_signals.py's own style.
_SIGNALS_DB_COLUMNS = {
    "Symbol": "symbol", "Company": "company", "Broad_Sector": "broad_sector",
    "Sector": "sector", "Industry": "industry", "Current_Price": "current_price",
    # 2026-10-01: the 9 fundamental quality/valuation flags (CamelCase -> snake_case, same
    # pairing as modules/turtlequant/screener.py's QUALITY_COLUMNS <-> quality_flags.QUALITY_FIELD_NAMES).
    **dict(zip(sc.QUALITY_COLUMNS, qf.QUALITY_FIELD_NAMES)),
}

# turtle_fundamentals is the SAME shared table generate_turtle_fundamentals.py (Turtle Strategy)
# writes -- company-attribute data (screener.in's Sector/Broad_Sector classification, plus the
# quality/valuation flags), not a strategy-specific computation, so Turtle Quant reads it too
# rather than duplicating a fetch.
_FUNDAMENTALS_FROM_DB = {
    "symbol": "Symbol", "ttm_net_profit": "TTM_Net_Profit",
    "max_annual_net_profit": "Max_Annual_Net_Profit", "ttm_net_sales": "TTM_Net_Sales",
    "max_annual_net_sales": "Max_Annual_Net_Sales",
    "broad_sector": "Broad_Sector", "sector": "Sector",
    "broad_industry": "Broad_Industry", "industry": "Industry",
    **dict(zip(qf.QUALITY_FIELD_NAMES, sc.QUALITY_COLUMNS)),
}

# Postgres column name -> CSV column name -- reverse of the universe read, same reasoning as
# generate_turtle_signals.py's _UNIVERSE_FROM_DB (the universe is produced by an earlier,
# separate weekly-screening workflow; Postgres is the real cross-workflow hand-off, the local
# CSV read is just a local-dev fallback).
_UNIVERSE_FROM_DB = {
    "symbol": "Symbol", "company_name": "Company Name", "sector": "Sector", "industry": "Industry",
    "current_price": "Current_Price",
}


def _from_postgres(table: str, rename_map: dict) -> pd.DataFrame:
    """Best-effort read of ``table`` via MARKET_DATA_DB_URL. Empty DataFrame (not an
    exception) on any failure, so callers fall back to their CSV/default path unchanged."""
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, table)
        finally:
            conn.close()
        return df.rename(columns=rename_map) if not df.empty else df
    except Exception as exc:
        print(f"WARNING: Postgres read of {table} failed, falling back to local CSV: {exc}")
        return pd.DataFrame()


def load_universe() -> pd.DataFrame:
    df = _from_postgres("nse_universe", _UNIVERSE_FROM_DB)
    if df.empty:
        if not os.path.exists(UNIVERSE_FILE):
            raise SystemExit(
                f"Universe not found in Postgres (nse_universe) or at {UNIVERSE_FILE}.\n"
                "Run the weekly stock screening first (generate_weekly_stock_list.py)."
            )
        df = pd.read_csv(UNIVERSE_FILE)
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    df = df.dropna(subset=["Symbol"])
    df = df[df["Symbol"].str.len() > 0]
    return df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)


def load_fundamentals() -> pd.DataFrame:
    """Best-effort read of turtle_fundamentals (screener.in Sector/Broad_Sector classification +
    quality/valuation flags) -- empty DataFrame (not an exception) if unavailable, same as every
    other optional input here; run_pipeline degrades to the universe CSV's Yahoo Sector tag and
    all-None quality flags when this is empty."""
    return _from_postgres("turtle_fundamentals", _FUNDAMENTALS_FROM_DB)


def main():
    ap = argparse.ArgumentParser(description="Generate Turtle Quant signals")
    ap.add_argument("--limit", type=int, default=None, help="screen only the first N symbols")
    args = ap.parse_args()

    universe = load_universe()
    fundamentals = load_fundamentals()
    print(f"Universe: {len(universe)} symbols. Fundamentals rows: {len(fundamentals)}.")

    out = sc.run_pipeline(universe, fundamentals_df=fundamentals, limit=args.limit, verbose=True)

    date_str = pd.Timestamp.now().strftime("%Y%m%d")
    signals_path = os.path.join(REPO_BASE_PATH, SIGNALS_TEMPLATE.format(date_str=date_str))

    # Always write the file (with headers) so the dashboard has a stable, current target.
    signals = out["signals"] if not out["signals"].empty else pd.DataFrame(columns=sc.SIGNAL_COLUMNS)
    signals.to_csv(signals_path, index=False)

    print(f"\nTurtle Quant signals : {len(signals):>4}  -> {os.path.basename(signals_path)}")
    for flag_col in [c for c in sc.QUALITY_COLUMNS if c.endswith("_Flag")]:
        true_count = int((signals[flag_col] == True).sum()) if flag_col in signals.columns else 0  # noqa: E712
        print(f"  {flag_col}: {true_count} True")

    # Postgres write -- dual-write alongside the CSV, same pattern as generate_turtle_signals.py.
    try:
        conn = mdw.get_connection()
        try:
            if not signals.empty:
                db_signals = signals.rename(columns=_SIGNALS_DB_COLUMNS).copy()
                n = mdw.upsert_dataframe(conn, "turtlequant_signals_latest", db_signals, conflict_columns=["symbol"])
                print(f"DB: turtlequant_signals_latest upserted {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed, CSV above is still the source of truth for now: {exc}")


if __name__ == "__main__":
    main()
