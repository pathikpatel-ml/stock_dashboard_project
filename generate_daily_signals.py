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

# For Candle Signals (Your V20 Strategy)
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv" # Assuming this is the input for V20
INPUT_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)
OUTPUT_SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv" # Output for V20

# For Moving Average Signals (New Module)
PROFIT_COMPANIES_FILE_NAME = "Master_5000_profit_companies.csv" # Input for MA Signals
INPUT_PROFIT_DF_PATH = os.path.join(REPO_BASE_PATH, PROFIT_COMPANIES_FILE_NAME)
OUTPUT_MA_SIGNALS_FILENAME_TEMPLATE = "ma_signals_data_{date_str}.csv" # Output for MA Signals

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

def generate_and_save_candle_analysis_file(current_growth_file_path, output_candle_file_path): # Your V20 main generation
    print(f"\n--- GENERATION: Starting Candle Analysis (V20 Strategy) ---")
    if not os.path.exists(current_growth_file_path): print(f"Candle ERROR: Symbol list '{current_growth_file_path}' NOT FOUND."); return False, 0
    try: growth_df = pd.read_csv(current_growth_file_path)
    except Exception as e: print(f"Candle ERROR: reading list '{current_growth_file_path}': {e}"); return False, 0
    if 'Symbol' not in growth_df.columns: print(f"Candle ERROR: 'Symbol' column missing in '{current_growth_file_path}'."); return False, 0
    if growth_df.empty: print("Candle: Symbol list empty.");

    all_candle_signals = []
    symbols_for_analysis = growth_df["Symbol"].dropna().astype(str).unique()
    total_symbols = len(symbols_for_analysis)
    print(f"Candle: Analyzing {total_symbols} symbols for V20 strategy...")

    for i, symbol_short in enumerate(symbols_for_analysis):
        symbol_nse = f"{symbol_short.upper().strip()}.NS"
        sys.stdout.write(f"\rCandle (V20): [{i+1}/{total_symbols}] {symbol_short} ({( (i + 1) / total_symbols) * 100:.1f}%)")
        sys.stdout.flush()
        hist_data = fetch_historical_data_yf_candle(symbol_nse) # Use candle-specific fetch
        if not hist_data.empty:
            signals = analyze_stock_candles(symbol_short, hist_data) # Your V20 analysis
            if signals: all_candle_signals.extend(signals)
        time.sleep(0.1)
    sys.stdout.write("\nCandle (V20): Done processing symbols.\n"); sys.stdout.flush()

    num_signals_generated = 0
    output_df_columns = ['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence']
    if all_candle_signals:
        signals_df_generated = pd.DataFrame(all_candle_signals, columns=output_df_columns).sort_values(by=['Symbol', 'Buy_Date']).reset_index(drop=True)
        num_signals_generated = len(signals_df_generated)
        try: signals_df_generated.to_csv(output_candle_file_path, index=False); print(f"Candle (V20): Saved {num_signals_generated} signals to '{output_candle_file_path}'"); return True, num_signals_generated
        except Exception as e: print(f"Candle (V20) ERROR: saving signals: {e}"); return False, 0
    else:
        print("Candle (V20): No signals generated.")
        try: pd.DataFrame(columns=output_df_columns).to_csv(output_candle_file_path, index=False); print(f"Candle (V20): Saved empty file to '{output_candle_file_path}'."); return True, 0
        except Exception as e: print(f"Candle (V20) ERROR: saving empty signals file: {e}"); return False, 0

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

# --- Moving Average (MA) Signal Generation Functions ---
def fetch_historical_data_yf_ma(symbol_nse):
    """Fetches historical data specifically for MA analysis (e.g., 2-5 years)."""
    try:
        stock_ticker = yf.Ticker(symbol_nse)
        hist_data = stock_ticker.history(period="2y", interval="1d", auto_adjust=False, actions=False, timeout=20) # No actions needed
        if hist_data.empty:
            hist_data = stock_ticker.history(period="5y", interval="1d", auto_adjust=False, actions=False, timeout=15)
            if hist_data.empty:
                 return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        required_ohlc = ['Open', 'High', 'Low', 'Close'] # Still need OHLC for 'Close'
        if not all(col in hist_data.columns for col in required_ohlc): return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=['Close'], inplace=True) # Only 'Close' is strictly needed for MAs
        hist_data = hist_data.sort_values(by='Date').reset_index(drop=True)
        return hist_data
    except Exception as e:
        # print(f"Error fetching {symbol_nse} for MA: {e}")
        return pd.DataFrame()

