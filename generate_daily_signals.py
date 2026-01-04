#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
import time
import yfinance as yf
from datetime import datetime, timedelta, date
import numpy as np
import sys
import subprocess

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# For V20 Strategy - Using dynamically generated stock list
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv" # Dynamic stock list from weekly screening
INPUT_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)
OUTPUT_SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"

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

def generate_and_save_candle_analysis_file(current_growth_file_path, output_candle_file_path): # V20 main generation
    print(f"\n--- GENERATION: Starting V20 Candle Analysis (Enhanced with Dynamic Stock List) ---")
    if not os.path.exists(current_growth_file_path): 
        print(f"V20 ERROR: Dynamic stock list '{current_growth_file_path}' NOT FOUND.")
        print("V20 ERROR: Please ensure weekly stock screening has run successfully.")
        return False, 0
    try: growth_df = pd.read_csv(current_growth_file_path)
    except Exception as e: print(f"V20 ERROR: reading dynamic stock list '{current_growth_file_path}': {e}"); return False, 0
    if 'Symbol' not in growth_df.columns: print(f"V20 ERROR: 'Symbol' column missing in '{current_growth_file_path}'."); return False, 0
    if growth_df.empty: print("V20: Dynamic stock list is empty.");

    all_candle_signals = []
    symbols_for_analysis = growth_df["Symbol"].dropna().astype(str).unique()
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
        try: signals_df_generated.to_csv(output_candle_file_path, index=False); print(f"V20: Saved {num_signals_generated} signals to '{output_candle_file_path}'"); return True, num_signals_generated
        except Exception as e: print(f"V20 ERROR: saving signals: {e}"); return False, 0
    else:
        print("V20: No signals generated from dynamically screened stocks.")
        try: pd.DataFrame(columns=output_df_columns).to_csv(output_candle_file_path, index=False); print(f"V20: Saved empty file to '{output_candle_file_path}'."); return True, 0
        except Exception as e: print(f"V20 ERROR: saving empty signals file: {e}"); return False, 0

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



# --- Git Helper Functions (UNCHANGED from your provided code) ---
def run_git_command(command_list, working_dir="."):
    try:
        process = subprocess.Popen(command_list, cwd=working_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=120)
        if process.returncode == 0:
            if stdout.strip(): print(f"GIT STDOUT: {stdout.strip()}")
            return True
        else:
            print(f"GIT ERROR: Command '{' '.join(command_list)}' failed with code {process.returncode}.")
            if stdout.strip(): print(f"GIT STDOUT: {stdout.strip()}")
            if stderr.strip(): print(f"GIT STDERR: {stderr.strip()}")
            return False
    except subprocess.TimeoutExpired: print(f"GIT TIMEOUT: Command '{' '.join(command_list)}' timed out."); return False
    except Exception as e: print(f"GIT EXCEPTION: running command '{' '.join(command_list)}': {e}"); return False

def commit_and_push_files_to_github(files_to_add, commit_message):
    print(f"\n--- GIT OPS: Starting Git Operations for {len(files_to_add)} file(s) ---")
    today_date_str = datetime.now().strftime("%Y%m%d")
    new_files_full_paths = [os.path.abspath(os.path.join(REPO_BASE_PATH, f)) for f in files_to_add]

    for item in os.listdir(REPO_BASE_PATH):
        # Remove old candle and old ATH signal files
        if (item.startswith("stock_candle_signals_from_listing_") or \
            item.startswith("ath_triggers_data_")) and item.endswith(".csv"):
            item_full_path = os.path.abspath(os.path.join(REPO_BASE_PATH, item))
            if item_full_path not in new_files_full_paths:
                print(f"GIT OPS: Found old generated file: {item}. Attempting to remove.")
                if run_git_command(["git", "rm", "-f", item], working_dir=REPO_BASE_PATH):
                     print(f"GIT OPS: Successfully 'git rm {item}'.")
                else:
                    try:
                        if os.path.exists(item_full_path): os.remove(item_full_path); print(f"GIT OPS: Deleted '{item}' from disk.")
                    except Exception as e: print(f"GIT OPS WARNING: Could not delete old file '{item}' from disk: {e}")
    
    added_successfully = True
    for file_to_add in files_to_add:
        if not os.path.exists(os.path.join(REPO_BASE_PATH, file_to_add)):
            print(f"GIT OPS WARNING: File '{file_to_add}' not found. Skipping add.")
            continue
        if not run_git_command(["git", "add", file_to_add], working_dir=REPO_BASE_PATH):
            print(f"GIT OPS ERROR: Failed to 'git add {file_to_add}'.")
            added_successfully = False
        else:
            print(f"GIT OPS: Successfully added '{file_to_add}' to staging.")
    
    status_check_process = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO_BASE_PATH)
    if not status_check_process.stdout.strip():
        print("GIT OPS: No changes staged for commit. Skipping commit and push.")
        return True 

    if not added_successfully and not status_check_process.stdout.strip():
        print("GIT OPS: No new files were added or found. Aborting commit.")
        return True 

    if not run_git_command(["git", "commit", "-m", commit_message], working_dir=REPO_BASE_PATH):
        print(f"GIT OPS ERROR: Failed to 'git commit'. Aborting push.")
        return False
    print(f"GIT OPS: Successfully committed changes with message: '{commit_message}'.")

    if not run_git_command(["git", "push"], working_dir=REPO_BASE_PATH):
        print(f"GIT OPS ERROR: Failed to 'git push'.")
        return False
    print(f"GIT OPS: Successfully pushed changes to remote repository.")
    return True

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

    # --- Commit and Push if any files were successfully generated ---
    if files_generated_for_commit:
        commit_msg = f"Automated V20 signals for {today_date_str} ({num_candle_signals} signals from dynamic stock screening)"

        if commit_and_push_files_to_github(files_generated_for_commit, commit_msg):
            print("SCRIPT: Successfully committed and pushed to GitHub.")
        else:
            print("SCRIPT ERROR: Failed to commit and push to GitHub.")
            overall_success = False
    elif overall_success:
        print("SCRIPT: No new data files were generated or found to commit, but script ran without generation errors.")
    else:
        print("SCRIPT: No files to commit due to generation errors.")

    print(f"DAILY DATA GENERATION SCRIPT: Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if overall_success and files_generated_for_commit:
        sys.exit(0)
    elif overall_success and not files_generated_for_commit:
        print("SCRIPT NOTE: Process completed, but no new files were generated or staged for commit.")
        sys.exit(0)
    else:
        sys.exit(1)
