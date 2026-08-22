#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
import time
import yfinance as yf
from datetime import datetime, timedelta, date
import numpy as np
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# CSV column name -> Postgres column name.
_V20_DB_COLUMNS = {
    "Symbol": "symbol", "Buy_Date": "buy_date", "Buy_Price_Low": "buy_price_low",
    "Sell_Date": "sell_date", "Sell_Price_High": "sell_price_high",
    "Sequence_Gain_Percent": "sequence_gain_percent", "Days_in_Sequence": "days_in_sequence",
}


def _write_v20_to_postgres(df: pd.DataFrame):
    """REPLACE (not upsert) v20_signals_latest with today's freshly-detected sequences -- a
    sequence that no longer qualifies must disappear, not sit stale (see
    migrations/20260820_market_data_tables.sql's comment on this table). Best-effort: CSV
    stays the source of truth until the read side is confirmed working end to end.
    """
    try:
        db_df = df.rename(columns=_V20_DB_COLUMNS).copy()
        db_df["run_date"] = datetime.now().strftime("%Y-%m-%d")
        conn = mdw.get_connection()
        try:
            n = mdw.replace_table_contents(conn, "v20_signals_latest", db_df)
            print(f"DB: v20_signals_latest replaced with {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed, CSV is still the source of truth for now: {exc}")

# For V20 Strategy - Using dynamically generated stock list
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv" # Dynamic stock list from weekly screening
INPUT_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)
OUTPUT_SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"

KNOWN_PSU_SYMBOLS = {
    'BHEL', 'BPCL', 'COALINDIA', 'CONCOR', 'GAIL', 'HAL', 'HPCL', 'HUDCO', 'IOC',
    'IRCON', 'IRCTC', 'IRFC', 'IREDA', 'LICI', 'NBCC', 'NLCINDIA', 'NMDC', 'NTPC',
    'OIL', 'ONGC', 'PFC', 'POWERGRID', 'RAILTEL', 'RCF', 'RECLTD', 'SAIL', 'SBI', 'SBIN',
    'SBICARD', 'SBILIFE', 'SCI', 'UNIONBANK'
}

# --- Candle Analysis Functions (Your V20 Strategy - UNCHANGED) ---
# This section should be exactly as you had it for your "v20 strategy"
def fetch_historical_data_yf_candle(symbol_nse): # Renamed to avoid conflict if MA needs different params
    """Fetches historical data specifically for candle analysis (longer period)."""
    try:
        stock_ticker = yf.Ticker(symbol_nse)
        # Original V20 fetch period was 10y, then 5y
        hist_data = stock_ticker.history(period="10y", interval="1d", auto_adjust=False, actions=True, timeout=20)
        if hist_data.empty:
            hist_data = stock_ticker.history(period="5y", interval="1d", auto_adjust=False, actions=True, timeout=15)
            if hist_data.empty:
                 return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        required_ohlc = ['Open', 'High', 'Low', 'Close']
        if not all(col in hist_data.columns for col in required_ohlc): return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=required_ohlc, inplace=True)
        hist_data = hist_data.sort_values(by='Date').reset_index(drop=True)
        return hist_data
    except Exception as e:
        # print(f"Error fetching {symbol_nse} for candle: {e}")
        return pd.DataFrame()

def analyze_stock_candles(base_symbol, hist_data_df): # Your V20 analysis logic
    signals = []
    required_cols = ['Date', 'Open', 'Close', 'Low', 'High']
    if hist_data_df.empty or not all(col in hist_data_df.columns for col in required_cols): return signals
    df_full_history = hist_data_df.copy()
    for col in ['Open', 'Close', 'Low', 'High']: df_full_history[col] = pd.to_numeric(df_full_history[col], errors='coerce')
    df_full_history.dropna(subset=['Open', 'Close', 'Low', 'High'], inplace=True)
    if df_full_history.empty: return signals

    df_full_history['GreenCandle'] = df_full_history['Close'] > df_full_history['Open']
    if 'GreenCandle' not in df_full_history.columns or df_full_history['GreenCandle'].empty: return signals
    df_full_history['Block'] = (df_full_history['GreenCandle'].diff() != 0).cumsum()
    green_sequences_grouped = df_full_history[df_full_history['GreenCandle']].groupby('Block')
    if green_sequences_grouped.ngroups == 0: return signals

    for _block_id, sequence_df in green_sequences_grouped:
        if len(sequence_df) == 0: continue
        buy_date_dt = sequence_df['Date'].iloc[0]
        buy_price_low = sequence_df['Low'].iloc[0]
        sell_date_dt = sequence_df['Date'].iloc[-1]
        sell_price_high = sequence_df['High'].iloc[-1]
        if any(pd.isna(val) for val in [buy_price_low, sell_price_high]) or buy_price_low == 0: continue
        gain_percentage = ((sell_price_high - buy_price_low) / buy_price_low) * 100
        if gain_percentage < 20.0: continue # Your V20 specific filter
        is_triggered_in_future = False # Your V20 specific future check
        future_data = df_full_history[df_full_history['Date'] > sell_date_dt].copy()
        if not future_data.empty:
            future_buy_condition_met_date = None
            for _idx, future_row in future_data.iterrows():
                if future_buy_condition_met_date is None and future_row['Low'] <= buy_price_low:
                    future_buy_condition_met_date = future_row['Date']
                if future_buy_condition_met_date is not None and future_row['Date'] >= future_buy_condition_met_date:
                    if future_row['High'] >= sell_price_high:
                        is_triggered_in_future = True; break
        if is_triggered_in_future: continue
        signals.append({
            'Symbol': base_symbol, 'Buy_Date': buy_date_dt.strftime('%Y-%m-%d'),
            'Buy_Price_Low': round(buy_price_low, 2), 'Sell_Date': sell_date_dt.strftime('%Y-%m-%d'),
            'Sell_Price_High': round(sell_price_high, 2), 'Sequence_Gain_Percent': round(gain_percentage, 2),
            'Days_in_Sequence': len(sequence_df)
        })
    return signals

