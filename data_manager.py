# data_manager.py
import os
import pandas as pd
from datetime import datetime
import numpy as np
import yfinance as yf
import requests_cache
# ... other imports ...

# --- START: NEW GITHUB CONFIGURATION ---
# Replace these with your actual GitHub username and repository name
GITHUB_USERNAME = "pathikpatel-ml"
GITHUB_REPOSITORY = "stock_dashboard_project"
# In data_manager.py

# --- Configuration ---
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"
MA_SIGNALS_FILENAME_TEMPLATE = "ma_signals_data_{date_str}.csv"

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
ma_signals_df = pd.DataFrame()
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


# --- START: NEW DYNAMIC DATA LOADING FUNCTION ---
# This function replaces the old `load_data_for_dashboard_from_repo`
# def load_data_if_stale():
#     """
#     Checks if the data in memory is for today. If not, it reloads.
#     This function will be called from the UI callbacks to prevent stale data.
#     """
#     global signals_df, ma_signals_df, all_available_symbols, v20_processed_df
#     global LOADED_V20_FILE_DATE, LOADED_MA_FILE_DATE
    
#     today_date = datetime.now().date()
    
#     # Check and reload V20 data if stale
#     if LOADED_V20_FILE_DATE != today_date:
#         print(f"DATA MANAGER: V20 data is stale (or not loaded). Attempting to load for {today_date}...")
#         v20_filename = os.path.join(REPO_BASE_PATH, SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date.strftime("%Y%m%d")))
#         if os.path.exists(v20_filename):
#             try:
#                 signals_df = pd.read_csv(v20_filename, parse_dates=['Buy_Date', 'Sell_Date'])
#                 v20_processed_df = process_v20_signals(signals_df) # Process the new data
#                 LOADED_V20_FILE_DATE = today_date
#                 print(f"DATA MANAGER: Successfully loaded and processed {len(v20_processed_df)} V20 signals.")
#             except Exception as e:
#                 print(f"DATA MANAGER ERROR: Failed to load V20 file '{v20_filename}': {e}")
#                 signals_df = pd.DataFrame() # Clear on error
#                 v20_processed_df = pd.DataFrame()
#         else:
#             print(f"DATA MANAGER: V20 file not found for today.")
#             signals_df = pd.DataFrame()
#             v20_processed_df = pd.DataFrame()

#     # Check and reload MA data if stale
#     if LOADED_MA_FILE_DATE != today_date:
#         print(f"DATA MANAGER: MA data is stale. Attempting to load for {today_date}...")
#         ma_filename = os.path.join(REPO_BASE_PATH, MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date.strftime("%Y%m%d")))
#         if os.path.exists(ma_filename):
#             try:
#                 ma_signals_df = pd.read_csv(ma_filename, parse_dates=['Date'])
#                 LOADED_MA_FILE_DATE = today_date
#                 print(f"DATA MANAGER: Successfully loaded {len(ma_signals_df)} MA events.")
#             except Exception as e:
#                 print(f"DATA MANAGER ERROR: Failed to load MA file '{ma_filename}': {e}")
#                 ma_signals_df = pd.DataFrame()
#         else:
#             print(f"DATA MANAGER: MA file not found for today.")
#             ma_signals_df = pd.DataFrame()
            
#     # Always update the symbol list after loading
#     symbols_s = signals_df['Symbol'].dropna().unique().tolist() if not signals_df.empty else []
#     symbols_m = ma_signals_df['Symbol'].dropna().unique().tolist() if not ma_signals_df.empty else []
#     all_available_symbols = sorted(list(set(symbols_s + symbols_m)))

# --- END: NEW DYNAMIC DATA LOADING FUNCTION ---

# In data_manager.py

# # --- NEW DYNAMIC DATA LOADING FUNCTION FROM GITHUB ---
# def load_data_from_github(file_template):
#     """
#     Constructs the GitHub raw URL for today's file and attempts to load it.
#     Returns a DataFrame (empty if it fails).
#     """
#     today_str = datetime.now().strftime("%Y%m%d")
#     filename = file_template.format(date_str=today_str)
    
#     # Construct the full raw URL
#     url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{filename}"
    
#     print(f"Attempting to load data from: {url}")
    
#     try:
#         # Use pandas to read directly from the URL. This is the key change.
#         df = pd.read_csv(url)
#         print(f"Successfully loaded {filename} from GitHub.")
#         return df
#     except Exception as e:
#         # This will happen if the file doesn't exist (404 error) or other network issues
#         print(f"Failed to load {filename} from GitHub. Error: {e}")
#         return pd.DataFrame() # Return an empty DataFrame on failure

# In data_manager.py (DELETE the old load function, ADD these two)

# --- NEW SMART DATA LOADING FUNCTIONS ---
def get_v20_signals():
    global v20_signals_cache, V20_CACHE_DATE
    today_date = datetime.now().date()
    if V20_CACHE_DATE != today_date:
        print(f"CACHE MISS: V20 data is stale. Fetching from GitHub for {today_date}...")
        filename = SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date.strftime("%Y%m%d"))
        url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{filename}"
        try:
            v20_signals_cache = pd.read_csv(url, parse_dates=['Buy_Date', 'Sell_Date'])
            V20_CACHE_DATE = today_date
            print(f"CACHE UPDATED: V20 cache updated with {len(v20_signals_cache)} signals.")
        except Exception as e:
            print(f"CACHE ERROR: Failed to load V20 data from GitHub: {e}")
            v20_signals_cache = pd.DataFrame(); V20_CACHE_DATE = None
    return v20_signals_cache

def get_ma_signals():
    global ma_signals_cache, MA_CACHE_DATE
    today_date = datetime.now().date()
    if MA_CACHE_DATE != today_date:
        print(f"CACHE MISS: MA data is stale. Fetching from GitHub for {today_date}...")
        filename = MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date.strftime("%Y%m%d"))
        url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{filename}"
        try:
            ma_signals_cache = pd.read_csv(url, parse_dates=['Date'])
            MA_CACHE_DATE = today_date
            print(f"CACHE UPDATED: MA cache updated with {len(ma_signals_cache)} events.")
        except Exception as e:
            print(f"CACHE ERROR: Failed to load MA data from GitHub: {e}")
            ma_signals_cache = pd.DataFrame(); MA_CACHE_DATE = None
    return ma_signals_cache
