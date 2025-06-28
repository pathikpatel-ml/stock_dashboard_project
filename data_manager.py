# data_manager.py
import os
import pandas as pd
from datetime import datetime
import numpy as np
import yfinance as yf

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"
MA_SIGNALS_FILENAME_TEMPLATE = "ma_signals_data_{date_str}.csv"
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

# --- Global DataFrames (Data Cache) ---
signals_df = pd.DataFrame()
ma_signals_df = pd.DataFrame()
growth_df = pd.DataFrame()
all_available_symbols = []

# This is the cache for the processed V20 data!
v20_processed_df = pd.DataFrame()

# --- V20 Helper Function (Original Logic, now for caching) ---
def process_v20_signals(v20_signals_df):
    """
    The slow function that gets latest signals and fetches live prices.
    This logic is taken directly from your working file and now populates a cache.
    It correctly checks if the sell price has been hit.
    """
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
        symbol = str(row.get('Symbol','')).upper()
        cmp_val = latest_prices_map.get(symbol)
        buy_target, sell_target = row.get('Buy_Price_Low'), row.get('Sell_Price_High')
        
        if pd.isna(cmp_val) or pd.isna(buy_target) or buy_target == 0: continue
        if pd.notna(sell_target) and cmp_val >= sell_target: continue

        prox_pct = ((cmp_val - buy_target) / buy_target) * 100
        results.append({
            'Symbol': symbol, 'Signal Buy Date': pd.to_datetime(row.get('Buy_Date')).strftime('%Y-%m-%d'),
            'Target Buy Price (Low)': round(buy_target, 2), 'Sell_Price_High': round(sell_target, 2),
            'Latest Close Price': round(cmp_val, 2), 'Proximity to Buy (%)': round(prox_pct, 2),
            'Closeness (%)': round(abs(prox_pct), 2),
            'Potential Gain (%)': round(row.get('Sequence_Gain_Percent', np.nan), 2)
        })
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
    primary_list = [{'Symbol': s, 'Company Name': d.get('Company Name'), 'Type': d.get('Type'), 'Market Cap': d.get('MarketCap'), 'Primary Buy Date': d['Date'].strftime('%Y-%m-%d'), 'Primary Buy Price': round(d['Price'], 2), 'Current Price': round(latest_prices_map.get(f"{s}.NS"), 2), 'Difference (%)': round(((latest_prices_map.get(f"{s}.NS") - d['Price']) / d['Price']) * 100, 2) if d.get('Price',0) != 0 else 0} for s, d in active_primary.items() if f"{s}.NS" in latest_prices_map]
    secondary_list = [{'Symbol': s, 'Company Name': d.get('Company Name'), 'Type': d.get('Type'), 'Market Cap': d.get('MarketCap'), 'Secondary Buy Date': d['Date'].strftime('%Y-%m-%d'), 'Secondary Buy Price': round(d['Price'], 2), 'Current Price': round(latest_prices_map.get(f"{s}.NS"), 2), 'Difference (%)': round(((latest_prices_map.get(f"{s}.NS") - d['Price']) / d['Price']) * 100, 2) if d.get('Price',0) != 0 else 0} for s, d in active_secondary.items() if f"{s}.NS" in latest_prices_map]
    return pd.DataFrame(primary_list), pd.DataFrame(secondary_list)

# --- Main Data Loading Function ---
def load_data_for_dashboard_from_repo():
    global signals_df, ma_signals_df, growth_df, all_available_symbols, v20_processed_df
    print("\n--- DASH APP: Loading and Processing Data on Startup ---")
    current_date_str = datetime.now().strftime("%Y%m%d")
    
    signals_file = os.path.join(REPO_BASE_PATH, SIGNALS_FILENAME_TEMPLATE.format(date_str=current_date_str))
    if os.path.exists(signals_file):
        signals_df = pd.read_csv(signals_file, parse_dates=['Buy_Date', 'Sell_Date'])
        v20_processed_df = process_v20_signals(signals_df)
        print(f"DASH APP: Loaded and processed {len(v20_processed_df)} active V20 signals.")
    else:
        print(f"DASH WARNING: V20 signals file not found for today.")

    ma_file = os.path.join(REPO_BASE_PATH, MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=current_date_str))
    if os.path.exists(ma_file):
        ma_signals_df = pd.read_csv(ma_file, parse_dates=['Date'])
        print(f"DASH APP: Loaded {len(ma_signals_df)} MA signal events.")
    else:
        print(f"DASH WARNING: MA signals file not found for today.")

    symbols_s = signals_df['Symbol'].dropna().unique().tolist() if not signals_df.empty else []
    symbols_m = ma_signals_df['Symbol'].dropna().unique().tolist() if not ma_signals_df.empty else []
    all_available_symbols = sorted(list(set(symbols_s + symbols_m)))
