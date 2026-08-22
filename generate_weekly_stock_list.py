#!/usr/bin/env python
# coding: utf-8

"""
Weekly Stock List Generation Script
Generates dynamic stock list based on financial screening criteria
"""

import os
import sys
from datetime import datetime
from modules.stock_screener import StockScreener, add_moving_averages_to_stocks, add_nse_categories_to_stocks
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
STOCK_LIST_FILENAME = "Master_company_market_trend_analysis.csv"
FULL_UNIVERSE_FILENAME = "NSE_EQ_All_Stocks_Analysis.csv"
CATEGORIES_FILENAME = "nse_categories.csv"
OUTPUT_STOCK_LIST_PATH = os.path.join(REPO_BASE_PATH, STOCK_LIST_FILENAME)
OUTPUT_FULL_UNIVERSE_PATH = os.path.join(REPO_BASE_PATH, FULL_UNIVERSE_FILENAME)
OUTPUT_CATEGORIES_PATH = os.path.join(REPO_BASE_PATH, CATEGORIES_FILENAME)

# CSV column name -> Postgres column name (see generate_turtle_signals.py for why this stays
# explicit at the call site rather than a shared implicit convention).
_UNIVERSE_DB_COLUMNS = {
    "Symbol": "symbol", "Company Name": "company_name", "Sector": "sector", "Industry": "industry",
    "Market Cap": "market_cap", "Net Profit (Cr)": "net_profit_cr", "ROCE (%)": "roce_pct",
    "ROE (%)": "roe_pct", "Debt to Equity": "debt_to_equity",
    "Latest Quarter Profit (Cr)": "latest_quarter_profit_cr", "Last 3Q Profits (Cr)": "last_3q_profits_cr",
    "Public Holding (%)": "public_holding_pct", "Is Bank/Finance": "is_bank_finance", "Is PSU": "is_psu",
    "Passes Criteria": "passes_criteria", "Screening Date": "screening_date",
    "MA10": "ma10", "MA50": "ma50", "MA100": "ma100", "MA200": "ma200", "Current_Price": "current_price",
}
_TREND_ANALYSIS_DB_COLUMNS = {
    k: v for k, v in _UNIVERSE_DB_COLUMNS.items()
    if k not in ("Passes Criteria", "MA10", "MA50", "MA100", "MA200", "Current_Price")
}
_CATEGORIES_DB_COLUMNS = {"Symbol": "symbol", "NSE_Categories": "nse_categories"}
_CATEGORIES_FROM_DB = {"symbol": "Symbol", "nse_categories": "NSE_Categories"}


def _seed_categories_csv_from_postgres():
    """Write the current nse_categories table to OUTPUT_CATEGORIES_PATH before
    add_nse_categories_to_stocks() runs.

    refresh_nifty_membership() (modules/nse_category_fetcher.py) merges freshly-fetched Nifty
    50/100/200 membership into whatever's already at that path, specifically to preserve
    thematic tags (e.g. "NIFTY PHARMA") that aren't part of this run's fetch. Now that
    nse_categories.csv isn't committed to git, a fresh CI checkout has no local file to merge
    from -- without this, every run would start from an empty map and silently drop every
    thematic tag. Best-effort: if Postgres has no data yet (or is unreachable), leave whatever
    local file state exists, matching the CSV-era behaviour of "missing file -> start empty".
    """
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, "nse_categories")
        finally:
            conn.close()
        if not df.empty:
            df.rename(columns=_CATEGORIES_FROM_DB)[["Symbol", "NSE_Categories"]].to_csv(
                OUTPUT_CATEGORIES_PATH, index=False
            )
            print(f"DB: seeded {OUTPUT_CATEGORIES_PATH} with {len(df)} rows from nse_categories for merge")
    except Exception as exc:
        print(f"WARNING: could not seed nse_categories.csv from Postgres, merge will start empty: {exc}")


