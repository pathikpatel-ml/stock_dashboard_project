# data_manager.py
import os
import pandas as pd
from datetime import datetime
import numpy as np
import yfinance as yf

# --- Configuration (Unchanged) ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"
MA_SIGNALS_FILENAME_TEMPLATE = "ma_signals_data_{date_str}.csv"

# --- Global DataFrames (Data Cache) ---
signals_df = pd.DataFrame()
ma_signals_df = pd.DataFrame()
v20_processed_df = pd.DataFrame()
all_available_symbols = []

# --- NEW: Global variables to track loaded file dates ---
LOADED_V20_FILE_DATE = None
LOADED_MA_FILE_DATE = None

# --- V20 Helper Function (Unchanged) ---
def process_v20_signals(v20_signals_df):
    if v20_signals_df.empty: return pd.DataFrame()
    df_to_process = v20_signals_df.copy()
    df_to_process['Buy_Date'] = pd.to_datetime(df_to_process['Buy_Date'], errors='coerce')
    df_to_process.dropna(subset=['Buy_Date'], inplace=True)
    latest_signals = df_to_process.sort_values('Buy_Date', ascending=False).groupby('Symbol').first().reset_index()
    unique_symbols = latest_signals['Symbol'].dropna().unique()
    if not unique_symbols.any(): return pd.DataFrame()
    print(f"PROCESS V20: Fetching live prices for {len(unique_symbols)} symbols...")
    yf_symbols = [f"{s}.NS" for s in unique_symbols]
    latest_prices_map = {}
    data = yf.download(tickers=yf_symbols, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=30)
    if data is not None and not data.empty:
        for sym_ns in yf_symbols:
            base_sym = sym_ns.replace(".NS", "").upper()
            price_series = None
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if (sym_ns, 'Close') in data.columns: price_series = data[(sym_ns, 'Close')]
                elif isinstance(data, dict):
                    symbol_data = data.get(sym_ns)
                    if symbol_data is not None and 'Close' in symbol_data.columns: price_series = symbol_data['Close']
                elif 'Close' in data.columns and len(yf_symbols) == 1: price_series = data['Close']
                if price_series is not None and not price_series.dropna().empty: latest_prices_map[base_sym] = price_series.dropna().iloc[-1]
            except Exception: continue
    results = []
    for _, row in latest_signals.iterrows():
        symbol, cmp_val = str(row.get('Symbol','')).upper(), latest_prices_map.get(str(row.get('Symbol','')).upper())
        buy_target, sell_target = row.get('Buy_Price_Low'), row.get('Sell_Price_High')
        if pd.isna(cmp_val) or pd.isna(buy_target) or buy_target == 0: continue
        if pd.notna(sell_target) and cmp_val >= sell_target: continue
        prox_pct = ((cmp_val - buy_target) / buy_target) * 100
        results.append({'Symbol': symbol, 'Signal Buy Date': pd.to_datetime(row.get('Buy_Date')).strftime('%Y-%m-%d'), 'Target Buy Price (Low)': round(buy_target, 2), 'Sell_Price_High': round(sell_target, 2), 'Latest Close Price': round(cmp_val, 2), 'Proximity to Buy (%)': round(prox_pct, 2), 'Closeness (%)': round(abs(prox_pct), 2), 'Potential Gain (%)': round(row.get('Sequence_Gain_Percent', np.nan), 2)})
    return pd.DataFrame(results).sort_values(by=['Closeness (%)']).reset_index(drop=True)

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

# --- Main Data Loading Function (MODIFIED) ---
def load_data_if_stale():
    """
    Checks if the data in memory is for today. If not, it reloads.
    This function will be called from the UI callbacks.
    """
    global signals_df, ma_signals_df, all_available_symbols, v20_processed_df
    global LOADED_V20_FILE_DATE, LOADED_MA_FILE_DATE
    
    today_date = datetime.now().date()
    
    # Check and reload V20 data if stale
    if LOADED_V20_FILE_DATE != today_date:
        print(f"DATA MANAGER: V20 data is stale (or not loaded). Attempting to load for {today_date}...")
        v20_filename = os.path.join(REPO_BASE_PATH, SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date.strftime("%Y%m%d")))
        if os.path.exists(v20_filename):
            try:
                signals_df = pd.read_csv(v20_filename, parse_dates=['Buy_Date', 'Sell_Date'])
                v20_processed_df = process_v20_signals(signals_df)
                LOADED_V20_FILE_DATE = today_date
                print(f"DATA MANAGER: Successfully loaded and processed {len(v20_processed_df)} V20 signals.")
            except Exception as e:
                print(f"DATA MANAGER ERROR: Failed to load V20 file '{v20_filename}': {e}")
                signals_df = pd.DataFrame() # Clear on error
                v20_processed_df = pd.DataFrame()
        else:
            print(f"DATA MANAGER: V20 file not found for today.")
            signals_df = pd.DataFrame()
            v20_processed_df = pd.DataFrame()

    # Check and reload MA data if stale
    if LOADED_MA_FILE_DATE != today_date:
        print(f"DATA MANAGER: MA data is stale. Attempting to load for {today_date}...")
        ma_filename = os.path.join(REPO_BASE_PATH, MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_date.strftime("%Y%m%d")))
        if os.path.exists(ma_filename):
            try:
                ma_signals_df = pd.read_csv(ma_filename, parse_dates=['Date'])
                LOADED_MA_FILE_DATE = today_date
                print(f"DATA MANAGER: Successfully loaded {len(ma_signals_df)} MA events.")
            except Exception as e:
                print(f"DATA MANAGER ERROR: Failed to load MA file '{ma_filename}': {e}")
                ma_signals_df = pd.DataFrame()
        else:
            print(f"DATA MANAGER: MA file not found for today.")
            ma_signals_df = pd.DataFrame()
            
    # Always update the symbol list after loading
    symbols_s = signals_df['Symbol'].dropna().unique().tolist() if not signals_df.empty else []
    symbols_m = ma_signals_df['Symbol'].dropna().unique().tolist() if not ma_signals_df.empty else []
    all_available_symbols = sorted(list(set(symbols_s + symbols_m)))
