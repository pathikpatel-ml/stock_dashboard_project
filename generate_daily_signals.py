#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
import time
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np
import sys
import subprocess # For running git commands

# --- Configuration ---
# Assuming this script is in the root of your Git repository
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
INPUT_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)
OUTPUT_SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"

# --- Candle Analysis Functions (Your existing core logic - UNCHANGED) ---
def fetch_historical_data_yf(symbol_nse):
    try:
        stock_ticker = yf.Ticker(symbol_nse)
        # Fetch a bit more data than strictly needed, yfinance can sometimes be inconsistent with exact "max"
        hist_data = stock_ticker.history(period="10y", interval="1d", auto_adjust=False, actions=True, timeout=20) # Increased timeout
        if hist_data.empty:
            # Try a shorter period if 10y fails, some new stocks might not have that much data
            hist_data = stock_ticker.history(period="5y", interval="1d", auto_adjust=False, actions=True, timeout=15)
            if hist_data.empty:
                 print(f"Warning: No data for {symbol_nse} even with shorter period.")
                 return pd.DataFrame()

        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns:
            print(f"Warning: 'Date' column missing for {symbol_nse}.")
            return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        required_ohlc = ['Open', 'High', 'Low', 'Close']
        if not all(col in hist_data.columns for col in required_ohlc):
            print(f"Warning: OHLC columns missing for {symbol_nse}.")
            return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=required_ohlc, inplace=True)
        return hist_data
    except Exception as e:
        print(f"Error fetching {symbol_nse}: {e}")
        return pd.DataFrame()

def analyze_stock_candles(base_symbol, hist_data_df):
    signals = []
    required_cols = ['Date', 'Open', 'Close', 'Low', 'High']
    if hist_data_df.empty or not all(col in hist_data_df.columns for col in required_cols): return signals
    df_full_history = hist_data_df.copy()
    for col in ['Open', 'Close', 'Low', 'High']: df_full_history[col] = pd.to_numeric(df_full_history[col], errors='coerce')
    df_full_history.dropna(subset=['Open', 'Close', 'Low', 'High'], inplace=True) # Ensure no NaNs after conversion
    if df_full_history.empty: return signals # Check if df became empty after dropna

    df_full_history['GreenCandle'] = df_full_history['Close'] > df_full_history['Open']
    # Ensure 'GreenCandle' column exists before diff and cumsum
    if 'GreenCandle' not in df_full_history.columns or df_full_history['GreenCandle'].empty:
        return signals # Not enough data to form blocks
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
        if gain_percentage < 20.0: continue

        is_triggered_in_future = False
        future_data = df_full_history[df_full_history['Date'] > sell_date_dt].copy()
        if not future_data.empty:
            future_buy_condition_met_date = None
            for _idx, future_row in future_data.iterrows():
                if future_buy_condition_met_date is None and future_row['Low'] <= buy_price_low:
                    future_buy_condition_met_date = future_row['Date']
                if future_buy_condition_met_date is not None and future_row['Date'] >= future_buy_condition_met_date:
                    if future_row['High'] >= sell_price_high:
                        is_triggered_in_future = True
                        break
        if is_triggered_in_future: continue
        signals.append({
            'Symbol': base_symbol,
            'Buy_Date': buy_date_dt.strftime('%Y-%m-%d'),
            'Buy_Price_Low': round(buy_price_low, 2),
            'Sell_Date': sell_date_dt.strftime('%Y-%m-%d'),
            'Sell_Price_High': round(sell_price_high, 2),
            'Sequence_Gain_Percent': round(gain_percentage, 2),
            'Days_in_Sequence': len(sequence_df)
        })
    return signals

