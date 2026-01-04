# data_manager.py
import os
import pandas as pd
from datetime import datetime
import numpy as np
import yfinance as yf
import requests_cache
import time
# ... other imports ...

# --- START: NEW GITHUB CONFIGURATION ---
# Replace these with your actual GitHub username and repository name
GITHUB_USERNAME = "pathikpatel-ml"
GITHUB_REPOSITORY = "stock_dashboard_project"
# In data_manager.py

# --- Configuration ---
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"

# --- Global In-Memory Cache ---
v20_signals_cache = pd.DataFrame()
ma_signals_cache = pd.DataFrame()
V20_CACHE_DATE = None
MA_CACHE_DATE = None

# --- Configuration (Unchanged) ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

# --- Global DataFrames (Data Cache) ---
signals_df = pd.DataFrame()
v20_signals_df = pd.DataFrame()  # Added missing global variable
growth_df = pd.DataFrame()
all_available_symbols = []
v20_processed_df = pd.DataFrame() # This is our cache

# --- START: NEW GLOBAL VARIABLES TO FIX STALE DATA ISSUE ---
# These variables will track the date of the loaded files.
LOADED_V20_FILE_DATE = None
LOADED_MA_FILE_DATE = None
# --- END: NEW GLOBAL VARIABLES ---


# --- V20 Helper Function (Your Exact Logic - UNCHANGED) ---
def process_v20_signals(signals_df_local):
    """
    This function uses the exact logic you provided to process V20 signals.
    It fetches live prices for all signals and calculates proximity.
    """
    if signals_df_local.empty or 'Symbol' not in signals_df_local.columns: return pd.DataFrame()
    df_to_process = signals_df_local.copy()
    
    print("DASH (V20 NearestBuy): Fetching CMPs...")
    unique_symbols = df_to_process['Symbol'].dropna().astype(str).str.upper().unique()
    if not unique_symbols.any(): return pd.DataFrame()
    
    yf_symbols = [f"{s}.NS" for s in unique_symbols]; latest_prices_map = {}
    chunk_size = 50
    for i in range(0, len(yf_symbols), chunk_size):
        chunk = yf_symbols[i:i + chunk_size]
        try:
            data = yf.download(tickers=chunk, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=20)
            if data is not None and not data.empty:
                for sym_ns_original_case in chunk:
                    base_sym = sym_ns_original_case.replace(".NS", "")
                    price_series = None
                    if isinstance(data.columns, pd.MultiIndex):
                        if (sym_ns_original_case, 'Close') in data.columns:
                            price_series = data[(sym_ns_original_case, 'Close')]
                        elif (sym_ns_original_case.upper(), 'Close') in data.columns:
                            price_series = data[(sym_ns_original_case.upper(), 'Close')]
                    elif isinstance(data, dict) and sym_ns_original_case in data:
                        if 'Close' in data[sym_ns_original_case].columns:
                            price_series = data[sym_ns_original_case]['Close']
                    elif 'Close' in data.columns and len(chunk) == 1:
                        price_series = data['Close']
                    
                    if price_series is not None and not price_series.dropna().empty:
                        latest_prices_map[base_sym.upper()] = price_series.dropna().iloc[-1]
        except Exception as e_yf: print(f"DASH (V20 NearestBuy): yf.download error for chunk: {e_yf}")

    df_to_process['Latest Close Price'] = df_to_process['Symbol'].astype(str).str.upper().map(latest_prices_map)
    df_to_process.dropna(subset=['Latest Close Price'], inplace=True)
    if df_to_process.empty: return pd.DataFrame()

    results = []
    for _idx, row in df_to_process.iterrows():
        symbol, buy_target, cmp_val = str(row.get('Symbol','')).upper(), row.get('Buy_Price_Low'), row.get('Latest Close Price')
        if not symbol or pd.isna(buy_target) or buy_target == 0 or pd.isna(cmp_val): continue
        prox_pct = ((cmp_val - buy_target) / buy_target) * 100
        buy_date_str = pd.to_datetime(row.get('Buy_Date')).strftime('%Y-%m-%d') if pd.notna(row.get('Buy_Date')) else 'N/A'
        results.append({'Symbol': symbol, 'Signal Buy Date': buy_date_str, 'Target Buy Price (Low)': round(buy_target, 2),
                        'Latest Close Price': round(cmp_val, 2), 'Proximity to Buy (%)': round(prox_pct, 2),
                        'Closeness (%)': round(abs(prox_pct), 2),
                        'Potential Gain (%)': round(row.get('Sequence_Gain_Percent', np.nan), 2)})
    if not results: return pd.DataFrame()
    return pd.DataFrame(results).sort_values(by=['Closeness (%)', 'Symbol']).reset_index(drop=True)

