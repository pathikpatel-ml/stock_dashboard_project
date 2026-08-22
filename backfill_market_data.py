#!/usr/bin/env python
"""
One-off backfill: push today's already-generated CSV files into Postgres, without re-running
the (expensive, live-network) generate_*.py scripts. Uses the exact same column-rename maps
and write helpers each generate_*.py script uses -- this is purely "get the DB caught up to
what the CSVs already have", not a new data path.

Safe to re-run (everything here is upsert/replace, matching each table's own write semantics).
"""
import os

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from database import market_data_writer as mdw

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))


def _upsert(conn, table, csv_path, rename_map, conflict_columns, extra_columns=None):
    path = os.path.join(REPO_BASE_PATH, csv_path)
    if not os.path.exists(path):
        print(f"SKIP {table}: {csv_path} not found")
        return
    df = pd.read_csv(path)
    df = df.rename(columns=rename_map)
    for col, value in (extra_columns or {}).items():
        df[col] = value
    n = mdw.upsert_dataframe(conn, table, df, conflict_columns=conflict_columns)
    print(f"OK   {table}: upserted {n} rows from {csv_path}")


def main():
    conn = mdw.get_connection()
    try:
        _upsert(conn, "turtle_fundamentals", "turtle_screener_fundamentals.csv", {
            "Symbol": "symbol", "TTM_Net_Profit": "ttm_net_profit",
            "Max_Annual_Net_Profit": "max_annual_net_profit", "TTM_Net_Sales": "ttm_net_sales",
            "Max_Annual_Net_Sales": "max_annual_net_sales",
        }, ["symbol"])

        _upsert(conn, "nse_universe", "NSE_EQ_All_Stocks_Analysis.csv", {
            "Symbol": "symbol", "Company Name": "company_name", "Sector": "sector", "Industry": "industry",
            "Market Cap": "market_cap", "Net Profit (Cr)": "net_profit_cr", "ROCE (%)": "roce_pct",
            "ROE (%)": "roe_pct", "Debt to Equity": "debt_to_equity",
            "Latest Quarter Profit (Cr)": "latest_quarter_profit_cr", "Last 3Q Profits (Cr)": "last_3q_profits_cr",
            "Public Holding (%)": "public_holding_pct", "Is Bank/Finance": "is_bank_finance", "Is PSU": "is_psu",
            "Passes Criteria": "passes_criteria", "Screening Date": "screening_date",
            "MA10": "ma10", "MA50": "ma50", "MA100": "ma100", "MA200": "ma200", "Current_Price": "current_price",
        }, ["symbol"])

        _upsert(conn, "market_trend_analysis", "Master_company_market_trend_analysis.csv", {
            "Symbol": "symbol", "Company Name": "company_name", "Sector": "sector", "Industry": "industry",
            "Market Cap": "market_cap", "Net Profit (Cr)": "net_profit_cr", "ROCE (%)": "roce_pct",
            "ROE (%)": "roe_pct", "Debt to Equity": "debt_to_equity",
            "Latest Quarter Profit (Cr)": "latest_quarter_profit_cr", "Last 3Q Profits (Cr)": "last_3q_profits_cr",
            "Public Holding (%)": "public_holding_pct", "Is Bank/Finance": "is_bank_finance", "Is PSU": "is_psu",
            "Screening Date": "screening_date",
        }, ["symbol"])

        _upsert(conn, "nse_categories", "nse_categories.csv",
                {"Symbol": "symbol", "NSE_Categories": "nse_categories"}, ["symbol"])

        _upsert(conn, "turtle_live_prices", "turtle_live_prices.csv",
                {"Symbol": "symbol", "Live_Price": "live_price", "Price_As_Of": "price_as_of"}, ["symbol"])

        _upsert(conn, "turtle_sector_pulse", "turtle_sector_pulse.csv",
                {"Sector": "sector", "ATH_Price_Flag": "ath_price_flag", "RS_vs_Nifty50": "rs_vs_nifty50"},
                ["sector"])

        signal_date = pd.Timestamp.now().strftime("%Y-%m-%d")
        signals_csv = f"turtle_signals_{pd.Timestamp.now().strftime('%Y%m%d')}.csv"
        _upsert(conn, "turtle_signals_latest", signals_csv, {
            "Symbol": "symbol", "Company": "company", "Sector": "sector", "Industry": "industry",
            "Current_Price": "current_price", "ATH_Price_Flag": "ath_price_flag",
            "TTM_Net_Profit": "ttm_net_profit", "ATH_Profit_Flag": "ath_profit_flag",
            "Above_MA212_Flag": "above_ma212_flag", "RS_Peer_Group": "rs_peer_group",
            "RS_vs_Sector": "rs_vs_sector", "RS_vs_Benchmark": "rs_vs_benchmark",
            "Outperformance_Flag": "outperformance_flag", "TTM_Net_Sales": "ttm_net_sales",
            "ATH_Sales": "ath_sales", "ATH_Sales_Flag": "ath_sales_flag", "Signal": "signal",
        }, ["symbol"], extra_columns={"signal_date": signal_date})

        v20_csv = f"stock_candle_signals_from_listing_{pd.Timestamp.now().strftime('%Y%m%d')}.csv"
        path = os.path.join(REPO_BASE_PATH, v20_csv)
        if os.path.exists(path):
            df = pd.read_csv(path).rename(columns={
                "Symbol": "symbol", "Buy_Date": "buy_date", "Buy_Price_Low": "buy_price_low",
                "Sell_Date": "sell_date", "Sell_Price_High": "sell_price_high",
                "Sequence_Gain_Percent": "sequence_gain_percent", "Days_in_Sequence": "days_in_sequence",
            })
            df["run_date"] = signal_date
            n = mdw.replace_table_contents(conn, "v20_signals_latest", df)
            print(f"OK   v20_signals_latest: replaced with {n} rows from {v20_csv}")
        else:
            print(f"SKIP v20_signals_latest: {v20_csv} not found")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