def generate_and_save_candle_analysis_file(current_growth_file_path, output_candle_file_path):
    print(f"\n--- GENERATION: Starting Candle Analysis ---")
    print(f"GENERATION: Using input symbol list from: {current_growth_file_path}")
    if not os.path.exists(current_growth_file_path):
        print(f"GENERATION ERROR: Symbol list file '{current_growth_file_path}' NOT FOUND.")
        return False, 0
    try:
        growth_df = pd.read_csv(current_growth_file_path)
    except Exception as e:
        print(f"GENERATION ERROR: reading symbol list file '{current_growth_file_path}': {e}")
        return False, 0
    if 'Symbol' not in growth_df.columns:
        print(f"GENERATION ERROR: 'Symbol' column missing in '{current_growth_file_path}'.")
        return False, 0
    if growth_df.empty:
        print("GENERATION: Symbol list file is empty.")
        empty_df = pd.DataFrame(columns=['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence'])
        try:
            empty_df.to_csv(output_candle_file_path, index=False)
            print(f"GENERATION: Saved empty candle analysis file to '{output_candle_file_path}'.")
            return True, 0 # Success, 0 signals
        except Exception as e:
            print(f"GENERATION ERROR: saving empty candle signals file: {e}")
            return False, 0


    all_candle_signals = []
    symbols_for_analysis = growth_df["Symbol"].dropna().astype(str).unique()
    total_symbols = len(symbols_for_analysis)
    print(f"GENERATION: Analyzing candles for {total_symbols} unique symbols. This may take some time...")

    for i, symbol_short in enumerate(symbols_for_analysis):
        symbol_nse = f"{symbol_short.upper().strip()}.NS"
        progress_percent = ((i + 1) / total_symbols) * 100
        sys.stdout.write(f"\rGENERATION: Processing: [{i+1}/{total_symbols}] {symbol_short} ({progress_percent:.1f}%)")
        sys.stdout.flush()
        hist_data = fetch_historical_data_yf(symbol_nse)
        if not hist_data.empty:
            signals = analyze_stock_candles(symbol_short, hist_data)
            if signals:
                all_candle_signals.extend(signals)
        time.sleep(0.25) # Small delay, be respectful to yfinance API
    sys.stdout.write("\nGENERATION: Done processing symbols.\n")
    sys.stdout.flush()

    num_signals_generated = 0
    if all_candle_signals:
        signals_df_generated = pd.DataFrame(all_candle_signals).sort_values(by=['Symbol', 'Buy_Date']).reset_index(drop=True)
        num_signals_generated = len(signals_df_generated)
        try:
            signals_df_generated.to_csv(output_candle_file_path, index=False)
            print(f"GENERATION: Saved {num_signals_generated} candle signals to '{output_candle_file_path}'")
            return True, num_signals_generated
        except Exception as e:
            print(f"GENERATION ERROR: saving candle signals to '{output_candle_file_path}': {e}")
            return False, 0
    else:
        print("GENERATION: No candle signals generated.")
        empty_df = pd.DataFrame(columns=['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence'])
        try:
            empty_df.to_csv(output_candle_file_path, index=False)
            print(f"GENERATION: Saved empty candle analysis file to '{output_candle_file_path}'.")
            return True, 0 # Success in saving an empty file
        except Exception as e:
            print(f"GENERATION ERROR: saving empty candle signals file: {e}")
            return False, 0

