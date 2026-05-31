#!/usr/bin/env python
"""
Generate Multi-Year Breakout signals + near-breakout watchlist.

Mirrors ``generate_daily_signals.py`` (the V20 generator): reads the screened universe
``Master_company_market_trend_analysis.csv``, runs the breakout screening pipeline
(modules/breakout/screener.py) over each symbol fetching monthly/daily OHLCV from yfinance and
recent delivery % from the NSE Bhav Copy monthly store, then writes two dated CSVs that the
dashboard loads at startup:

    breakout_signals_<YYYYMMDD>.csv     -> Module 1 (Breakout Alerts Feed)
    breakout_watchlist_<YYYYMMDD>.csv   -> Module 2 (Near-Breakout Watchlist)

Usage
-----
    python generate_breakout_signals.py                  # full universe, delivery required
    python generate_breakout_signals.py --limit 25       # quick subset (testing)
    python generate_breakout_signals.py --delivery-optional   # bootstrap before delivery history exists
"""
import argparse
import os

import pandas as pd

from modules.breakout import delivery_data as dd
from modules.breakout import screener as sc

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "Master_company_market_trend_analysis.csv")
SIGNALS_TEMPLATE = "breakout_signals_{date_str}.csv"
WATCHLIST_TEMPLATE = "breakout_watchlist_{date_str}.csv"

# Reuse the V20 PSU exclusion set (kept in sync with data_manager.KNOWN_PSU_SYMBOLS).
KNOWN_PSU_SYMBOLS = {
    "BHEL", "BPCL", "COALINDIA", "CONCOR", "GAIL", "HAL", "HPCL", "HUDCO", "IOC",
    "IRCON", "IRCTC", "IRFC", "IREDA", "LICI", "NBCC", "NLCINDIA", "NMDC", "NTPC",
    "OIL", "ONGC", "PFC", "POWERGRID", "RAILTEL", "RCF", "RECLTD", "SAIL", "SBI", "SBIN",
    "SBICARD", "SBILIFE", "SCI", "UNIONBANK", "PNB", "IOB", "INDIANB", "BANKINDIA",
    "CENTRALBK", "CANBK",
}


def load_universe() -> pd.DataFrame:
    if not os.path.exists(UNIVERSE_FILE):
        raise SystemExit(
            f"Universe file not found: {UNIVERSE_FILE}\n"
            "Run the weekly stock screening first (generate_weekly_stock_list.py)."
        )
    df = pd.read_csv(UNIVERSE_FILE)
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    return df[~df["Symbol"].isin(KNOWN_PSU_SYMBOLS)].reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description="Generate Multi-Year Breakout signals")
    ap.add_argument("--limit", type=int, default=None, help="screen only the first N symbols")
    ap.add_argument("--delivery-optional", action="store_true",
                    help="do not reject when delivery history is unavailable (bootstrap mode)")
    args = ap.parse_args()

    universe = load_universe()
    monthly_store = dd.load_monthly_store()
    print(f"Universe: {len(universe)} symbols. Delivery store rows: {len(monthly_store)}.")
    if monthly_store.empty and not args.delivery_optional:
        print("WARNING: delivery store is empty — every breakout will be rejected at STEP 6.\n"
              "         Run download_delivery_data.py --backfill-days 120 first, or pass --delivery-optional.")

    out = sc.run_pipeline(
        universe,
        monthly_store,
        require_delivery=not args.delivery_optional,
        limit=args.limit,
        verbose=True,
    )

    date_str = pd.Timestamp.now().strftime("%Y%m%d")
    signals_path = os.path.join(REPO_BASE_PATH, SIGNALS_TEMPLATE.format(date_str=date_str))
    watch_path = os.path.join(REPO_BASE_PATH, WATCHLIST_TEMPLATE.format(date_str=date_str))

    # Always write the files (with headers) so the dashboard has a stable, current target.
    signals = out["signals"] if not out["signals"].empty else pd.DataFrame(columns=sc.SIGNAL_COLUMNS)
    watch = out["watchlist"] if not out["watchlist"].empty else pd.DataFrame(columns=sc.WATCHLIST_COLUMNS)
    signals.to_csv(signals_path, index=False)
    watch.to_csv(watch_path, index=False)

    print(f"\nBreakout signals : {len(signals):>4}  -> {os.path.basename(signals_path)}")
    print(f"Watchlist        : {len(watch):>4}  -> {os.path.basename(watch_path)}")
    print(f"Rejections       : {len(out['rejections']):>4}")


if __name__ == "__main__":
    main()