# Postgres column name -> CSV column name, reverse of generate_weekly_stock_list.py's
# _TREND_ANALYSIS_DB_COLUMNS. market_trend_analysis is produced by a separate, earlier-running
# weekly workflow -- Postgres is the real cross-workflow hand-off now that its CSV isn't
# committed to git; the local file read is just a local-dev fallback.
_MARKET_TREND_FROM_DB = {"symbol": "Symbol", "is_psu": "Is PSU", "public_holding_pct": "Public Holding (%)"}


def _load_growth_df(current_growth_file_path):
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, "market_trend_analysis")
        finally:
            conn.close()
        if not df.empty:
            return df.rename(columns=_MARKET_TREND_FROM_DB)
    except Exception as exc:
        print(f"V20 WARNING: Postgres read of market_trend_analysis failed, falling back to local CSV: {exc}")

    if not os.path.exists(current_growth_file_path):
        return None
    return pd.read_csv(current_growth_file_path)


def generate_and_save_candle_analysis_file(current_growth_file_path, output_candle_file_path): # V20 main generation
    print(f"\n--- GENERATION: Starting V20 Candle Analysis (Enhanced with Dynamic Stock List) ---")
    try:
        growth_df = _load_growth_df(current_growth_file_path)
    except Exception as e: print(f"V20 ERROR: reading dynamic stock list '{current_growth_file_path}': {e}"); return False, 0
    if growth_df is None:
        print(f"V20 ERROR: Dynamic stock list not found in Postgres (market_trend_analysis) or at '{current_growth_file_path}'.")
        print("V20 ERROR: Please ensure weekly stock screening has run successfully.")
        return False, 0
    if 'Symbol' not in growth_df.columns: print(f"V20 ERROR: 'Symbol' column missing in dynamic stock list."); return False, 0
    if growth_df.empty: print("V20: Dynamic stock list is empty.");

    all_candle_signals = []
    symbols_for_analysis = get_v20_eligible_symbols(growth_df)
    total_symbols = len(symbols_for_analysis)
    print(f"V20: Analyzing {total_symbols} dynamically screened symbols for V20 strategy...")

    for i, symbol_short in enumerate(symbols_for_analysis):
        symbol_nse = f"{symbol_short.upper().strip()}.NS"
        sys.stdout.write(f"\rV20: [{i+1}/{total_symbols}] {symbol_short} ({( (i + 1) / total_symbols) * 100:.1f}%)")
        sys.stdout.flush()
        hist_data = fetch_historical_data_yf_candle(symbol_nse) # Use candle-specific fetch
        if not hist_data.empty:
            signals = analyze_stock_candles(symbol_short, hist_data) # V20 analysis
            if signals: all_candle_signals.extend(signals)
        time.sleep(0.1)
    sys.stdout.write("\nV20: Done processing dynamically screened symbols.\n"); sys.stdout.flush()

    num_signals_generated = 0
    output_df_columns = ['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence']
    if all_candle_signals:
        signals_df_generated = pd.DataFrame(all_candle_signals, columns=output_df_columns).sort_values(by=['Symbol', 'Buy_Date']).reset_index(drop=True)
        num_signals_generated = len(signals_df_generated)
        try:
            signals_df_generated.to_csv(output_candle_file_path, index=False)
            print(f"V20: Saved {num_signals_generated} signals to '{output_candle_file_path}'")
            _write_v20_to_postgres(signals_df_generated)
            return True, num_signals_generated
        except Exception as e: print(f"V20 ERROR: saving signals: {e}"); return False, 0
    else:
        print("V20: No signals generated from dynamically screened stocks.")
        try:
            pd.DataFrame(columns=output_df_columns).to_csv(output_candle_file_path, index=False)
            print(f"V20: Saved empty file to '{output_candle_file_path}'.")
            _write_v20_to_postgres(pd.DataFrame(columns=output_df_columns))
            return True, 0
        except Exception as e: print(f"V20 ERROR: saving empty signals file: {e}"); return False, 0


