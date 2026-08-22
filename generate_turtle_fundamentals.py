#!/usr/bin/env python
"""
Generate consolidated TTM + historical-max-annual Net Profit and Net Sales for the Turtle
Strategy universe, scraped from screener.in (modules/turtle/standalone_fundamentals.py --
module name is historical; it fetches the ``/consolidated/`` page, not standalone).

Writes turtle_screener_fundamentals.csv (repo root):
    Symbol, TTM_Net_Profit, Max_Annual_Net_Profit, TTM_Net_Sales, Max_Annual_Net_Sales

generate_turtle_signals.py reads this file (instead of the old, EPS-proxy-based
stock_fundamentals_yearly.csv approach) so ATH_Profit_Flag/ATH_Sales_Flag can do a
direct TTM-vs-max-annual comparison with no unit-conversion step (see modules/turtle/compute.py
::_ttm_ath_flag for why that's now possible: both figures come from the same screener.in table).

screener.in is a much smaller site than NSE/Yahoo and has no documented rate-limit policy, so
this paces requests conservatively and checkpoints progress every CHECKPOINT_EVERY symbols to
output/turtle_screener_fundamentals_checkpoint.csv -- a full-universe run (~2,300+ symbols) can
take a while; --resume picks up where a prior (interrupted) run left off instead of re-fetching
everything.

Usage
-----
    python generate_turtle_fundamentals.py                # full universe
    python generate_turtle_fundamentals.py --limit 25      # quick subset (testing)
    python generate_turtle_fundamentals.py --resume        # continue from the last checkpoint
"""
import argparse
import os
import time

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw
from modules.turtle import standalone_fundamentals as sf

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")
OUTPUT_FILE = os.path.join(REPO_BASE_PATH, "turtle_screener_fundamentals.csv")
CHECKPOINT_FILE = os.path.join(REPO_BASE_PATH, "output", "turtle_screener_fundamentals_checkpoint.csv")
OUTPUT_COLUMNS = ["Symbol", "TTM_Net_Profit", "Max_Annual_Net_Profit", "TTM_Net_Sales", "Max_Annual_Net_Sales"]
CHECKPOINT_EVERY = 50

# CSV column name -> Postgres column name (see generate_turtle_signals.py for why this stays
# explicit at the call site rather than a shared implicit convention).
_FUNDAMENTALS_DB_COLUMNS = {
    "Symbol": "symbol", "TTM_Net_Profit": "ttm_net_profit",
    "Max_Annual_Net_Profit": "max_annual_net_profit", "TTM_Net_Sales": "ttm_net_sales",
    "Max_Annual_Net_Sales": "max_annual_net_sales",
}


def load_universe_symbols() -> list:
    # nse_universe is produced by a separate, earlier-running weekly workflow -- Postgres is
    # the real cross-workflow hand-off now that its CSV isn't committed to git; the local file
    # read below is just a local-dev fallback (see generate_turtle_signals.py::_from_postgres).
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, "nse_universe")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres read of nse_universe failed, falling back to local CSV: {exc}")
        df = pd.DataFrame()

    if not df.empty:
        symbols = df["symbol"].astype(str).str.upper().str.strip()
    else:
        if not os.path.exists(UNIVERSE_FILE):
            raise SystemExit(
                f"Universe not found in Postgres (nse_universe) or at {UNIVERSE_FILE}.\n"
                "Run the weekly stock screening first (generate_weekly_stock_list.py)."
            )
        symbols = pd.read_csv(UNIVERSE_FILE)["Symbol"].astype(str).str.upper().str.strip()
    symbols = symbols[symbols.str.len() > 0]
    return sorted(symbols.unique().tolist())


def load_checkpoint() -> pd.DataFrame:
    if os.path.exists(CHECKPOINT_FILE):
        return pd.read_csv(CHECKPOINT_FILE)
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def fetch_one(symbol: str, session, retries: int, pause: float) -> dict:
    result = sf.fetch_profit_and_loss(symbol, session=session, retries=retries, pause=pause)
    if result is None:
        return {
            "Symbol": symbol, "TTM_Net_Profit": None, "Max_Annual_Net_Profit": None,
            "TTM_Net_Sales": None, "Max_Annual_Net_Sales": None,
        }
    annual_profit = result.get("annual_net_profit") or []
    annual_sales = result.get("annual_net_sales") or []
    return {
        "Symbol": symbol,
        "TTM_Net_Profit": result.get("ttm_net_profit"),
        "Max_Annual_Net_Profit": max(annual_profit) if annual_profit else None,
        "TTM_Net_Sales": result.get("ttm_net_sales"),
        "Max_Annual_Net_Sales": max(annual_sales) if annual_sales else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Generate Turtle Strategy consolidated fundamentals from screener.in")
    ap.add_argument("--limit", type=int, default=None, help="fetch only the first N symbols")
    ap.add_argument("--pause", type=float, default=0.5,
                     help="seconds to pause between symbols (screener.in is small, no documented "
                          "rate-limit policy -- default is conservative) (default: 0.5)")
    ap.add_argument("--retries", type=int, default=3, help="retries per symbol on network failure")
    ap.add_argument("--resume", action="store_true", help="skip symbols already in the checkpoint file")
    args = ap.parse_args()

    symbols = load_universe_symbols()
    if args.limit:
        symbols = symbols[: args.limit]

    rows = []
    if args.resume:
        checkpoint = load_checkpoint()
        if not checkpoint.empty:
            done_symbols = set(checkpoint["Symbol"].astype(str).str.upper())
            rows = checkpoint.to_dict("records")
            symbols = [s for s in symbols if s not in done_symbols]
            print(f"Resuming: {len(done_symbols)} symbols already done, {len(symbols)} remaining.")

    print(f"Universe: {len(symbols)} symbols to fetch from screener.in (pause={args.pause}s).")
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)

    session = sf.new_session()
    ok_count = 0
    fail_count = 0
    start = time.time()
    try:
        for i, symbol in enumerate(symbols, 1):
            row = fetch_one(symbol, session, args.retries, args.pause)
            rows.append(row)
            if row["TTM_Net_Profit"] is not None or row["TTM_Net_Sales"] is not None:
                ok_count += 1
            else:
                fail_count += 1

            if i % CHECKPOINT_EVERY == 0:
                pd.DataFrame(rows, columns=OUTPUT_COLUMNS).to_csv(CHECKPOINT_FILE, index=False)

            if i % 100 == 0:
                elapsed = time.time() - start
                print(f"  fundamentals: fetched {i}/{len(symbols)}  "
                      f"(ok={ok_count} fail={fail_count}, {elapsed:.0f}s elapsed)")
    finally:
        session.close()
        pd.DataFrame(rows, columns=OUTPUT_COLUMNS).to_csv(CHECKPOINT_FILE, index=False)

    result_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS).drop_duplicates(subset=["Symbol"], keep="last")
    result_df.to_csv(OUTPUT_FILE, index=False)

    elapsed = time.time() - start
    print(f"\nWrote {len(result_df)} rows -> {os.path.basename(OUTPUT_FILE)} ({elapsed:.0f}s)")
    print(f"  ok={ok_count}  fail(no data)={fail_count}")

    try:
        conn = mdw.get_connection()
        try:
            n = mdw.upsert_dataframe(
                conn, "turtle_fundamentals",
                result_df.rename(columns=_FUNDAMENTALS_DB_COLUMNS),
                conflict_columns=["symbol"],
            )
            print(f"DB: turtle_fundamentals upserted {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed, CSV above is still the source of truth for now: {exc}")


if __name__ == "__main__":
    main()
