#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
import time
import yfinance as yf
from datetime import datetime, timedelta, date # Added date
import numpy as np
import sys
import subprocess

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))

# For Candle Signals
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
INPUT_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)
OUTPUT_SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"

# For ATH Triggers
PROFIT_COMPANIES_FILE_NAME = "Master_5000_profit_companies.csv" # Your profit companies list
INPUT_PROFIT_DF_PATH = os.path.join(REPO_BASE_PATH, PROFIT_COMPANIES_FILE_NAME)
OUTPUT_ATH_TRIGGERS_FILENAME_TEMPLATE = "ath_triggers_data_{date_str}.csv" # New output file

# --- Candle Analysis Functions (fetch_historical_data_yf, analyze_stock_candles) ---
# ... (Your existing functions - UNCHANGED) ...
def fetch_historical_data_yf(symbol_nse):
    try:
        stock_ticker = yf.Ticker(symbol_nse)
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
        return hist_data
    except Exception as e:
        # print(f"Error fetching {symbol_nse} for candle: {e}") # Can be verbose
        return pd.DataFrame()

def analyze_stock_candles(base_symbol, hist_data_df):
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
                        is_triggered_in_future = True; break
        if is_triggered_in_future: continue
        signals.append({
            'Symbol': base_symbol, 'Buy_Date': buy_date_dt.strftime('%Y-%m-%d'),
            'Buy_Price_Low': round(buy_price_low, 2), 'Sell_Date': sell_date_dt.strftime('%Y-%m-%d'),
            'Sell_Price_High': round(sell_price_high, 2), 'Sequence_Gain_Percent': round(gain_percentage, 2),
            'Days_in_Sequence': len(sequence_df)
        })
    return signals


def generate_and_save_candle_analysis_file(current_growth_file_path, output_candle_file_path):
    # ... (Your existing function - UNCHANGED) ...
    print(f"\n--- GENERATION: Starting Candle Analysis ---")
    if not os.path.exists(current_growth_file_path): print(f"Candle ERROR: Symbol list '{current_growth_file_path}' NOT FOUND."); return False, 0
    try: growth_df = pd.read_csv(current_growth_file_path)
    except Exception as e: print(f"Candle ERROR: reading list '{current_growth_file_path}': {e}"); return False, 0
    if 'Symbol' not in growth_df.columns: print(f"Candle ERROR: 'Symbol' column missing in '{current_growth_file_path}'."); return False, 0
    if growth_df.empty: print("Candle: Symbol list empty."); # Save empty file logic below
    
    all_candle_signals = []
    symbols_for_analysis = growth_df["Symbol"].dropna().astype(str).unique()
    total_symbols = len(symbols_for_analysis)
    print(f"Candle: Analyzing {total_symbols} symbols...")

    for i, symbol_short in enumerate(symbols_for_analysis):
        symbol_nse = f"{symbol_short.upper().strip()}.NS"
        sys.stdout.write(f"\rCandle: [{i+1}/{total_symbols}] {symbol_short} ({( (i + 1) / total_symbols) * 100:.1f}%)")
        sys.stdout.flush()
        hist_data = fetch_historical_data_yf(symbol_nse) # Uses the existing fetch function
        if not hist_data.empty:
            signals = analyze_stock_candles(symbol_short, hist_data)
            if signals: all_candle_signals.extend(signals)
        time.sleep(0.1) # Be respectful to yfinance
    sys.stdout.write("\nCandle: Done processing symbols.\n"); sys.stdout.flush()

    num_signals_generated = 0
    output_df_columns = ['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence']
    if all_candle_signals:
        signals_df_generated = pd.DataFrame(all_candle_signals, columns=output_df_columns).sort_values(by=['Symbol', 'Buy_Date']).reset_index(drop=True)
        num_signals_generated = len(signals_df_generated)
        try: signals_df_generated.to_csv(output_candle_file_path, index=False); print(f"Candle: Saved {num_signals_generated} signals to '{output_candle_file_path}'"); return True, num_signals_generated
        except Exception as e: print(f"Candle ERROR: saving signals: {e}"); return False, 0
    else: # Save empty file if no signals
        print("Candle: No signals generated.")
        try: pd.DataFrame(columns=output_df_columns).to_csv(output_candle_file_path, index=False); print(f"Candle: Saved empty file to '{output_candle_file_path}'."); return True, 0
        except Exception as e: print(f"Candle ERROR: saving empty signals file: {e}"); return False, 0


# --- Helper function for PSU type (ensure this is defined or adapted in your script) ---
def get_company_type(psu_value):
    """Helper to determine PSU type from CSV value."""
    is_psu = False
    if isinstance(psu_value, str): is_psu = psu_value.strip().lower() in ['true', 'yes', '1', 'y']
    elif isinstance(psu_value, (int, float)): is_psu = bool(psu_value)
    elif isinstance(psu_value, bool): is_psu = psu_value
    return "PSU" if is_psu else "Non-PSU"