# --- MA Helper Function (Unchanged) ---
def process_ma_signals_for_ui(ma_events_df):
    if ma_events_df.empty: return pd.DataFrame(), pd.DataFrame()
    active_primary, active_secondary = {}, {}
    for symbol, group in ma_events_df.sort_values(by=['Symbol', 'Date']).groupby('Symbol'):
        last_primary_buy = group[group['Event_Type'] == 'Primary_Buy'].tail(1)
        if last_primary_buy.empty: continue
        sell_after_buy = group[(group['Event_Type'] == 'Primary_Sell') & (group['Date'] > last_primary_buy.iloc[0]['Date'])]
        if sell_after_buy.empty:
            active_primary[symbol] = last_primary_buy.iloc[0].to_dict()
            relevant_events = group[group['Date'] >= last_primary_buy.iloc[0]['Date']]
            last_sec_buy = relevant_events[relevant_events['Event_Type'] == 'Secondary_Buy_Dip'].tail(1)
            if not last_sec_buy.empty:
                sec_sell_after_buy = relevant_events[(relevant_events['Event_Type'] == 'Secondary_Sell_Rise') & (relevant_events['Date'] > last_sec_buy.iloc[0]['Date'])]
                if sec_sell_after_buy.empty: active_secondary[symbol] = last_sec_buy.iloc[0].to_dict()
    active_symbols = set(active_primary.keys())
    if not active_symbols: return pd.DataFrame(), pd.DataFrame()
    prices = yf.download(tickers=[f"{s}.NS" for s in active_symbols], period="2d", progress=False)['Close'].iloc[-1]
    latest_prices_map = prices.to_dict()
    primary_list = [{'Symbol': s, 'Company Name': d.get('Company Name'), 'Type': d.get('Type'), 'Market Cap': d.get('MarketCap'), 'Primary Buy Date': d['Date'].strftime('%Y-%m-%d'), 'Primary Buy Price': round(d['Price'], 2), 'Current Price': round(latest_prices_map.get(f"{s}.NS", 0), 2), 'Difference (%)': round(((latest_prices_map.get(f"{s}.NS", 0) - d['Price']) / d.get('Price', 1)) * 100, 2)} for s, d in active_primary.items() if f"{s}.NS" in latest_prices_map]
    secondary_list = [{'Symbol': s, 'Company Name': d.get('Company Name'), 'Type': d.get('Type'), 'Market Cap': d.get('MarketCap'), 'Secondary Buy Date': d['Date'].strftime('%Y-%m-%d'), 'Secondary Buy Price': round(d['Price'], 2), 'Current Price': round(latest_prices_map.get(f"{s}.NS", 0), 2), 'Difference (%)': round(((latest_prices_map.get(f"{s}.NS", 0) - d['Price']) / d.get('Price', 1)) * 100, 2)} for s, d in active_secondary.items() if f"{s}.NS" in latest_prices_map]
    return pd.DataFrame(primary_list), pd.DataFrame(secondary_list)


# # --- NEW MAIN DATA LOADING FUNCTION ---
# def load_data():
#     """
#     Loads all necessary data from GitHub on startup.
#     This mimics the successful monolithic approach.
#     """
#     global v20_signals_df, ma_signals_df, all_available_symbols
    
#     today_str = datetime.now().strftime("%Y%m%d")
    
#     # Load V20 Signals
#     v20_filename = SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str)
#     v20_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{v20_filename}"
#     print(f"Attempting to load V20 data from: {v20_url}")
#     try:
#         v20_signals_df = pd.read_csv(v20_url, parse_dates=['Buy_Date', 'Sell_Date'])
#         print(f"Successfully loaded {len(v20_signals_df)} V20 signals.")
#     except Exception as e:
#         print(f"Failed to load V20 data: {e}")
#         v20_signals_df = pd.DataFrame()

#     # Load MA Signals
#     ma_filename = MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str)
#     ma_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{ma_filename}"
#     print(f"Attempting to load MA data from: {ma_url}")
#     try:
#         ma_signals_df = pd.read_csv(ma_url, parse_dates=['Date'])
#         print(f"Successfully loaded {len(ma_signals_df)} MA events.")
#     except Exception as e:
#         print(f"Failed to load MA data: {e}")
#         ma_signals_df = pd.DataFrame()
        
#     # Populate the symbol list for the dropdown
#     symbols_s = v20_signals_df['Symbol'].dropna().unique().tolist() if not v20_signals_df.empty else []
#     symbols_m = ma_signals_df['Symbol'].dropna().unique().tolist() if not ma_signals_df.empty else []
#     all_available_symbols = sorted(list(set(symbols_s + symbols_m)))

def load_and_process_data_on_startup():
    global v20_signals_df, all_available_symbols, v20_processed_df
    today_str = datetime.now().strftime("%Y%m%d")
    
    # Load V20 from GitHub
    v20_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str)}"
    try:
        v20_signals_df = pd.read_csv(v20_url, parse_dates=['Buy_Date', 'Sell_Date'])
        # Initial slow processing
        v20_processed_df = process_v20_signals(v20_signals_df)
        print(f"STARTUP: Loaded and processed {len(v20_processed_df)} active V20 signals from dynamic stock list.")
    except Exception as e:
        print(f"STARTUP ERROR: Failed to load V20 data: {e}")