def _truthy_flag(value):
    if isinstance(value, str):
        return value.strip().lower() in ['true', 'yes', '1', 'y']
    if isinstance(value, (int, float)):
        return bool(value)
    return bool(value)


def get_v20_eligible_symbols(growth_df):
    if growth_df.empty or 'Symbol' not in growth_df.columns:
        return []

    df = growth_df.copy()
    df['Symbol'] = df['Symbol'].astype(str).str.upper().str.strip()

    if 'Is PSU' in df.columns:
        df = df[~df['Is PSU'].apply(_truthy_flag)]

    public_holding_columns = ['Public_Holding_Percent', 'Public Holding (%)']
    public_holding_column = next((col for col in public_holding_columns if col in df.columns), None)
    if public_holding_column:
        df[public_holding_column] = pd.to_numeric(df[public_holding_column], errors='coerce')
        df = df[df[public_holding_column] < 30]

    df = df[~df['Symbol'].isin(KNOWN_PSU_SYMBOLS)]
    return df['Symbol'].dropna().unique().tolist()

# --- Helper function for PSU type (Shared) ---
def get_company_type(psu_value):
    is_psu = False
    if isinstance(psu_value, str): is_psu = psu_value.strip().lower() in ['true', 'yes', '1', 'y']
    elif isinstance(psu_value, (int, float)): is_psu = bool(psu_value)
    elif isinstance(psu_value, bool): is_psu = psu_value
    return "PSU" if is_psu else "Non-PSU"

def get_v40_type(v40_value):
    """
    Helper to determine type from the 'V40' column.
    Returns 'V40' if TRUE, 'V40Next' if FALSE.
    """
    is_v40 = False
    if isinstance(v40_value, str):
        # Handles cases like "TRUE", "true", "True", "yes", "1", "y"
        is_v40 = v40_value.strip().lower() in ['true', 'yes', '1', 'y']
    elif isinstance(v40_value, (int, float)):
        # Handles 1 or 1.0 as TRUE, 0 or 0.0 as FALSE
        is_v40 = bool(v40_value)
    elif isinstance(v40_value, bool):
        # Handles native boolean True/False
        is_v40 = v40_value
        
    return "V40" if is_v40 else "V40Next"
# --- END: MODIFIED HELPER FUNCTION ---

# --- MA components removed - V20 strategy only ---



# --- Main Execution ---
if __name__ == "__main__":
    print(f"DAILY DATA GENERATION SCRIPT: Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    today_date_str = datetime.now().strftime("%Y%m%d")
    
    files_generated_for_commit = []
    overall_success = True
    num_candle_signals = -1 

    # --- Generate Candle Signals File (V20 Strategy) ---
    output_candle_signals_filename_relative = OUTPUT_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date_str)
    output_candle_signals_file_fullpath = os.path.join(REPO_BASE_PATH, output_candle_signals_filename_relative)
    success_candle_signals, num_candle_signals = generate_and_save_candle_analysis_file(INPUT_GROWTH_DF_PATH, output_candle_signals_file_fullpath)
    if success_candle_signals:
        print(f"SCRIPT: V20 candle analysis processing finished: {output_candle_signals_filename_relative} ({num_candle_signals} signals from dynamic stock list)")
        if os.path.exists(output_candle_signals_file_fullpath):
             files_generated_for_commit.append(output_candle_signals_filename_relative)
    else:
        print("SCRIPT ERROR: V20 candle analysis file generation failed.")
        overall_success = False

    # V20 signals now live in Postgres (v20_signals_latest, written above during
    # generate_and_save_candle_analysis_file). The CSV is still written to disk as a
    # local/debug artifact but is no longer committed back to the repo.
    if files_generated_for_commit:
        print(f"SCRIPT: Signals written locally to {files_generated_for_commit} (not committed to git).")
    elif overall_success:
        print("SCRIPT: No new data files were generated, but script ran without generation errors.")
    else:
        print("SCRIPT: Generation errors occurred; no files produced.")

    print(f"DAILY DATA GENERATION SCRIPT: Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if overall_success and files_generated_for_commit:
        sys.exit(0)
    elif overall_success and not files_generated_for_commit:
        print("SCRIPT NOTE: Process completed, but no new files were generated or staged for commit.")
        sys.exit(0)
    else:
        sys.exit(1)