# --- REVISED: ATH Triggers Generation Function ---
def generate_and_save_ath_triggers_file(profit_companies_file_path, output_ath_file_path):
    print(f"\n--- GENERATION: Starting ATH Triggers Analysis ---")
    print(f"ATH: Using input profit company list from: {profit_companies_file_path}")
    if not os.path.exists(profit_companies_file_path):
        print(f"ATH ERROR: Profit company list file '{profit_companies_file_path}' NOT FOUND.")
        return False, 0
    try:
        profit_df = pd.read_csv(profit_companies_file_path)
    except Exception as e:
        print(f"ATH ERROR: reading profit company list file '{profit_companies_file_path}': {e}")
        return False, 0

    # Define the columns we expect and will output, including MarketCap
    final_output_ath_columns = [
        'Symbol', 'Company Name', 'Type', 'MarketCap',
        'All-Time High (ATH)', 'Current Market Price (CMP)',
        'Buy Trigger Price', 'Sell Trigger Price',
        'CMP Proximity to Buy (%)', 'ClosenessAbs (%)'
    ]

    # Check for essential input columns (Symbol, Company Name, PSU). MarketCap will be handled.
    essential_input_cols = ['Symbol', 'Company Name', 'PSU']
    for col in essential_input_cols:
        if col not in profit_df.columns:
            print(f"ATH ERROR: Essential input column '{col}' missing in '{profit_companies_file_path}'. Cannot proceed.")
            return False, 0
            
    # Handle MarketCap specifically: if not present in input, add it as NaN
    if 'MarketCap' not in profit_df.columns:
        print(f"ATH WARNING: 'MarketCap' column missing in input file '{profit_companies_file_path}'. MarketCap in output will be NaN.")
        profit_df['MarketCap'] = np.nan
            
    if profit_df.empty:
        print("ATH: Profit company list file is empty.")
        try: 
            pd.DataFrame(columns=final_output_ath_columns).to_csv(output_ath_file_path, index=False)
            print(f"ATH: Saved empty ATH triggers file to '{output_ath_file_path}'.")
            return True, 0
        except Exception as e: 
            print(f"ATH ERROR: saving empty ATH triggers file: {e}")
            return False, 0

    all_ath_triggers = []
    profit_df['Symbol'] = profit_df['Symbol'].astype(str).str.strip().str.upper()
    symbols_for_ath = profit_df["Symbol"].unique()
    total_symbols_ath = len(symbols_for_ath)
    
    if total_symbols_ath == 0:
        print("ATH: No symbols found in the profit company list after cleaning.")
        try: 
            pd.DataFrame(columns=final_output_ath_columns).to_csv(output_ath_file_path, index=False)
            print(f"ATH: Saved empty ATH triggers file to '{output_ath_file_path}'.")
            return True, 0
        except Exception as e: 
            print(f"ATH ERROR: saving empty ATH triggers file: {e}")
            return False, 0

    print(f"ATH: Analyzing ATH triggers for {total_symbols_ath} unique profit companies. This may take some time...")
    symbol_data_map = {row['Symbol']: row for _index, row in profit_df.drop_duplicates(subset=['Symbol']).iterrows()}
    processed_ath_count = 0
    chunk_size_ath = 20 
    
    for i in range(0, total_symbols_ath, chunk_size_ath):
        chunk = symbols_for_ath[i:i + chunk_size_ath]
        for symbol_short in chunk:
            symbol_nse = f"{symbol_short}.NS"
            ath, cmp = np.nan, np.nan 
            try:
                stock_ticker_ath = yf.Ticker(symbol_nse)
                hist_max = stock_ticker_ath.history(period="max", interval="1d", auto_adjust=False, actions=False, timeout=15)
                if not hist_max.empty and 'Close' in hist_max.columns:
                    close_series_ath = hist_max['Close'].dropna() 
                    if not close_series_ath.empty:
                        ath = close_series_ath.max()
                        if isinstance(ath, pd.Series): ath = ath.iloc[0] if not ath.empty else np.nan
                cmp_data = yf.download(tickers=symbol_nse, period="5d", interval="1d", progress=False, auto_adjust=False, timeout=10)
                if not cmp_data.empty and 'Close' in cmp_data.columns:
                    close_series_cmp = cmp_data['Close'].dropna() 
                    if not close_series_cmp.empty:
                        cmp = close_series_cmp.iloc[-1]
                        if isinstance(cmp, pd.Series): cmp = cmp.iloc[0] if not cmp.empty else np.nan
                time.sleep(0.15)
            except Exception: pass
            processed_ath_count += 1
            ath_str = f"{ath:.2f}" if pd.notna(ath) else "N/A"; cmp_str = f"{cmp:.2f}" if pd.notna(cmp) else "N/A"
            sys.stdout.write(f"\rATH: [{processed_ath_count}/{total_symbols_ath}] {symbol_short} (ATH: {ath_str}, CMP: {cmp_str})      ")
            sys.stdout.flush()

            if pd.notna(ath) and pd.notna(cmp):
                original_row_data = symbol_data_map.get(symbol_short)
                if original_row_data is not None:
                    company_name = original_row_data.get('Company Name', "N/A")
                    psu_value = original_row_data.get('PSU', False)
                    market_cap_value = original_row_data.get('MarketCap', np.nan) # Get MarketCap
                    company_type = get_company_type(psu_value)
                    ath_drop_percent = 30.0 if company_type == "PSU" else 20.0
                    sell_rise_percent = 20.0
                    buy_trigger_price = ath * (1 - (ath_drop_percent / 100.0))
                    sell_trigger_price = buy_trigger_price * (1 + (sell_rise_percent / 100.0))
                    cmp_vs_buy_trigger_pct = ((cmp - buy_trigger_price) / buy_trigger_price) * 100.0 if buy_trigger_price != 0 else np.nan
                    all_ath_triggers.append({
                        'Symbol': symbol_short, 'Company Name': company_name, 'Type': company_type,
                        'MarketCap': market_cap_value, # MarketCap included here
                        'All-Time High (ATH)': round(ath, 2), 'Current Market Price (CMP)': round(cmp, 2),
                        'Buy Trigger Price': round(buy_trigger_price, 2), 'Sell Trigger Price': round(sell_trigger_price, 2),
                        'CMP Proximity to Buy (%)': round(cmp_vs_buy_trigger_pct, 2) if pd.notna(cmp_vs_buy_trigger_pct) else "N/A",
                        'ClosenessAbs (%)': abs(round(cmp_vs_buy_trigger_pct, 2)) if pd.notna(cmp_vs_buy_trigger_pct) else np.inf
                    })
    sys.stdout.write("\nATH: Done processing profit company symbols.\n"); sys.stdout.flush()

    num_ath_generated = 0
    if all_ath_triggers:
        ath_df_generated = pd.DataFrame(all_ath_triggers) # Create from list of dicts
        for col_name in final_output_ath_columns: # Ensure all desired columns are present
            if col_name not in ath_df_generated.columns:
                ath_df_generated[col_name] = np.nan
        ath_df_generated = ath_df_generated[final_output_ath_columns] # Select and order
        ath_df_generated = ath_df_generated.sort_values(by=['ClosenessAbs (%)', 'Symbol']).reset_index(drop=True)
        num_ath_generated = len(ath_df_generated)
        try:
            ath_df_generated.to_csv(output_ath_file_path, index=False)
            print(f"ATH: Saved {num_ath_generated} ATH triggers to '{output_ath_file_path}'")
            return True, num_ath_generated
        except Exception as e:
            print(f"ATH ERROR: saving ATH triggers to '{output_ath_file_path}': {e}")
            return False, 0
    else:
        print("ATH: No ATH triggers were successfully generated.")
        try: 
            pd.DataFrame(columns=final_output_ath_columns).to_csv(output_ath_file_path, index=False)
            print(f"ATH: Saved empty ATH triggers file to '{output_ath_file_path}'.")
            return True, 0
        except Exception as e:
            print(f"ATH ERROR: saving empty ATH triggers file: {e}")
            return False, 0

