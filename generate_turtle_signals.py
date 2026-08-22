#!/usr/bin/env python
"""
Generate Turtle Strategy signals (docs/TURTLE_STRATEGY_PLAN.md).

Runs the Turtle screening pipeline (modules/turtle/screener.py) over the NSE universe already
built by the weekly screening job, fetching monthly/daily OHLCV from yfinance for ATH price and
52-week (weekly-high-close) relative strength, and consolidated TTM/historical-max-annual Net Profit + Net Sales from
turtle_screener_fundamentals.csv (screener.in, via generate_turtle_fundamentals.py -- run that
script first/separately, on its own weekly cadence, since screener.in fundamentals don't change
daily), then writes one dated CSV that the dashboard loads at startup:

    turtle_signals_<YYYYMMDD>.csv

Universe source: NSE_EQ_All_Stocks_Analysis.csv (produced weekly by generate_weekly_stock_list.py)
already carries Sector, Industry, Current_Price, MA200 — no separate universe download needed.

Usage
-----
    python generate_turtle_signals.py                # full universe
    python generate_turtle_signals.py --limit 25      # quick subset (testing)
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
from modules.turtle import screener as sc

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")
FUNDAMENTALS_FILE = os.path.join(REPO_BASE_PATH, "turtle_screener_fundamentals.csv")
CATEGORIES_FILE = os.path.join(REPO_BASE_PATH, "nse_categories.csv")
SIGNALS_TEMPLATE = "turtle_signals_{date_str}.csv"
SECTOR_PULSE_FILE = os.path.join(REPO_BASE_PATH, "turtle_sector_pulse.csv")

# CSV column name -> Postgres column name. Kept explicit here (not a shared implicit
# convention) so the mapping is visible right next to the write call it feeds -- the
# equivalent reverse mapping lives in data_manager.py next to the matching read call.
_SECTOR_PULSE_DB_COLUMNS = {
    "Sector": "sector", "ATH_Price_Flag": "ath_price_flag", "RS_vs_Nifty50": "rs_vs_nifty50",
}
_SIGNALS_DB_COLUMNS = {
    "Symbol": "symbol", "Company": "company", "Sector": "sector", "Industry": "industry",
    "Current_Price": "current_price", "ATH_Price_Flag": "ath_price_flag",
    "TTM_Net_Profit": "ttm_net_profit", "ATH_Profit_Flag": "ath_profit_flag",
    "Above_MA212_Flag": "above_ma212_flag", "RS_Peer_Group": "rs_peer_group",
    "RS_vs_Sector": "rs_vs_sector", "RS_vs_Benchmark": "rs_vs_benchmark",
    "Outperformance_Flag": "outperformance_flag", "TTM_Net_Sales": "ttm_net_sales",
    "ATH_Sales": "ath_sales", "ATH_Sales_Flag": "ath_sales_flag", "Signal": "signal",
}


def load_universe() -> pd.DataFrame:
    if not os.path.exists(UNIVERSE_FILE):
        raise SystemExit(
            f"Universe file not found: {UNIVERSE_FILE}\n"
            "Run the weekly stock screening first (generate_weekly_stock_list.py)."
        )
    df = pd.read_csv(UNIVERSE_FILE)
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    df = df.dropna(subset=["Symbol"])
    df = df[df["Symbol"].str.len() > 0]
    return df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)


def load_fundamentals() -> pd.DataFrame:
    if not os.path.exists(FUNDAMENTALS_FILE):
        print(f"WARNING: {FUNDAMENTALS_FILE} not found — ATH-Profit/ATH-Sales will be unavailable. "
              "Run generate_turtle_fundamentals.py first.")
        return pd.DataFrame(columns=[
            "Symbol", "TTM_Net_Profit", "Max_Annual_Net_Profit", "TTM_Net_Sales", "Max_Annual_Net_Sales",
        ])
    return pd.read_csv(FUNDAMENTALS_FILE)


def load_categories() -> pd.DataFrame:
    if not os.path.exists(CATEGORIES_FILE):
        print(f"WARNING: {CATEGORIES_FILE} not found — RS peer groups will all fall back to "
              "the broad Sector column (no sectoral-index basket available).")
        return pd.DataFrame(columns=["Symbol", "NSE_Categories"])
    return pd.read_csv(CATEGORIES_FILE)


def main():
    ap = argparse.ArgumentParser(description="Generate Turtle Strategy signals")
    ap.add_argument("--limit", type=int, default=None, help="screen only the first N symbols")
    ap.add_argument("--pause", type=float, default=0.1,
                     help="seconds to pause after each symbol's fetch, to ease Yahoo Finance "
                          "throttling risk across the full ~2,365-symbol universe (default: 0.1)")
    args = ap.parse_args()

    universe = load_universe()
    fundamentals = load_fundamentals()
    categories = load_categories()
    print(f"Universe: {len(universe)} symbols. Fundamentals rows: {len(fundamentals)}. "
          f"Category rows: {len(categories)}.")

    # LOCKED decision #2: benchmark = BSE 500, proxied by Nifty 500 (^CRSLDX). A failure here
    # must stop the run, not silently degrade to some other benchmark.
    benchmark_rs = sc.fetch_benchmark_rs()
    print(f"Benchmark ({sc.C.BENCHMARK_LABEL}) 52wk RS: {benchmark_rs:.2f}%")

    # Sectoral indices' own direct RS (2026-08-20) -- takes priority over the leave-one-out
    # peer-average for any sectoral tag it covers. A failed/missing index here just means
    # run_pipeline falls back to the peer-average for that one index, not a run-stopping error.
    sectoral_index_rs = sc.fetch_sectoral_index_rs()
    print(f"Sectoral index RS: {len(sectoral_index_rs)}/{len(sc.C.SECTORAL_INDEX_TICKERS)} fetched "
          f"({', '.join(f'{k}={v:.1f}%' for k, v in sectoral_index_rs.items())})")

    out = sc.run_pipeline(
        universe, fundamentals, benchmark_rs, categories_df=categories,
        sectoral_index_rs=sectoral_index_rs,
        limit=args.limit, verbose=True, pause_seconds=args.pause,
    )

    # Sector Pulse table (2026-08-20) -- dashboard summary, one row per sectoral index (not
    # per stock): ATH_Price_Flag + RS_vs_Nifty50, both computed on the index's own price
    # series directly. Non-dated rolling file (like turtle_live_prices.csv), always
    # (re)written so a transient fetch failure here doesn't leave a stale file that never
    # updates -- an empty table just means the dashboard panel shows nothing this run.
    sector_pulse = sc.fetch_sector_pulse_table()
    sector_pulse.to_csv(SECTOR_PULSE_FILE, index=False)
    print(f"Sector Pulse     : {len(sector_pulse):>4}  -> {os.path.basename(SECTOR_PULSE_FILE)}")

    date_str = pd.Timestamp.now().strftime("%Y%m%d")
    signal_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    signals_path = os.path.join(REPO_BASE_PATH, SIGNALS_TEMPLATE.format(date_str=date_str))

    # Always write the file (with headers) so the dashboard has a stable, current target.
    signals = out["signals"] if not out["signals"].empty else pd.DataFrame(columns=sc.SIGNAL_COLUMNS)
    signals.to_csv(signals_path, index=False)

    counts = signals["Signal"].value_counts().to_dict() if not signals.empty else {}
    print(f"\nTurtle signals   : {len(signals):>4}  -> {os.path.basename(signals_path)}")
    print(f"  ADD={counts.get('ADD', 0)}  HOLD={counts.get('HOLD', 0)}  EXIT={counts.get('EXIT', 0)}")
    print(f"Rejections       : {len(out['rejections']):>4}")

    # Postgres writes (2026-08-20 migration) -- dual-write alongside the CSVs above during the
    # migration/verification period; CSV writes get removed once every table's read side is
    # confirmed working end to end (see migrations/20260820_market_data_tables.sql).
    try:
        conn = mdw.get_connection()
        try:
            n = mdw.upsert_dataframe(
                conn, "turtle_sector_pulse",
                sector_pulse.rename(columns=_SECTOR_PULSE_DB_COLUMNS),
                conflict_columns=["sector"],
            )
            print(f"DB: turtle_sector_pulse upserted {n} rows")

            if not signals.empty:
                db_signals = signals.rename(columns=_SIGNALS_DB_COLUMNS).copy()
                db_signals["signal_date"] = signal_date
                n = mdw.upsert_dataframe(conn, "turtle_signals_latest", db_signals, conflict_columns=["symbol"])
                print(f"DB: turtle_signals_latest upserted {n} rows")
                n = mdw.upsert_dataframe(
                    conn, "turtle_signals_history", db_signals,
                    conflict_columns=["symbol", "signal_date"], touch_updated_at=False,
                )
                print(f"DB: turtle_signals_history upserted {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed, CSVs above are still the source of truth for now: {exc}")


if __name__ == "__main__":
    main()
