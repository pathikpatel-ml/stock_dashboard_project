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

from modules.turtle import screener as sc

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")
FUNDAMENTALS_FILE = os.path.join(REPO_BASE_PATH, "turtle_screener_fundamentals.csv")
CATEGORIES_FILE = os.path.join(REPO_BASE_PATH, "nse_categories.csv")
SIGNALS_TEMPLATE = "turtle_signals_{date_str}.csv"


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

    out = sc.run_pipeline(
        universe, fundamentals, benchmark_rs, categories_df=categories,
        limit=args.limit, verbose=True, pause_seconds=args.pause,
    )

    date_str = pd.Timestamp.now().strftime("%Y%m%d")
    signals_path = os.path.join(REPO_BASE_PATH, SIGNALS_TEMPLATE.format(date_str=date_str))

    # Always write the file (with headers) so the dashboard has a stable, current target.
    signals = out["signals"] if not out["signals"].empty else pd.DataFrame(columns=sc.SIGNAL_COLUMNS)
    signals.to_csv(signals_path, index=False)

    counts = signals["Signal"].value_counts().to_dict() if not signals.empty else {}
    print(f"\nTurtle signals   : {len(signals):>4}  -> {os.path.basename(signals_path)}")
    print(f"  ADD={counts.get('ADD', 0)}  HOLD={counts.get('HOLD', 0)}  EXIT={counts.get('EXIT', 0)}")
    print(f"Rejections       : {len(out['rejections']):>4}")


if __name__ == "__main__":
    main()