# --- Git Helper Functions ---
def run_git_command(command_list, working_dir="."):
    # ... (Your existing function - UNCHANGED) ...
    try:
        # print(f"GIT CMD: Running '{' '.join(command_list)}' in '{working_dir}'")
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


def commit_and_push_files_to_github(files_to_add, commit_message): # Modified to take a list
    print(f"\n--- GIT OPS: Starting Git Operations for {len(files_to_add)} file(s) ---")

    # 1. Remove old generated files (both types)
    today_date_str = datetime.now().strftime("%Y%m%d")
    # Construct full paths for the new files to avoid accidentally removing them
    new_files_full_paths = [os.path.abspath(os.path.join(REPO_BASE_PATH, f)) for f in files_to_add]

    for item in os.listdir(REPO_BASE_PATH):
        if (item.startswith("stock_candle_signals_from_listing_") or item.startswith("ath_triggers_data_")) and item.endswith(".csv"):
            item_full_path = os.path.abspath(os.path.join(REPO_BASE_PATH, item))
            # Ensure we don't try to remove the files we just created/are about to add
            if item_full_path not in new_files_full_paths:
                print(f"GIT OPS: Found old generated file: {item}. Attempting to remove.")
                if run_git_command(["git", "rm", "-f", item], working_dir=REPO_BASE_PATH):
                     print(f"GIT OPS: Successfully 'git rm {item}'.")
                else: # If git rm fails (e.g. not tracked), try deleting from disk
                    try:
                        if os.path.exists(item_full_path): os.remove(item_full_path); print(f"GIT OPS: Deleted '{item}' from disk.")
                    except Exception as e: print(f"GIT OPS WARNING: Could not delete old file '{item}' from disk: {e}")
    
    # 2. Add the new files
    added_successfully = True
    for file_to_add in files_to_add:
        if not os.path.exists(os.path.join(REPO_BASE_PATH, file_to_add)):
            print(f"GIT OPS WARNING: File '{file_to_add}' not found. Skipping add.")
            continue # Skip this file if it doesn't exist (e.g., generation failed for one type)
        if not run_git_command(["git", "add", file_to_add], working_dir=REPO_BASE_PATH):
            print(f"GIT OPS ERROR: Failed to 'git add {file_to_add}'.")
            added_successfully = False # Mark that at least one add failed
        else:
            print(f"GIT OPS: Successfully added '{file_to_add}' to staging.")
    
    # If no files were actually added (e.g. all were missing), nothing to commit.
    # Check git status before committing
    status_check_process = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO_BASE_PATH)
    if not status_check_process.stdout.strip():
        print("GIT OPS: No changes staged for commit. Skipping commit and push.")
        return True # Nothing to do, considered a success for workflow

    if not added_successfully and not status_check_process.stdout.strip(): # No files added AND no other changes
        print("GIT OPS: No new files were added or found. Aborting commit.")
        return True # Technically not a failure of git itself if nothing was there to add

    # 3. Commit
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
    print(f"DAILY DATA GENERATION SCRIPT: Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    today_date_str = datetime.now().strftime("%Y%m%d")
    
    files_generated_for_commit = []
    overall_success = True

    # --- Generate Candle Signals File ---
    output_signals_filename_relative = OUTPUT_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date_str)
    output_signals_file_fullpath = os.path.join(REPO_BASE_PATH, output_signals_filename_relative)
    success_signals, num_signals = generate_and_save_candle_analysis_file(INPUT_GROWTH_DF_PATH, output_signals_file_fullpath)
    if success_signals:
        print(f"SCRIPT: Candle analysis processing finished: {output_signals_filename_relative} ({num_signals} signals)")
        if os.path.exists(output_signals_file_fullpath): # Ensure file exists before adding
             files_generated_for_commit.append(output_signals_filename_relative)
    else:
        print("SCRIPT ERROR: Candle analysis file generation failed.")
        overall_success = False

    # --- Generate ATH Triggers File ---
    output_ath_filename_relative = OUTPUT_ATH_TRIGGERS_FILENAME_TEMPLATE.format(date_str=today_date_str)
    output_ath_file_fullpath = os.path.join(REPO_BASE_PATH, output_ath_filename_relative)
    success_ath, num_ath_triggers = generate_and_save_ath_triggers_file(INPUT_PROFIT_DF_PATH, output_ath_file_fullpath)
    if success_ath:
        print(f"SCRIPT: ATH Triggers processing finished: {output_ath_filename_relative} ({num_ath_triggers} records)")
        if os.path.exists(output_ath_file_fullpath): # Ensure file exists
            files_generated_for_commit.append(output_ath_filename_relative)
    else:
        print("SCRIPT ERROR: ATH Triggers file generation failed.")
        overall_success = False # Mark failure if this part fails

    # --- Commit and Push if any files were successfully generated and exist ---
    if files_generated_for_commit:
        commit_msg = f"Automated daily data update for {today_date_str}"
        if num_signals > -1 : commit_msg += f" ({num_signals} signals" # -1 if not run
        if num_ath_triggers > -1 : commit_msg += f", {num_ath_triggers} ATH records)"
        else: commit_msg += ")"

        if commit_and_push_files_to_github(files_generated_for_commit, commit_msg):
            print("SCRIPT: Successfully committed and pushed to GitHub.")
        else:
            print("SCRIPT ERROR: Failed to commit and push to GitHub.")
            overall_success = False # Mark failure for git ops
    elif overall_success: # No files to commit but no errors in generation either (e.g. empty outputs)
        print("SCRIPT: No new data files were generated or found to commit, but script ran without generation errors.")
    else: # No files to commit AND there were generation errors
        print("SCRIPT: No files to commit due to generation errors.")


    print(f"DAILY DATA GENERATION SCRIPT: Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if overall_success and files_generated_for_commit: # Exit 0 only if everything went well AND there was something to commit
        sys.exit(0)
    elif overall_success and not files_generated_for_commit: # Script ran fine, but nothing new to commit
        print("SCRIPT NOTE: Process completed, but no new files were generated or staged for commit (e.g., all outputs were empty or unchanged).")
        sys.exit(0) # Still a successful run of the script itself
    else:
        sys.exit(1) # Indicate failure
