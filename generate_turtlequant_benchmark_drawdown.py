#!/usr/bin/env python
"""
Generate Turtle Quant's Nifty-50-anchored ATH/52-week-low drawdown comparison
(2026-11-22, per explicit user request).

Fetches Nifty 50's own all-time-high date/price, 52-week-low date/price, and today's close
(see modules/turtlequant/screener.py::fetch_nifty50_reference -- ATH/52wk-low use the index's
intraday High/Low, confirmed live against real data; "today" uses the close), then for every
stock in the universe fetches its own daily close history and computes how far it has moved
from ITS OWN price on those same two reference dates to today, compared to how far Nifty moved
over the same span (modules/turtlequant/benchmark_drawdown.py has the actual formulas).

Writes:
  * turtlequant_nifty_benchmark -- the single shared Nifty 50 reference row.
  * turtlequant_signals_latest  -- 4 columns per stock (stock_ath_return_pct,
    stock_52wklow_return_pct, rs_vs_nifty_ath, rs_vs_nifty_52wklow), upserted WITHOUT touching
    any of that table's other (fundamentals-screen) columns, which generate_turtlequant_signals.py
    owns separately.

Usage
-----
    python generate_turtlequant_benchmark_drawdown.py              # full universe
    python generate_turtlequant_benchmark_drawdown.py --limit 25   # quick subset (testing)
"""
import argparse

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw
from generate_turtlequant_signals import load_universe
from modules.turtlequant import benchmark_drawdown as bd
from modules.turtlequant import screener as tq_screener


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="compute only the first N symbols")
    args = ap.parse_args()

    nifty_ref = tq_screener.fetch_nifty50_reference()
    if nifty_ref is None:
        raise SystemExit(
            "Could not fetch Nifty 50 reference data (ATH/52-week-low/today) -- aborting "
            "without touching any stored data."
        )
    print(
        f"Nifty 50 reference: ATH {nifty_ref['ath_price']:.2f} on {nifty_ref['ath_date']}, "
        f"52wk-low {nifty_ref['low_52wk_price']:.2f} on {nifty_ref['low_52wk_date']}, "
        f"today {nifty_ref['today_price']:.2f} on {nifty_ref['today_date']}"
    )

    universe = load_universe()
    print(f"Universe: {len(universe)} symbols.")

    drawdown_df = tq_screener.compute_universe_drawdown(universe, nifty_ref, limit=args.limit, verbose=True)
    computed = drawdown_df["stock_ath_return_pct"].notna().sum() if not drawdown_df.empty else 0
    print(f"Computed drawdown comparison for {computed}/{len(drawdown_df)} symbols "
          f"(the rest have insufficient price history reaching back to the reference dates).")

    try:
        conn = mdw.get_connection()
        try:
            ref_df = pd.DataFrame([{
                "benchmark": "NIFTY50",
                "ath_price": nifty_ref["ath_price"], "ath_date": nifty_ref["ath_date"],
                "low_52wk_price": nifty_ref["low_52wk_price"], "low_52wk_date": nifty_ref["low_52wk_date"],
                "today_price": nifty_ref["today_price"], "today_date": nifty_ref["today_date"],
            }])
            mdw.upsert_dataframe(conn, "turtlequant_nifty_benchmark", ref_df, conflict_columns=["benchmark"])
            print("DB: turtlequant_nifty_benchmark upserted")

            if not drawdown_df.empty:
                n = mdw.upsert_dataframe(
                    conn, "turtlequant_signals_latest", drawdown_df.rename(columns={"Symbol": "symbol"}),
                    conflict_columns=["symbol"], update_columns=list(bd.DRAWDOWN_FIELDS),
                )
                print(f"DB: turtlequant_signals_latest updated {n} rows (drawdown columns only)")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed: {exc}")


if __name__ == "__main__":
    main()
