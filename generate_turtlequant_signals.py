#!/usr/bin/env python
"""
Generate Turtle Quant signals (weekly RS vs NSE:NIFTY + SuperTrend/ADX/RSI trend-following).

Runs the Turtle Quant screening pipeline (modules/turtlequant/screener.py) over the same NSE
universe the Turtle Strategy pipeline already uses, fetching weekly OHLCV from yfinance, and
writes one dated CSV that the dashboard loads at startup:

    turtlequant_signals_<YYYYMMDD>.csv

Universe source: same as generate_turtle_signals.py -- NSE_EQ_All_Stocks_Analysis.csv (Postgres
``nse_universe`` first, local CSV fallback). No fundamentals/categories file needed -- this is a
purely technical screen.

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
from modules.turtlequant import screener as sc

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")
SIGNALS_TEMPLATE = "turtlequant_signals_{date_str}.csv"

# CSV column name -> Postgres column name -- kept explicit here (not a shared implicit
# convention) so the mapping is visible right next to the write call it feeds, matching
# generate_turtle_signals.py's own style.
_SIGNALS_DB_COLUMNS = {
    "Symbol": "symbol", "Company": "company", "Sector": "sector", "Industry": "industry",
    "Current_Price": "current_price", "RS_Long_Term": "rs_long_term",
    "RS_Short_Term": "rs_short_term", "ADX": "adx", "RSI": "rsi",
    "SuperTrend_Direction": "supertrend_direction", "Volume_Building": "volume_building",
    "Price_Above_MA13": "price_above_ma13", "Signal": "signal",
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


def main():
    ap = argparse.ArgumentParser(description="Generate Turtle Quant signals")
    ap.add_argument("--limit", type=int, default=None, help="screen only the first N symbols")
    ap.add_argument("--pause", type=float, default=0.1,
                     help="seconds to pause after each symbol's fetch, to ease Yahoo Finance "
                          "throttling risk across the full universe (default: 0.1)")
    args = ap.parse_args()

    universe = load_universe()
    print(f"Universe: {len(universe)} symbols.")

    out = sc.run_pipeline(universe, limit=args.limit, verbose=True, pause_seconds=args.pause)

    date_str = pd.Timestamp.now().strftime("%Y%m%d")
    signal_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    signals_path = os.path.join(REPO_BASE_PATH, SIGNALS_TEMPLATE.format(date_str=date_str))

    # Always write the file (with headers) so the dashboard has a stable, current target.
    signals = out["signals"] if not out["signals"].empty else pd.DataFrame(columns=sc.SIGNAL_COLUMNS)
    signals.to_csv(signals_path, index=False)

    counts = signals["Signal"].value_counts().to_dict() if not signals.empty else {}
    print(f"\nTurtle Quant signals : {len(signals):>4}  -> {os.path.basename(signals_path)}")
    print(f"  BUY={counts.get('BUY', 0)}  HOLD={counts.get('HOLD', 0)}  SELL={counts.get('SELL', 0)}")
    print(f"Rejections           : {len(out['rejections']):>4}")

    # Postgres writes -- dual-write alongside the CSV, same pattern as generate_turtle_signals.py.
    try:
        conn = mdw.get_connection()
        try:
            if not signals.empty:
                db_signals = signals.rename(columns=_SIGNALS_DB_COLUMNS).copy()
                db_signals["signal_date"] = signal_date
                n = mdw.upsert_dataframe(conn, "turtlequant_signals_latest", db_signals, conflict_columns=["symbol"])
                print(f"DB: turtlequant_signals_latest upserted {n} rows")
                n = mdw.upsert_dataframe(
                    conn, "turtlequant_signals_history", db_signals,
                    conflict_columns=["symbol", "signal_date"], touch_updated_at=False,
                )
                print(f"DB: turtlequant_signals_history upserted {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed, CSV above is still the source of truth for now: {exc}")


if __name__ == "__main__":
    main()
