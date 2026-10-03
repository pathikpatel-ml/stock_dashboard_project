#!/usr/bin/env python
"""
Generate consolidated TTM + historical-max-annual Net Profit and Net Sales for the Turtle
Strategy universe, scraped from screener.in (modules/turtle/standalone_fundamentals.py --
module name is historical; it fetches the ``/consolidated/`` page, not standalone).

Writes turtle_screener_fundamentals.csv (repo root):
    Symbol, TTM_Net_Profit, Max_Annual_Net_Profit, TTM_Net_Sales, Max_Annual_Net_Sales,
    Broad_Sector, Sector, Broad_Industry, Industry

generate_turtle_signals.py reads this file (instead of the old, EPS-proxy-based
stock_fundamentals_yearly.csv approach) so ATH_Profit_Flag/ATH_Sales_Flag can do a
direct TTM-vs-max-annual comparison with no unit-conversion step (see modules/turtle/compute.py
::_ttm_ath_flag for why that's now possible: both figures come from the same screener.in table).

The four Broad_Sector/Sector/Broad_Industry/Industry columns (2026-09) are screener.in's own
classification (verified live: 12 Broad Sectors, 22 Sectors, 58 Broad Industries, 188
Industries -- a real hierarchy, unlike Yahoo Finance's crude 12-value "Sector" tag the universe
CSV carries), extracted from the SAME company-page response already fetched here for TTM
profit/sales -- no extra network cost. modules/turtle/screener.py prefers Sector/Broad_Sector
from this file over the universe CSV's Yahoo tag whenever screener.in has it.

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
import calendar
import os
import time

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw
from modules.breakout import data_feed
from modules.turtle import nse_shareholding as nse_sh
from modules.turtle import quality_flags as qf
from modules.turtle import standalone_fundamentals as sf

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")
OUTPUT_FILE = os.path.join(REPO_BASE_PATH, "turtle_screener_fundamentals.csv")
CHECKPOINT_FILE = os.path.join(REPO_BASE_PATH, "output", "turtle_screener_fundamentals_checkpoint.csv")

# 2026-10-01: the 9 Turtle Quant quality/valuation flags (see modules/turtle/quality_flags.py)
# -- computed here (not in generate_turtlequant_signals.py) since they're derived from the SAME
# screener.in page already fetched for TTM profit/sales/sector, just with one extra yfinance
# monthly-price fetch per symbol for the valuation-ratio checks (see _year_end_prices below).
_QUALITY_COLUMNS = [
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

OUTPUT_COLUMNS = [
    "Symbol", "TTM_Net_Profit", "Max_Annual_Net_Profit", "TTM_Net_Sales", "Max_Annual_Net_Sales",
    "Broad_Sector", "Sector", "Broad_Industry", "Industry",
] + _QUALITY_COLUMNS
CHECKPOINT_EVERY = 50

# CSV column name -> Postgres column name (see generate_turtle_signals.py for why this stays
# explicit at the call site rather than a shared implicit convention).
_FUNDAMENTALS_DB_COLUMNS = {
    "Symbol": "symbol", "TTM_Net_Profit": "ttm_net_profit",
    "Max_Annual_Net_Profit": "max_annual_net_profit", "TTM_Net_Sales": "ttm_net_sales",
    "Max_Annual_Net_Sales": "max_annual_net_sales",
    "Broad_Sector": "broad_sector", "Sector": "sector",
    "Broad_Industry": "broad_industry", "Industry": "industry",
    "Book_Value_CAGR_10Y": "book_value_cagr_10y", "Book_Value_Growth_Flag": "book_value_growth_flag",
    "EPS_CAGR_10Y": "eps_cagr_10y", "EPS_Growth_Flag": "eps_growth_flag",
    "ROE_Avg_10Y": "roe_avg_10y", "ROE_Flag": "roe_flag",
    "Sales_CAGR_10Y": "sales_cagr_10y", "Sales_Growth_Flag": "sales_growth_flag",
    "Promoter_Holding_Change_3Y": "promoter_holding_change_3y", "Promoter_Holding_Flag": "promoter_holding_flag",
    "Interest_Coverage": "interest_coverage", "Interest_Coverage_Flag": "interest_coverage_flag",
    "Quality_Of_Turnover_Pct": "quality_of_turnover_pct", "Quality_Of_Turnover_Flag": "quality_of_turnover_flag",
    "PB_Current": "pb_current", "PB_5Y_Avg": "pb_5y_avg", "PB_Flag": "pb_flag",
    "PS_Current": "ps_current", "PS_5Y_Avg": "ps_5y_avg", "PS_Flag": "ps_flag",
    "PCF_Current": "pcf_current", "PCF_5Y_Avg": "pcf_5y_avg", "PCF_Flag": "pcf_flag",
    "Growth_Category_Flag": "growth_category_flag", "Red_Flag_Category_Flag": "red_flag_category_flag",
    "Value_Category_Flag": "value_category_flag",
}

_MONTH_NUM = {m: i for i, m in enumerate(calendar.month_abbr) if m}


def _year_end_prices(monthly: pd.DataFrame, periods: list) -> dict:
    """Maps each screener.in period label (e.g. "Mar 2024") to the closest available monthly
    close on or before that fiscal year-end date -- feeds quality_flags.compute_all's
    valuation-ratio checks. Empty dict (not an exception) for missing/unusable price data."""
    if monthly is None or monthly.empty or "Close" not in monthly.columns:
        return {}
    index = pd.DatetimeIndex(monthly.index).tz_localize(None)
    result = {}
    for period in periods:
        try:
            month_str, year_str = period.split()
            month_num = _MONTH_NUM.get(month_str)
            if month_num is None:
                continue
            last_day = calendar.monthrange(int(year_str), month_num)[1]
            target = pd.Timestamp(year=int(year_str), month=month_num, day=last_day)
        except (ValueError, IndexError):
            continue
        mask = index <= target
        if mask.any():
            result[period] = float(monthly["Close"].to_numpy()[mask][-1])
    return result


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


def fetch_one(symbol: str, session, retries: int, pause: float, nse_session=None) -> dict:
    empty_quality = {c: None for c in _QUALITY_COLUMNS}
    result = sf.fetch_profit_and_loss(symbol, session=session, retries=retries, pause=pause)
    if result is None:
        return {
            "Symbol": symbol, "TTM_Net_Profit": None, "Max_Annual_Net_Profit": None,
            "TTM_Net_Sales": None, "Max_Annual_Net_Sales": None,
            "Broad_Sector": None, "Sector": None, "Broad_Industry": None, "Industry": None,
            **empty_quality,
        }
    annual_profit = result.get("annual_net_profit") or []
    annual_sales = result.get("annual_net_sales") or []

    # Quality flags (2026-10-01) -- only attempted when the balance-sheet/P&L-extra history
    # actually came back (a symbol with no usable page at all has nothing to compute from
    # anyway); one extra yfinance monthly fetch per symbol, for the valuation-ratio checks'
    # year-end prices -- never lets a price-fetch hiccup fail the whole row, just leaves the
    # 3 valuation checks as None (quality_flags.compute_all is already None-safe per-field).
    quality = dict(empty_quality)
    if result.get("balance_sheet") or result.get("pl_extra"):
        try:
            monthly = data_feed.get_monthly(symbol, period="10y")
        except Exception:
            monthly = None
        periods = (result.get("balance_sheet") or {}).get("equity_capital")
        periods = periods[0] if periods else []
        year_end_prices = _year_end_prices(monthly, periods)
        # 2026-10-02: a same-day attempt to fix PB_Current/PS_Current/PCF_Current's ~30-day-stale
        # price (using the last MONTHLY bar) by adding a separate get_daily() call per symbol was
        # REVERTED the same day -- confirmed live in production that roughly doubling the number
        # of per-symbol yfinance calls (~2,600 -> ~5,200) caused the full-universe job to hang for
        # 3+ hours and get killed by the workflow timeout, producing ZERO usable output for that
        # run. This matches a known, already-documented failure class in this codebase: yfinance's
        # underlying transport can abandon a native thread in a way its own ``timeout=`` parameter
        # doesn't reliably bound (see the V20 Render crash-loop this was fixed for previously) --
        # confirmed by two ~75-minute gaps between log lines in the killed run's logs. Accepting
        # the last monthly bar's staleness (~30 days worst case, ~1.7% observed) is a far smaller
        # risk than losing an entire batch run to an unbounded hang.
        current_price = (
            float(monthly["Close"].to_numpy()[-1])
            if monthly is not None and not monthly.empty and "Close" in monthly.columns else None
        )
        # NSE's own promoter-holding data (2026-10-02) -- the primary regulatory source, keyed by
        # the same NSE symbol, no mapping needed. Merged into `result` so quality_flags.compute_all
        # can prefer it over screener.in's shorter promoter-holding window; never lets an NSE
        # hiccup fail the row (the fetch is already None-safe).
        result["nse_promoter_holding"] = nse_sh.fetch_promoter_holding_history(symbol, session=nse_session)
        computed = qf.compute_all(result, year_end_prices, current_price)
        # computed's keys are snake_case (e.g. "book_value_cagr_10y"); _QUALITY_COLUMNS are the
        # CSV/CamelCase names (e.g. "Book_Value_CAGR_10Y") -- reuse _FUNDAMENTALS_DB_COLUMNS'
        # existing mapping between the two rather than a third naming convention.
        quality = {col: computed[_FUNDAMENTALS_DB_COLUMNS[col]] for col in _QUALITY_COLUMNS}

    return {
        "Symbol": symbol,
        "TTM_Net_Profit": result.get("ttm_net_profit"),
        "Max_Annual_Net_Profit": max(annual_profit) if annual_profit else None,
        "TTM_Net_Sales": result.get("ttm_net_sales"),
        "Max_Annual_Net_Sales": max(annual_sales) if annual_sales else None,
        "Broad_Sector": result.get("broad_sector"),
        "Sector": result.get("sector"),
        "Broad_Industry": result.get("broad_industry"),
        "Industry": result.get("industry"),
        **quality,
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
    nse_session = nse_sh.new_session()
    ok_count = 0
    fail_count = 0
    start = time.time()
    try:
        for i, symbol in enumerate(symbols, 1):
            row = fetch_one(symbol, session, args.retries, args.pause, nse_session=nse_session)
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
        nse_session.close()
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