def _write_to_postgres(table: str, df: pd.DataFrame, rename_map: dict, conflict_columns: list):
    """Best-effort DB upsert alongside the CSV write -- CSV stays the source of truth until
    every table's read side is confirmed working (see migrations/20260820_market_data_tables.sql)."""
    try:
        conn = mdw.get_connection()
        try:
            n = mdw.upsert_dataframe(conn, table, df.rename(columns=rename_map), conflict_columns=conflict_columns)
            print(f"DB: {table} upserted {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write to {table} failed, CSV is still the source of truth for now: {exc}")

def generate_weekly_stock_list(output_path, full_universe_output_path):
    """Generate weekly screened stock list plus full analyzed NSE universe."""
    try:
        print("Starting comprehensive stock screening with enhancements...")
        screener = StockScreener()
        df = screener.screen_stocks()
        
        if not df.empty:
            # Load comprehensive data (all stocks, not just screened ones)
            print("Loading comprehensive stock data...")
            try:
                output_dir = os.path.join(REPO_BASE_PATH, 'output')
                csv_files = [f for f in os.listdir(output_dir) if f.startswith('comprehensive_stock_analysis_')]
                if csv_files:
                    latest_file = sorted(csv_files)[-1]
                    comprehensive_df = pd.read_csv(os.path.join(output_dir, latest_file))
                    print(f"Loaded {len(comprehensive_df)} stocks from comprehensive analysis")
                else:
                    comprehensive_df = df
            except Exception as e:
                print(f"Error loading comprehensive data: {e}")
                comprehensive_df = df
            
            # Add moving averages
            print("Adding moving averages to stocks...")
            comprehensive_df = add_moving_averages_to_stocks(comprehensive_df)
            
            # Add NSE categories
            print("Adding NSE category information...")
            _seed_categories_csv_from_postgres()
            comprehensive_df = add_nse_categories_to_stocks(comprehensive_df)
            
            # Save enhanced comprehensive data
            timestamp = datetime.now().strftime('%Y%m%d')
            enhanced_filename = f'comprehensive_stock_analysis_{timestamp}.csv'
            enhanced_filepath = os.path.join(output_dir, enhanced_filename)
            
            comprehensive_df.to_csv(enhanced_filepath, index=False)
            print(f"Enhanced comprehensive data saved to: {enhanced_filename}")
            
            # Save screened stocks for the V20 shortlist
            df.to_csv(output_path, index=False)
            print(f"Screened stock list saved to: {output_path}")
            _write_to_postgres("market_trend_analysis", df, _TREND_ANALYSIS_DB_COLUMNS, ["symbol"])

            # Save full analyzed universe for the screener UI
            comprehensive_df.to_csv(full_universe_output_path, index=False)
            print(f"Full stock universe saved to: {full_universe_output_path}")
            _write_to_postgres("nse_universe", comprehensive_df, _UNIVERSE_DB_COLUMNS, ["symbol"])

            # add_nse_categories_to_stocks() above already refreshed nse_categories.csv as a
            # side effect (modules/nse_category_fetcher.py) -- push that same file to Postgres too.
            if os.path.exists(OUTPUT_CATEGORIES_PATH):
                categories_df = pd.read_csv(OUTPUT_CATEGORIES_PATH)
                _write_to_postgres("nse_categories", categories_df, _CATEGORIES_DB_COLUMNS, ["symbol"])

            return True, len(df), enhanced_filename
        else:
            print("No stocks found meeting criteria")
            return False, 0, None
    except Exception as e:
        print(f"Error generating stock list: {e}")
        return False, 0, None
# --- Main Execution ---
if __name__ == "__main__":
    print(f"WEEKLY STOCK LIST GENERATION: Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Generate the stock list using screening criteria
    success, stock_count, comprehensive_file = generate_weekly_stock_list(
        OUTPUT_STOCK_LIST_PATH,
        OUTPUT_FULL_UNIVERSE_PATH,
    )

    if success:
        print(f"WEEKLY: Successfully generated stock list with {stock_count} stocks "
              "(written to Postgres above; CSVs are a local artifact only, not committed).")
    else:
        print("WEEKLY ERROR: Failed to generate stock list.")
        sys.exit(1)

    print(f"WEEKLY STOCK LIST GENERATION: Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sys.exit(0)