# --- Git Helper Functions ---
def run_git_command(command_list, working_dir="."):
    """Runs a git command and returns True on success."""
    try:
        print(f"GIT CMD: Running '{' '.join(command_list)}' in '{working_dir}'")
        process = subprocess.Popen(command_list, cwd=working_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=120) # Increased timeout for git operations
        if process.returncode == 0:
            # print(f"GIT: Command '{' '.join(command_list)}' successful.") # Can be noisy
            if stdout.strip(): print(f"GIT STDOUT: {stdout.strip()}")
            return True
        else:
            print(f"GIT ERROR: Command '{' '.join(command_list)}' failed with code {process.returncode}.")
            if stdout.strip(): print(f"GIT STDOUT: {stdout.strip()}")
            if stderr.strip(): print(f"GIT STDERR: {stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"GIT TIMEOUT: Command '{' '.join(command_list)}' timed out.")
        return False
    except Exception as e:
        print(f"GIT EXCEPTION: running command '{' '.join(command_list)}': {e}")
        return False

def commit_and_push_to_github(new_file_to_add, commit_message):
    """Adds a file, commits, and pushes to GitHub."""
    print(f"\n--- GIT OPS: Starting Git Operations ---")

    # 1. Check for old signal files and remove them
    current_date_str = datetime.now().strftime("%Y%m%d")
    # Construct the full path for the new file to avoid accidentally removing it
    new_file_full_path = os.path.abspath(os.path.join(REPO_BASE_PATH, new_file_to_add))

    for item in os.listdir(REPO_BASE_PATH):
        if item.startswith("stock_candle_signals_from_listing_") and item.endswith(".csv"):
            item_full_path = os.path.abspath(os.path.join(REPO_BASE_PATH, item))
            # Ensure we don't try to remove the file we just created/are about to add
            if item_full_path != new_file_full_path:
                print(f"GIT OPS: Found old signals file: {item}. Attempting to remove from git and disk.")
                # Try git rm first, it's cleaner if the file is tracked
                if run_git_command(["git", "rm", "-f", item], working_dir=REPO_BASE_PATH): # -f to ignore if not tracked or modified
                     print(f"GIT OPS: Successfully 'git rm {item}'.")
                else:
                    # If git rm fails or file wasn't tracked, try to just delete from disk
                    try:
                        if os.path.exists(item_full_path): # Check again before deleting
                            os.remove(item_full_path)
                            print(f"GIT OPS: Deleted '{item}' from disk directly.")
                    except Exception as e:
                        print(f"GIT OPS WARNING: Could not delete old file '{item}' from disk: {e}")

    # 2. Add the new file
    if not run_git_command(["git", "add", new_file_to_add], working_dir=REPO_BASE_PATH):
        print(f"GIT OPS ERROR: Failed to 'git add {new_file_to_add}'. Aborting push.")
        return False
    print(f"GIT OPS: Successfully added '{new_file_to_add}' to staging.")

    # 3. Commit
    # Check git status before committing to see if there are actual changes
    status_check_process = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO_BASE_PATH)
    if not status_check_process.stdout.strip():
        print("GIT OPS: No changes to commit (new file might be identical to an existing one or add failed silently). Skipping push.")
        return True # Nothing to do, so consider it a success for the script's flow

    if not run_git_command(["git", "commit", "-m", commit_message], working_dir=REPO_BASE_PATH):
        print(f"GIT OPS ERROR: Failed to 'git commit'. Aborting push.")
        return False
    print(f"GIT OPS: Successfully committed changes with message: '{commit_message}'.")

    # 4. Push
    if not run_git_command(["git", "push"], working_dir=REPO_BASE_PATH):
        print(f"GIT OPS ERROR: Failed to 'git push'.")
        return False
    print(f"GIT OPS: Successfully pushed changes to remote repository.")
    return True

# --- Main Execution ---
if __name__ == "__main__":
    print(f"DATA GENERATION SCRIPT: Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Define today's output file path (relative to script location)
    today_date_str = datetime.now().strftime("%Y%m%d")
    output_signals_filename_relative = OUTPUT_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date_str)
    output_signals_file_fullpath = os.path.join(REPO_BASE_PATH, output_signals_filename_relative)

    # Generate the signals CSV file
    success, num_signals = generate_and_save_candle_analysis_file(INPUT_GROWTH_DF_PATH, output_signals_file_fullpath)

    if success:
        print(f"DATA GENERATION SCRIPT: Candle analysis file processing finished for: {output_signals_filename_relative}")

        # Commit and push the new file to GitHub (using relative path for git add)
        commit_msg = f"Automated daily signals: {num_signals} signals for {today_date_str}"
        if os.path.exists(output_signals_file_fullpath):
            if commit_and_push_to_github(output_signals_filename_relative, commit_msg):
                print("DATA GENERATION SCRIPT: Successfully committed and pushed to GitHub.")
            else:
                print("DATA GENERATION SCRIPT ERROR: Failed to commit and push to GitHub.")
                sys.exit(1) # Indicate failure
        else:
             print(f"DATA GENERATION SCRIPT WARNING: Output file '{output_signals_filename_relative}' not found after generation. Skipping Git commit.")
             # If file generation was 'successful' but file doesn't exist, it's an issue
             sys.exit(1)
    else:
        print("DATA GENERATION SCRIPT ERROR: Candle analysis file generation failed.")
        sys.exit(1) # Indicate failure

    print(f"DATA GENERATION SCRIPT: Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sys.exit(0) # Indicate success