def generate_and_save_ma_signals_file(company_list_file_path, output_ma_signals_file_path):
    print(f"\n--- GENERATION: Starting Moving Average (MA) Signal Analysis (Simplified Secondary) ---")
    print(f"MA Signals: Using input company list from: {company_list_file_path}")

    if not os.path.exists(company_list_file_path):
        print(f"MA Signals ERROR: Company list file '{company_list_file_path}' NOT FOUND.")
        return False, 0
    try:
        input_df = pd.read_csv(company_list_file_path)
    except Exception as e:
        print(f"MA Signals ERROR: reading company list file '{company_list_file_path}': {e}")
        return False, 0

    final_output_ma_columns = [
        'Symbol', 'Company Name', 'Type', 'MarketCap', 'Date', 'Event_Type',
        'Price', 'SMA20', 'SMA50', 'SMA200', 'Primary_Buy_Ref_Price', 'Details'
    ]
    essential_input_cols = ['Symbol', 'Company Name', 'V40'] # From your profit_companies_file
    for col in essential_input_cols:
        if col not in input_df.columns:
            print(f"MA Signals ERROR: Essential input column '{col}' missing in '{company_list_file_path}'.")
            return False, 0
    if 'MarketCap' not in input_df.columns:
        print(f"MA Signals WARNING: 'MarketCap' column missing. Output MarketCap will be NaN.")
        input_df['MarketCap'] = np.nan
            
    if input_df.empty:
        print("MA Signals: Company list file is empty.")
        try: 
            pd.DataFrame(columns=final_output_ma_columns).to_csv(output_ma_signals_file_path, index=False)
            print(f"MA Signals: Saved empty MA signals file to '{output_ma_signals_file_path}'.")
            return True, 0
        except Exception as e: 
            print(f"MA Signals ERROR: saving empty MA signals file: {e}")
            return False, 0

    all_ma_signals_events = []
    input_df['Symbol'] = input_df['Symbol'].astype(str).str.strip().str.upper()
    symbols_for_ma = input_df["Symbol"].unique()
    total_symbols_ma = len(symbols_for_ma)
    
    if total_symbols_ma == 0:
        print("MA Signals: No symbols found in the company list after cleaning.")
        try: 
            pd.DataFrame(columns=final_output_ma_columns).to_csv(output_ma_signals_file_path, index=False)
            print(f"MA Signals: Saved empty MA signals file to '{output_ma_signals_file_path}'.")
            return True, 0
        except Exception as e: 
            print(f"MA Signals ERROR: saving empty MA signals file: {e}")
            return False, 0

    print(f"MA Signals: Analyzing MA signals for {total_symbols_ma} unique companies...")
    company_details_map = {row['Symbol']: row for _, row in input_df.drop_duplicates(subset=['Symbol']).iterrows()}
    
    for i, symbol_short in enumerate(symbols_for_ma):
        symbol_nse = f"{symbol_short}.NS"
        company_data = company_details_map.get(symbol_short, {})
        company_name = company_data.get('Company Name', "N/A")
        v40_value = company_data.get('V40', False) # <<< CHANGE to get 'V40' value, 
        market_cap_value = company_data.get('MarketCap', np.nan)
        company_type = get_v40_type(v40_value)

        sys.stdout.write(f"\rMA Signals: [{i+1}/{total_symbols_ma}] Processing {symbol_short}...")
        sys.stdout.flush()

        hist_data = fetch_historical_data_yf_ma(symbol_nse) # Use MA-specific fetch
        if hist_data.empty or len(hist_data) < 200: # Need at least 200 days for SMA200
            time.sleep(0.05)
            continue
        
        hist_data['SMA20'] = hist_data['Close'].rolling(window=20, min_periods=1).mean() # min_periods=1 for start of series
        hist_data['SMA50'] = hist_data['Close'].rolling(window=50, min_periods=1).mean()
        hist_data['SMA200'] = hist_data['Close'].rolling(window=200, min_periods=1).mean()
        
        # We need to iterate from a point where all MAs are valid (or handle NaNs carefully)
        # For simplicity, let's start iterating after the longest MA period.
        # Or, ensure the loop handles NaN MAs gracefully.
        # The condition sma200 > sma50 > sma20 > current_close will naturally handle NaNs (evaluate to False).
        
        # Start iterating from the first row where SMA200 is not NaN
        first_valid_ma_index = hist_data['SMA200'].first_valid_index()
        if first_valid_ma_index is None: # Should not happen if len(hist_data) >= 200
            time.sleep(0.05)
            continue
        
        iter_hist_data = hist_data.loc[first_valid_ma_index:].copy()
        if iter_hist_data.empty:
            time.sleep(0.05)
            continue

        primary_buy_active = False
        primary_buy_price = np.nan
        primary_buy_date = None
        secondary_buy_triggered_for_current_primary = False
        secondary_buy_price_instance = np.nan

        for _, row in iter_hist_data.iterrows():
            current_date = row['Date']
            current_close = row['Close']
            sma20, sma50, sma200 = row['SMA20'], row['SMA50'], row['SMA200']

            # Skip if any MA is NaN for this row (shouldn't happen with iter_hist_data logic but good check)
            if pd.isna(sma20) or pd.isna(sma50) or pd.isna(sma200) or pd.isna(current_close):
                continue

            if primary_buy_active and (sma200 < sma50 < sma20 < current_close):
                all_ma_signals_events.append({
                    'Symbol': symbol_short, 'Company Name': company_name, 'Type': company_type,
                    'MarketCap': market_cap_value, 'Date': current_date.strftime('%Y-%m-%d'),
                    'Event_Type': 'Primary_Sell', 'Price': round(current_close, 2),
                    'SMA20': round(sma20, 2), 'SMA50': round(sma50, 2), 'SMA200': round(sma200, 2),
                    'Primary_Buy_Ref_Price': round(primary_buy_price,2) if pd.notna(primary_buy_price) else np.nan,
                    'Details': f"Closed primary buy from {primary_buy_date.strftime('%Y-%m-%d')} at {primary_buy_price:.2f}"
                })
                primary_buy_active = False; primary_buy_price = np.nan; primary_buy_date = None
                secondary_buy_triggered_for_current_primary = False; secondary_buy_price_instance = np.nan
                continue 

            if not primary_buy_active and (sma200 > sma50 > sma20 > current_close):
                primary_buy_active = True; primary_buy_price = current_close; primary_buy_date = current_date
                secondary_buy_triggered_for_current_primary = False; secondary_buy_price_instance = np.nan
                all_ma_signals_events.append({
                    'Symbol': symbol_short, 'Company Name': company_name, 'Type': company_type,
                    'MarketCap': market_cap_value, 'Date': current_date.strftime('%Y-%m-%d'),
                    'Event_Type': 'Primary_Buy', 'Price': round(current_close, 2),
                    'SMA20': round(sma20, 2), 'SMA50': round(sma50, 2), 'SMA200': round(sma200, 2),
                    'Primary_Buy_Ref_Price': round(current_close,2),
                    'Details': "MA Crossover Buy"
                })
                continue

            if primary_buy_active:
                if secondary_buy_triggered_for_current_primary and pd.notna(secondary_buy_price_instance) and \
                   (current_close >= secondary_buy_price_instance * 1.10):
                    all_ma_signals_events.append({
                        'Symbol': symbol_short, 'Company Name': company_name, 'Type': company_type,
                        'MarketCap': market_cap_value, 'Date': current_date.strftime('%Y-%m-%d'),
                        'Event_Type': 'Secondary_Sell_Rise', 'Price': round(current_close, 2),
                        'SMA20': round(sma20, 2), 'SMA50': round(sma50, 2), 'SMA200': round(sma200, 2),
                        'Primary_Buy_Ref_Price': round(primary_buy_price,2),
                        'Details': f"Sell from secondary dip (buy at {secondary_buy_price_instance:.2f})"
                    })
                    secondary_buy_price_instance = np.nan # Mark secondary as sold

                elif not secondary_buy_triggered_for_current_primary and \
                     (current_close <= primary_buy_price * 0.90): # primary_buy_price must be valid here
                    secondary_buy_triggered_for_current_primary = True
                    secondary_buy_price_instance = current_close
                    all_ma_signals_events.append({
                        'Symbol': symbol_short, 'Company Name': company_name, 'Type': company_type,
                        'MarketCap': market_cap_value, 'Date': current_date.strftime('%Y-%m-%d'),
                        'Event_Type': 'Secondary_Buy_Dip', 'Price': round(current_close, 2),
                        'SMA20': round(sma20, 2), 'SMA50': round(sma50, 2), 'SMA200': round(sma200, 2),
                        'Primary_Buy_Ref_Price': round(primary_buy_price,2),
                        'Details': "10% dip from primary buy"
                    })
        
        if primary_buy_active and not iter_hist_data.empty:
            last_row = iter_hist_data.iloc[-1]
            details_open = f"Primary buy from {primary_buy_date.strftime('%Y-%m-%d')} at {primary_buy_price:.2f} is still active."
            if secondary_buy_triggered_for_current_primary and pd.notna(secondary_buy_price_instance):
                details_open += f" Secondary buy at {secondary_buy_price_instance:.2f} is also active."
            elif secondary_buy_triggered_for_current_primary and pd.isna(secondary_buy_price_instance):
                 details_open += " Secondary buy occurred and was sold."
            else:
                details_open += " No secondary buy triggered yet for this primary cycle."

            all_ma_signals_events.append({
                'Symbol': symbol_short, 'Company Name': company_name, 'Type': company_type,
                'MarketCap': market_cap_value, 'Date': last_row['Date'].strftime('%Y-%m-%d'),
                'Event_Type': 'Position_Still_Open', 'Price': round(last_row['Close'], 2),
                'SMA20': round(last_row['SMA20'], 2), 'SMA50': round(last_row['SMA50'], 2), 'SMA200': round(last_row['SMA200'], 2),
                'Primary_Buy_Ref_Price': round(primary_buy_price,2) if pd.notna(primary_buy_price) else np.nan,
                'Details': details_open
            })
        time.sleep(0.1)

    sys.stdout.write("\nMA Signals: Done processing company symbols.\n"); sys.stdout.flush()

    num_ma_signals = 0
    if all_ma_signals_events:
        ma_signals_df = pd.DataFrame(all_ma_signals_events)
        for col_name in final_output_ma_columns:
            if col_name not in ma_signals_df.columns:
                ma_signals_df[col_name] = np.nan 
        ma_signals_df = ma_signals_df[final_output_ma_columns]
        ma_signals_df = ma_signals_df.sort_values(by=['Symbol', 'Date']).reset_index(drop=True)
        num_ma_signals = len(ma_signals_df)
        try:
            ma_signals_df.to_csv(output_ma_signals_file_path, index=False)
            print(f"MA Signals: Saved {num_ma_signals} MA signal events to '{output_ma_signals_file_path}'")
            return True, num_ma_signals
        except Exception as e:
            print(f"MA Signals ERROR: saving MA signals to '{output_ma_signals_file_path}': {e}")
            return False, 0
    else:
        print("MA Signals: No MA signal events were generated.")
        try: 
            pd.DataFrame(columns=final_output_ma_columns).to_csv(output_ma_signals_file_path, index=False)
            print(f"MA Signals: Saved empty MA signals file to '{output_ma_signals_file_path}'.")
            return True, 0
        except Exception as e:
            print(f"MA Signals ERROR: saving empty MA signals file: {e}")
            return False, 0

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
        # Remove old candle, old ATH, and old MA signal files
        if (item.startswith("stock_candle_signals_from_listing_") or \
            item.startswith("ath_triggers_data_") or \
            item.startswith("ma_signals_data_")) and item.endswith(".csv"):
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
    num_ma_events = -1 

    # --- Generate Candle Signals File (V20 Strategy) ---
    output_candle_signals_filename_relative = OUTPUT_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date_str)
    output_candle_signals_file_fullpath = os.path.join(REPO_BASE_PATH, output_candle_signals_filename_relative)
    success_candle_signals, num_candle_signals = generate_and_save_candle_analysis_file(INPUT_GROWTH_DF_PATH, output_candle_signals_file_fullpath)
    if success_candle_signals:
        print(f"SCRIPT: Candle analysis (V20) processing finished: {output_candle_signals_filename_relative} ({num_candle_signals} signals)")
        if os.path.exists(output_candle_signals_file_fullpath):
             files_generated_for_commit.append(output_candle_signals_filename_relative)
    else:
        print("SCRIPT ERROR: Candle analysis (V20) file generation failed.")
        overall_success = False

    # --- Generate MA Signals File ---
    output_ma_filename_relative = OUTPUT_MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date_str)
    output_ma_file_fullpath = os.path.join(REPO_BASE_PATH, output_ma_filename_relative)
    success_ma, num_ma_events = generate_and_save_ma_signals_file(INPUT_PROFIT_DF_PATH, output_ma_file_fullpath) # Use INPUT_PROFIT_DF_PATH
    if success_ma:
        print(f"SCRIPT: MA Signals processing finished: {output_ma_filename_relative} ({num_ma_events} events)")
        if os.path.exists(output_ma_file_fullpath):
            files_generated_for_commit.append(output_ma_filename_relative)
    else:
        print("SCRIPT ERROR: MA Signals file generation failed.")
        overall_success = False

    # --- Commit and Push if any files were successfully generated ---
    if files_generated_for_commit:
        commit_msg_parts = []
        if num_candle_signals > -1:
            commit_msg_parts.append(f"{num_candle_signals} V20 signals")
        if num_ma_events > -1:
            commit_msg_parts.append(f"{num_ma_events} MA events")
        
        commit_details = ", ".join(commit_msg_parts)
        commit_msg = f"Automated daily data for {today_date_str}"
        if commit_details:
            commit_msg += f" ({commit_details})"

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
