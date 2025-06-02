#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
import time
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np
import sys
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import argparse # For command-line arguments

# --- Environment Detection & Path Configuration ---
IS_ON_RENDER = os.environ.get('RENDER') == 'true'
RENDER_DISK_MOUNT_BASE = "/opt/render/project/src/" # Base provided by Render for disks
RENDER_DATA_SUBFOLDER = "csv_data" # Subfolder on the disk we will use

if IS_ON_RENDER:
    FIXED_BASE_PATH = os.path.join(RENDER_DISK_MOUNT_BASE, RENDER_DATA_SUBFOLDER)
    if not os.path.exists(FIXED_BASE_PATH):
        try:
            os.makedirs(FIXED_BASE_PATH, exist_ok=True)
            print(f"RENDER: Created data directory on disk: {FIXED_BASE_PATH}")
        except Exception as e:
            print(f"RENDER ERROR: Could not create data directory {FIXED_BASE_PATH}. Error: {e}")
            # Consider exiting if critical, but for now, let it proceed

    SERVER_GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
    # Path to the growth file in the Git repo (read-only for the app)
    ACTIVE_GROWTH_DF_PATH = os.path.join(os.path.dirname(__file__), SERVER_GROWTH_FILE_NAME)

    if not os.path.exists(ACTIVE_GROWTH_DF_PATH):
        print(f"RENDER CRITICAL ERROR: Growth file '{SERVER_GROWTH_FILE_NAME}' not found at expected repo path: '{ACTIVE_GROWTH_DF_PATH}'")
        # This could be fatal. You might want to sys.exit(1)
else:
    # Local Windows configuration
    FIXED_BASE_PATH = "C:\\Users\\Admin\\Desktop\\mayur\\last qtr profit high ever base on v200 screener\\"
    ACTIVE_GROWTH_DF_PATH = "" # Will be set by input() in local main_script_flow

LAST_RUN_DATE_TRACKER_FILE = os.path.join(FIXED_BASE_PATH, "candle_analysis_last_run.txt")
DYNAMIC_CANDLE_ANALYSIS_FILENAME = "" # Will be set dynamically


# --- Candle Analysis Functions --- (Keep these as they are)
def fetch_historical_data_yf(symbol_nse):
    # ... (your existing code)
    try:
        stock_ticker = yf.Ticker(symbol_nse)
        # Use a shorter timeout for individual stock fetches to avoid overly long waits
        hist_data = stock_ticker.history(period="max", interval="1d", auto_adjust=False, actions=True, timeout=10) # Added timeout
        if hist_data.empty: return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        required_ohlc = ['Open', 'High', 'Low', 'Close']
        if not all(col in hist_data.columns for col in required_ohlc): return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=required_ohlc, inplace=True)
        return hist_data
    except Exception as e:
        print(f"Error fetching {symbol_nse}: {e}") # Print error for debugging
        return pd.DataFrame()

def analyze_stock_candles(base_symbol, hist_data_df):
    # ... (your existing code)
    signals = []
    required_cols = ['Date', 'Open', 'Close', 'Low', 'High']
    if hist_data_df.empty or not all(col in hist_data_df.columns for col in required_cols): return signals
    df_full_history = hist_data_df.copy()
    for col in ['Open', 'Close', 'Low', 'High']: df_full_history[col] = pd.to_numeric(df_full_history[col], errors='coerce')
    df_full_history.dropna(subset=['Open', 'Close', 'Low', 'High'], inplace=True)
    df_full_history['GreenCandle'] = df_full_history['Close'] > df_full_history['Open']
    df_full_history['Block'] = (df_full_history['GreenCandle'].diff() != 0).cumsum()
    green_sequences_grouped = df_full_history[df_full_history['GreenCandle']].groupby('Block')
    if green_sequences_grouped.ngroups == 0: return signals
    for block_id, sequence_df in green_sequences_grouped:
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
                if future_buy_condition_met_date is None and future_row['Low'] <= buy_price_low: future_buy_condition_met_date = future_row['Date']
                if future_buy_condition_met_date is not None and future_row['Date'] >= future_buy_condition_met_date:
                    if future_row['High'] >= sell_price_high: is_triggered_in_future = True; break
        if is_triggered_in_future: continue
        signals.append({'Symbol': base_symbol, 'Buy_Date': buy_date_dt.strftime('%Y-%m-%d'), 'Buy_Price_Low': round(buy_price_low, 2), 'Sell_Date': sell_date_dt.strftime('%Y-%m-%d'), 'Sell_Price_High': round(sell_price_high, 2), 'Sequence_Gain_Percent': round(gain_percentage, 2), 'Days_in_Sequence': len(sequence_df)})
    return signals

def generate_candle_analysis_file(current_growth_file_path, output_candle_file_path):
    # ... (your existing code)
    print(f"\n--- Starting Candle Analysis Generation ---")
    print(f"Using input symbol list from: {current_growth_file_path}")
    if not os.path.exists(current_growth_file_path):
        print(f"ERROR: Symbol list file '{current_growth_file_path}' NOT FOUND.")
        return False
    try: growth_df = pd.read_csv(current_growth_file_path)
    except Exception as e: print(f"ERROR reading symbol list file '{current_growth_file_path}': {e}"); return False
    if 'Symbol' not in growth_df.columns: print(f"ERROR: 'Symbol' column missing in '{current_growth_file_path}'."); return False
    if growth_df.empty: print("Symbol list file is empty."); return False
    all_candle_signals, symbols_for_analysis = [], growth_df["Symbol"].dropna().astype(str).unique()
    total_symbols = len(symbols_for_analysis)
    print(f"Analyzing candles for {total_symbols} unique symbols. This may take some time...")
    for i, symbol_short in enumerate(symbols_for_analysis):
        symbol_nse = f"{symbol_short.upper().strip()}.NS"
        progress_percent = ((i + 1) / total_symbols) * 100
        sys.stdout.write(f"\rProcessing: [{i+1}/{total_symbols}] {symbol_short} ({progress_percent:.1f}%)"); sys.stdout.flush()
        hist_data = fetch_historical_data_yf(symbol_nse)
        if not hist_data.empty:
            signals = analyze_stock_candles(symbol_short, hist_data)
            if signals: all_candle_signals.extend(signals)
        time.sleep(0.1) # Small delay, yfinance might have rate limits
    sys.stdout.write("\nDone processing symbols.\n"); sys.stdout.flush()
    if all_candle_signals:
        signals_df_generated = pd.DataFrame(all_candle_signals).sort_values(by=['Symbol', 'Buy_Date']).reset_index(drop=True)
        try:
            signals_df_generated.to_csv(output_candle_file_path, index=False)
            print(f"Saved {len(signals_df_generated)} candle signals to '{output_candle_file_path}'")
            return True
        except Exception as e: print(f"ERROR saving candle signals to '{output_candle_file_path}': {e}"); return False
    else:
        print("No candle signals generated.")
        try:
            pd.DataFrame(columns=['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence']).to_csv(output_candle_file_path, index=False)
            print(f"Saved empty candle analysis file to '{output_candle_file_path}'.")
            return True
        except Exception as e: print(f"ERROR saving empty candle signals file: {e}"); return False

def ensure_candle_analysis_updated():
    # This function is primarily for the CRON JOB or LOCAL runs
    global DYNAMIC_CANDLE_ANALYSIS_FILENAME, ACTIVE_GROWTH_DF_PATH, LAST_RUN_DATE_TRACKER_FILE, FIXED_BASE_PATH
    current_date_str = datetime.now().strftime("%Y%m%d")
    # This sets the global DYNAMIC_CANDLE_ANALYSIS_FILENAME that generate_candle_analysis_file will use
    DYNAMIC_CANDLE_ANALYSIS_FILENAME = os.path.join(FIXED_BASE_PATH, f"stock_candle_signals_from_listing_{current_date_str}.csv")
    last_run_date_str = ""
    if os.path.exists(LAST_RUN_DATE_TRACKER_FILE):
        try:
            with open(LAST_RUN_DATE_TRACKER_FILE, 'r') as f: last_run_date_str = f.read().strip()
        except Exception as e: print(f"Warning: Could not read last run tracker: {e}")

    needs_update = False
    if not last_run_date_str: print("No record of last run. Update needed."); needs_update = True
    elif last_run_date_str != current_date_str: print(f"Date changed (last: {last_run_date_str}, current: {current_date_str}). Update needed."); needs_update = True
    elif not os.path.exists(DYNAMIC_CANDLE_ANALYSIS_FILENAME): print(f"Today's candle file ('{os.path.basename(DYNAMIC_CANDLE_ANALYSIS_FILENAME)}') missing. Update needed."); needs_update = True
    else: print(f"Today's candle file ('{os.path.basename(DYNAMIC_CANDLE_ANALYSIS_FILENAME)}') exists. Skipping generation."); return True

    if needs_update:
        print(f"Attempting to use growth file: {ACTIVE_GROWTH_DF_PATH}")
        if not ACTIVE_GROWTH_DF_PATH or not os.path.exists(ACTIVE_GROWTH_DF_PATH):
            print(f"CRITICAL ERROR: Growth file path '{ACTIVE_GROWTH_DF_PATH}' is invalid or file doesn't exist. Cannot generate candle analysis.")
            return False
        # generate_candle_analysis_file uses the global DYNAMIC_CANDLE_ANALYSIS_FILENAME set above
        if generate_candle_analysis_file(ACTIVE_GROWTH_DF_PATH, DYNAMIC_CANDLE_ANALYSIS_FILENAME):
            try:
                with open(LAST_RUN_DATE_TRACKER_FILE, 'w') as f: f.write(current_date_str)
                print(f"Updated last run date tracker to: {current_date_str}")
                return True
            except Exception as e: print(f"ERROR writing to last run date tracker: {e}"); return False
        else: print("Candle analysis generation FAILED."); return False
    return True

# --- Global DataFrames & Dash App Initialization ---
signals_df_for_dashboard = pd.DataFrame()
growth_df_for_dashboard = pd.DataFrame()
all_available_symbols_for_dashboard = []

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.title = "Stock Signal Dashboard"
server = app.server # Expose Flask server for WSGI

def load_data_for_dashboard():
    global signals_df_for_dashboard, growth_df_for_dashboard, all_available_symbols_for_dashboard
    global DYNAMIC_CANDLE_ANALYSIS_FILENAME, ACTIVE_GROWTH_DF_PATH # DYNAMIC_CANDLE_ANALYSIS_FILENAME should be set before calling this

    print(f"\n--- Loading Data for Dashboard ---")
    if not DYNAMIC_CANDLE_ANALYSIS_FILENAME:
        # This should ideally be set by initialize_app_for_server or ensure_candle_analysis_updated
        # Fallback to construct it if not set, for robustness.
        current_date_str = datetime.now().strftime("%Y%m%d")
        DYNAMIC_CANDLE_ANALYSIS_FILENAME = os.path.join(FIXED_BASE_PATH, f"stock_candle_signals_from_listing_{current_date_str}.csv")
        print(f"Dashboard WARNING: DYNAMIC_CANDLE_ANALYSIS_FILENAME was not pre-set. Using: {DYNAMIC_CANDLE_ANALYSIS_FILENAME}")

    print(f"Dashboard loading candle signals from: {DYNAMIC_CANDLE_ANALYSIS_FILENAME}")
    available_symbols_from_signals = []
    try:
        signals_df_for_dashboard = pd.read_csv(DYNAMIC_CANDLE_ANALYSIS_FILENAME)
        signals_df_for_dashboard['Buy_Date'] = pd.to_datetime(signals_df_for_dashboard['Buy_Date'])
        signals_df_for_dashboard['Sell_Date'] = pd.to_datetime(signals_df_for_dashboard['Sell_Date'])
        if 'Symbol' in signals_df_for_dashboard.columns:
            available_symbols_from_signals = sorted(signals_df_for_dashboard['Symbol'].astype(str).str.strip().dropna().unique())
        print(f"Dashboard: Loaded {len(signals_df_for_dashboard)} signals. Unique symbols from signals: {len(available_symbols_from_signals)}")
    except FileNotFoundError:
        print(f"Dashboard WARNING: Signals file '{os.path.basename(DYNAMIC_CANDLE_ANALYSIS_FILENAME)}' not found. This is normal if the cron job hasn't run yet today or ever.")
        signals_df_for_dashboard = pd.DataFrame(columns=['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence']) # Ensure schema
        available_symbols_from_signals = []
    except Exception as e:
        print(f"Dashboard ERROR loading signals file '{DYNAMIC_CANDLE_ANALYSIS_FILENAME}': {e}")
        signals_df_for_dashboard = pd.DataFrame(columns=['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence']) # Ensure schema
        available_symbols_from_signals = []
    
    print(f"Dashboard loading growth data from: {ACTIVE_GROWTH_DF_PATH}")
    available_symbols_from_growth = []
    if ACTIVE_GROWTH_DF_PATH and os.path.exists(ACTIVE_GROWTH_DF_PATH):
        try:
            growth_df_for_dashboard = pd.read_csv(ACTIVE_GROWTH_DF_PATH)
            if 'Symbol' in growth_df_for_dashboard.columns:
                available_symbols_from_growth = sorted(growth_df_for_dashboard['Symbol'].astype(str).str.strip().dropna().unique())
            print(f"Dashboard: Loaded {len(growth_df_for_dashboard)} companies from growth file. Unique symbols: {len(available_symbols_from_growth)}")
        except Exception as e:
            print(f"Dashboard ERROR loading growth file: {e}")
            growth_df_for_dashboard = pd.DataFrame(columns=['Symbol']) # Ensure schema
            available_symbols_from_growth = []
    else:
        print(f"Dashboard WARNING: Growth file path '{ACTIVE_GROWTH_DF_PATH}' invalid or file not found.")
        growth_df_for_dashboard = pd.DataFrame(columns=['Symbol']) # Ensure schema
        available_symbols_from_growth = []

    all_available_symbols_for_dashboard = sorted(list(set(available_symbols_from_signals + available_symbols_from_growth)))
    print(f"Dashboard: TOTAL unique symbols for dropdown: {len(all_available_symbols_for_dashboard)}.")
    return True

def get_nearest_to_buy_data(signals_df_input):
    # ... (your existing code)
    if signals_df_input.empty: return pd.DataFrame()
    if 'Symbol' not in signals_df_input.columns: return pd.DataFrame()
    all_unique_symbols = signals_df_input['Symbol'].dropna().unique()
    if not all_unique_symbols.any(): return pd.DataFrame()
    yf_symbols_to_fetch = [f"{s}.NS" for s in all_unique_symbols]
    dl_market_data = None
    try: 
        # Be mindful of yfinance download limits if this table is refreshed very often by many users
        dl_market_data = yf.download(yf_symbols_to_fetch, period="5d", progress=False, auto_adjust=False, group_by='ticker', timeout=30) # Increased timeout slightly
    except Exception as e:
        print(f"Error in get_nearest_to_buy_data yf.download: {e}") # Log error
        pass # Allow to proceed, will result in NaNs or empty data
    results = []
    for _, signal_row in signals_df_input.iterrows():
        symbol = signal_row['Symbol']
        if pd.isna(symbol) or 'Buy_Price_Low' not in signal_row or pd.isna(signal_row['Buy_Price_Low']) or signal_row['Buy_Price_Low'] == 0: continue
        buy_target = signal_row['Buy_Price_Low']; latest_close = np.nan; yf_key = f"{symbol}.NS"
        if dl_market_data is not None and not dl_market_data.empty:
            try:
                if isinstance(dl_market_data.columns, pd.MultiIndex):
                    if (yf_key, 'Close') in dl_market_data.columns:
                        s = dl_market_data[(yf_key, 'Close')].dropna(); latest_close = s.iloc[-1] if not s.empty else np.nan
                elif 'Close' in dl_market_data.columns and len(all_unique_symbols) == 1: # Single symbol download doesn't have MultiIndex
                    s = dl_market_data['Close'].dropna(); latest_close = s.iloc[-1] if not s.empty else np.nan
            except Exception as e:
                 # print(f"Minor error processing {symbol} in get_nearest_to_buy_data: {e}") # Can be noisy
                 pass
        if pd.isna(latest_close): continue # Skip if no latest_close
        prox_pct = ((latest_close - buy_target) / buy_target) * 100
        buy_date_str = pd.to_datetime(signal_row['Buy_Date']).strftime('%Y-%m-%d') if pd.notna(signal_row['Buy_Date']) else 'N/A'
        results.append({'Symbol': symbol, 'Signal Buy Date': buy_date_str, 'Target Buy Price (Low)': round(buy_target, 2), 'Latest Close Price': round(latest_close, 2), 'Proximity to Buy (%)': round(prox_pct, 2), 'Closeness (%)': round(abs(prox_pct), 2), 'Potential Gain (%)': round(signal_row.get('Sequence_Gain_Percent', np.nan), 2)})
    if not results: return pd.DataFrame()
    return pd.DataFrame(results).sort_values(by=['Closeness (%)', 'Symbol', 'Signal Buy Date']).reset_index(drop=True)

def create_app_layout():
    # ... (your existing code is fine, it uses all_available_symbols_for_dashboard)
    global ACTIVE_GROWTH_DF_PATH, DYNAMIC_CANDLE_ANALYSIS_FILENAME, all_available_symbols_for_dashboard
    return html.Div([
        html.H1("Stock Signal Dashboard", style={'textAlign': 'center', 'color': '#333'}),
        html.Div(f"Input Symbol List: {os.path.basename(ACTIVE_GROWTH_DF_PATH if ACTIVE_GROWTH_DF_PATH else 'N/A')}", style={'textAlign': 'center', 'fontSize': 'small'}),
        html.Div(f"Candle Signals From: {os.path.basename(DYNAMIC_CANDLE_ANALYSIS_FILENAME if DYNAMIC_CANDLE_ANALYSIS_FILENAME else 'N/A')}", style={'textAlign': 'center', 'marginBottom': '20px', 'fontSize': 'small'}),
        html.Div([
            html.H3("Stocks Nearest to Buy Signal", style={'textAlign': 'center'}),
            html.Div([html.Label("Max Display Proximity (% from Buy Price, +/-):"), dcc.Input(id='proximity-threshold-input', type='number', value=20, min=0, step=1, style={'marginLeft': '10px', 'marginRight': '20px'}), html.Button('Refresh Table', id='refresh-nearest-button', n_clicks=0, style={'backgroundColor': '#4CAF50', 'color': 'white', 'border': 'none', 'padding': '8px 12px', 'cursor': 'pointer'})], style={'textAlign': 'center', 'marginBottom': '10px'}),
            dcc.Loading(id="loading-nearest-table", type="circle", children=[html.Div(id='nearest-to-buy-table-container', style={'margin': 'auto', 'width': '90%'})])
        ], style={'marginBottom': '30px', 'padding': '20px', 'border': '1px solid #ddd', 'borderRadius': '8px', 'backgroundColor': '#f9f9f9'}),
        html.H3("Individual Stock Analysis", style={'textAlign': 'center', 'marginTop': '30px'}),
        html.Div([dcc.Dropdown(id='company-dropdown', options=[{'label': sym, 'value': sym} for sym in all_available_symbols_for_dashboard], value=all_available_symbols_for_dashboard[0] if all_available_symbols_for_dashboard else None, placeholder="Select Company", style={'width': '350px', 'display': 'inline-block', 'marginRight': '20px'}), dcc.DatePickerRange(id='date-picker-range', min_date_allowed=datetime(2000,1,1), max_date_allowed=datetime.now()+timedelta(days=1), initial_visible_month=datetime.now(), start_date=(datetime.now()-timedelta(days=365*1)).strftime('%Y-%m-%d'), end_date=datetime.now().strftime('%Y-%m-%d'), style={'display': 'inline-block'})], style={'marginBottom': '20px', 'textAlign': 'center'}),
        dcc.Loading(id="loading-chart", type="circle", children=dcc.Graph(id='price-chart')),
        html.H4("Signals for Selected Company:", style={'marginTop': '20px', 'textAlign': 'center'}),
        html.Div(id='signals-table-container', style={'margin': 'auto', 'width': '90%'})
    ])

# --- Dash Callbacks --- (Keep these as they are, they use the global dataframes)
@app.callback(Output('nearest-to-buy-table-container', 'children'), [Input('refresh-nearest-button', 'n_clicks')], [State('proximity-threshold-input', 'value')])
def update_nearest_to_buy_table(n_clicks, proximity_threshold_from_ui):
    # ... (your existing code)
    ctx = dash.callback_context
    # Allow initial load without click if desired, or keep as is
    if not ctx.triggered and n_clicks == 0 : # and not app.show_table_on_init: # (if you add such a flag)
         return html.Div(html.P("Click 'Refresh Table' to load proximity data.", style={'textAlign': 'center', 'padding': '20px'}), style={'border': '1px dashed #ccc', 'borderRadius': '5px', 'margin': '20px'})

    if signals_df_for_dashboard.empty: return html.P("No signal data available to calculate proximity. The daily data generation might not have run yet.", style={'color': 'red', 'textAlign': 'center'})
    
    proximity_threshold = float(proximity_threshold_from_ui if proximity_threshold_from_ui is not None else 20.0)
    
    # Fetch fresh market data for proximity check
    all_prox_df = get_nearest_to_buy_data(signals_df_for_dashboard) # This function now fetches yfinance data

    if all_prox_df.empty: return html.P("Could not retrieve current market prices or no signals to process.", style={'textAlign': 'center'})
    
    display_df = all_prox_df[all_prox_df['Closeness (%)'] <= proximity_threshold].copy()
    if display_df.empty: return html.P(f"No stocks currently within +/-{proximity_threshold}% of signal buy price.", style={'textAlign': 'center'})
    
    cols_to_display = ['Symbol', 'Signal Buy Date', 'Target Buy Price (Low)', 'Latest Close Price', 'Proximity to Buy (%)', 'Potential Gain (%)']
    # Filter display_df to only include necessary columns for the table to avoid sending too much data to DataTable
    display_df_subset = display_df[cols_to_display]

    cols = [{"name": i, "id": i} for i in cols_to_display]
    return dash_table.DataTable(id='nearest-table', columns=cols, data=display_df_subset.to_dict('records'), page_size=15, style_table={'overflowX': 'auto', 'width': '100%'}, style_cell={'textAlign': 'left', 'padding': '8px', 'fontSize': '14px', 'minWidth': '80px', 'width': '130px', 'maxWidth': '180px', 'border': '1px solid #eee'}, style_header={'backgroundColor': '#e9ecef', 'fontWeight': 'bold', 'borderBottom': '2px solid #dee2e6'}, style_data_conditional=[{'if': {'row_index': 'odd'},'backgroundColor': '#f8f9fa'}], sort_action="native", sort_mode="single", sort_by=[])


@app.callback([Output('price-chart', 'figure'), Output('signals-table-container', 'children')], [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def update_graph_and_table(selected_symbol, start_date_str, end_date_str):
    # ... (your existing code)
    fig = go.Figure(); table_content = html.P("Please select a company.", style={'textAlign': 'center'})
    if not selected_symbol: fig.update_layout(title="Select a Company", xaxis_rangeslider_visible=False, xaxis=dict(visible=False), yaxis=dict(visible=False), plot_bgcolor='rgba(0,0,0,0)'); return fig, html.Div(table_content, style={'border': '1px dashed #ccc', 'borderRadius': '5px', 'padding': '20px', 'margin': '20px'})
    if not start_date_str or not end_date_str: fig.update_layout(title="Select date range.", xaxis_rangeslider_visible=False); return fig, table_content
    symbol_yf = f"{selected_symbol}.NS"
    try:
        start_dt = datetime.strptime(start_date_str.split(' ')[0], '%Y-%m-%d'); end_dt = datetime.strptime(end_date_str.split(' ')[0], '%Y-%m-%d')
        if start_dt > end_dt: fig.update_layout(title="Start date after end date.", xaxis_rangeslider_visible=False); return fig, html.P("Error: Start date after end date.", style={'color': 'red'})
        hist = yf.download(symbol_yf, start=start_dt, end=end_dt+timedelta(days=1), progress=False, auto_adjust=False, timeout=15) # Added timeout
    except Exception as e: fig.update_layout(title=f"Could not load data for {selected_symbol}", xaxis_rangeslider_visible=False); print(f"YF download error for {selected_symbol}: {e}"); return fig, html.P(f"Error fetching data for {selected_symbol}.", style={'color': 'red'})
    if hist.empty: fig.update_layout(title=f"No data for {selected_symbol} in range", xaxis_rangeslider_visible=False); return fig, html.P(f"No data for {selected_symbol} in range.")
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name=f'{selected_symbol} Price'))
    comp_signals_df = pd.DataFrame()
    if not signals_df_for_dashboard.empty and all(c in signals_df_for_dashboard.columns for c in ['Symbol','Buy_Date','Sell_Date']):
        # Ensure Buy_Date and Sell_Date are datetime for comparison
        temp_signals_df = signals_df_for_dashboard.copy()
        temp_signals_df['Buy_Date'] = pd.to_datetime(temp_signals_df['Buy_Date'])
        temp_signals_df['Sell_Date'] = pd.to_datetime(temp_signals_df['Sell_Date'])
        comp_signals_df = temp_signals_df[(temp_signals_df['Symbol']==selected_symbol) & (temp_signals_df['Buy_Date']>=start_dt) & (temp_signals_df['Sell_Date']<=end_dt)].copy()
    
    if not comp_signals_df.empty:
        buys = comp_signals_df.dropna(subset=['Buy_Date','Buy_Price_Low']); sells = comp_signals_df.dropna(subset=['Sell_Date','Sell_Price_High'])
        if not buys.empty: fig.add_trace(go.Scatter(x=buys['Buy_Date'], y=buys['Buy_Price_Low'], mode='markers', marker=dict(color='green',size=10,symbol='triangle-up'), name='Buy', hovertext=[f"Buy: {r['Buy_Price_Low']:.2f}<br>{pd.to_datetime(r['Buy_Date']):%Y-%m-%d}<br>Gain: {r['Sequence_Gain_Percent']:.2f}%" for _,r in buys.iterrows()], hoverinfo='text'))
        if not sells.empty: fig.add_trace(go.Scatter(x=sells['Sell_Date'], y=sells['Sell_Price_High'], mode='markers', marker=dict(color='red',size=10,symbol='triangle-down'), name='Sell', hovertext=[f"Sell: {r['Sell_Price_High']:.2f}<br>{pd.to_datetime(r['Sell_Date']):%Y-%m-%d}<br>Gain: {r['Sequence_Gain_Percent']:.2f}%" for _,r in sells.iterrows()], hoverinfo='text'))
        
        # Prepare dataframe for display, ensuring correct date formatting
        disp_df_data = {
            'Buy Date': pd.to_datetime(comp_signals_df['Buy_Date']).dt.strftime('%Y-%m-%d'), 
            'Buy Price (Low)': comp_signals_df['Buy_Price_Low'].round(2), 
            'Sell Date': pd.to_datetime(comp_signals_df['Sell_Date']).dt.strftime('%Y-%m-%d'), 
            'Sell Price (High)': comp_signals_df['Sell_Price_High'].round(2), 
            'Gain (%)': comp_signals_df['Sequence_Gain_Percent'].round(2), 
            'Days in Seq.': comp_signals_df['Days_in_Sequence']
        }
        disp_df = pd.DataFrame(disp_df_data)
        table_content = dash_table.DataTable(columns=[{"name":i,"id":i} for i in disp_df.columns], data=disp_df.to_dict('records'), page_size=10, style_table={'overflowX':'auto','width':'100%'}, style_cell={'textAlign':'left','padding':'8px','fontSize':'14px'}, style_header={'backgroundColor':'#e9ecef','fontWeight':'bold','borderBottom':'2px solid #dee2e6'}, style_data_conditional=[{'if':{'row_index':'odd'},'backgroundColor':'#f8f9fa'}])
    else: table_content = html.P("No signals for this company in selected date range.", style={'textAlign':'center'})
    fig.update_layout(title=f'Price & Signals: {selected_symbol}', xaxis_title='Date', yaxis_title='Price (INR)', xaxis_rangeslider_visible=True, legend_title_text='Legend', hovermode="x unified", margin=dict(l=40,r=40,t=60,b=40))
    return fig, table_content

# --- Application Initialization Logic ---
def initialize_app_for_server(is_update_only_mode=False):
    """Main initialization sequence for data and layout."""
    global ACTIVE_GROWTH_DF_PATH, DYNAMIC_CANDLE_ANALYSIS_FILENAME

    print(f"SERVER INIT: Starting data initialization. IS_ON_RENDER: {IS_ON_RENDER}, UpdateOnlyMode: {is_update_only_mode}")
    print(f"SERVER INIT: Using growth file from repo: {ACTIVE_GROWTH_DF_PATH}")
    print(f"SERVER INIT: Data disk path for CSVs: {FIXED_BASE_PATH}")

    if is_update_only_mode: # This is for CRON JOB or local --update-only
        print("SERVER INIT: Running in data update mode (ensure_candle_analysis_updated).")
        if not ensure_candle_analysis_updated():
            print("SERVER INIT ERROR: ensure_candle_analysis_updated FAILED in update-only mode.")
            # DYNAMIC_CANDLE_ANALYSIS_FILENAME might not be set or file might be missing
            # For cron, we might sys.exit(1) here. For now, it will try to load_data_for_dashboard with potentially no file.
    else: # This is for WEB SERVER (local or Render)
        print("SERVER INIT: Running in web server mode. Will NOT run ensure_candle_analysis_updated().")
        # For web server, DYNAMIC_CANDLE_ANALYSIS_FILENAME needs to point to today's expected file.
        # The cron job is responsible for creating this file.
        current_date_str = datetime.now().strftime("%Y%m%d")
        DYNAMIC_CANDLE_ANALYSIS_FILENAME = os.path.join(FIXED_BASE_PATH, f"stock_candle_signals_from_listing_{current_date_str}.csv")
        print(f"SERVER INIT (Web): Expecting candle data file (from cron/previous run): {DYNAMIC_CANDLE_ANALYSIS_FILENAME}")
        # If running locally NOT in update-only mode, you might still want to generate data if missing
        if not IS_ON_RENDER and not os.path.exists(DYNAMIC_CANDLE_ANALYSIS_FILENAME):
            print("SERVER INIT (Local Web): Today's data file not found. Attempting to generate.")
            if not ensure_candle_analysis_updated(): # This will set DYNAMIC_CANDLE_ANALYSIS_FILENAME again
                 print("SERVER INIT WARNING (Local Web): Could not generate candle analysis data.")
            # ensure_candle_analysis_updated sets DYNAMIC_CANDLE_ANALYSIS_FILENAME based on current date.

    load_data_for_dashboard() # This will try to load DYNAMIC_CANDLE_ANALYSIS_FILENAME
    
    # Only assign layout if not in update_only_mode (cron job doesn't need a layout)
    if not is_update_only_mode:
        app.layout = create_app_layout() # Assign layout to the global app instance
        print(f"SERVER INIT: App layout assigned. {len(all_available_symbols_for_dashboard)} symbols in dropdown.")
    else:
        print("SERVER INIT: Skipping layout assignment for update-only mode.")


# --- Entry Point Logic ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run Stock Dashboard or update candle data.")
    parser.add_argument('--update-only', action='store_true', help='Only run candle analysis update and exit.')
    args = parser.parse_args()

    if args.update_only:
        # This is for the Render Cron Job or local `python script.py --update-only`
        print("MAIN: --update-only flag detected.")
        # Set ACTIVE_GROWTH_DF_PATH if it's local --update-only and wasn't set (e.g., no prior interactive run)
        if not IS_ON_RENDER and not ACTIVE_GROWTH_DF_PATH:
            print("MAIN (Local --update-only): ACTIVE_GROWTH_DF_PATH not set. Using default or prompting.")
            # You might want to hardcode a default master list for local cron simulation or prompt
            default_local_growth_filename = "Master_company_market_trend_analysis.csv" # Ensure this exists or change
            temp_path = os.path.join(FIXED_BASE_PATH, default_local_growth_filename)
            if os.path.exists(temp_path):
                ACTIVE_GROWTH_DF_PATH = temp_path
            else: # Fallback to repo version if local fixed path one doesn't exist
                ACTIVE_GROWTH_DF_PATH = os.path.join(os.path.dirname(__file__), SERVER_GROWTH_FILE_NAME)

            if not os.path.exists(ACTIVE_GROWTH_DF_PATH):
                 print(f"CRITICAL ERROR (Local --update-only): Growth file not found at {ACTIVE_GROWTH_DF_PATH}")
                 sys.exit(1)
            print(f"MAIN (Local --update-only): Using growth file: {ACTIVE_GROWTH_DF_PATH}")

        initialize_app_for_server(is_update_only_mode=True) # Will run ensure_candle_analysis_updated
        print("MAIN: --update-only processing complete.")
        sys.exit(0) # Clean exit for cron job
    
    else: # Not --update-only: could be local interactive or WSGI server import
        if not IS_ON_RENDER: # Local interactive run
            print("MAIN: No --update-only flag, running in local interactive mode.")
            # Prompt for growth file for local run
            while True:
                growth_file_name_input = input(f"Enter NAME of symbol list CSV (e.g., my_stocks.csv) in '{FIXED_BASE_PATH}' (or type 'repo' for default): ")
                if growth_file_name_input.lower() == 'repo':
                    ACTIVE_GROWTH_DF_PATH = os.path.join(os.path.dirname(__file__), SERVER_GROWTH_FILE_NAME)
                    if os.path.exists(ACTIVE_GROWTH_DF_PATH):
                        print(f"Using repo growth file: {ACTIVE_GROWTH_DF_PATH}")
                        break
                    else:
                        print(f"ERROR: Default repo growth file '{SERVER_GROWTH_FILE_NAME}' NOT FOUND.")
                        # continue or exit
                elif growth_file_name_input:
                    if not growth_file_name_input.lower().endswith('.csv'): growth_file_name_input += ".csv"
                    temp_path = os.path.join(FIXED_BASE_PATH, growth_file_name_input)
                    if os.path.exists(temp_path):
                        ACTIVE_GROWTH_DF_PATH = temp_path
                        print(f"Found symbol list file: {ACTIVE_GROWTH_DF_PATH}")
                        break
                    else:
                        print(f"ERROR: File '{growth_file_name_input}' NOT FOUND in '{FIXED_BASE_PATH}'.")
                
                retry = input("Try again? (yes/no): ").lower()
                if retry != 'yes': print("Exiting application."); sys.exit()
            
            initialize_app_for_server(is_update_only_mode=False) # Will run ensure_candle_analysis if file missing, then load, then set layout
            print("\n--- Starting Dash Web Server Locally ---")
            print("Open your browser and go to: http://127.0.0.1:8050/") # Default Dash port
            app.run(debug=True) # Default port 8050
        else:
            # IS_ON_RENDER and not --update-only: This means Gunicorn is importing this __main__ block.
            # This case should ideally not be hit if Gunicorn directly imports 'server'.
            # The `elif IS_ON_RENDER:` block (outside of __main__) should handle Gunicorn import.
            # However, to be safe:
            print("RENDER WSGI MAIN IMPORT: Initializing application (should ideally be caught by module-level import)...")
            initialize_app_for_server(is_update_only_mode=False) # Sets DYNAMIC_CANDLE_ANALYSIS_FILENAME, loads data, sets layout
            print("RENDER WSGI MAIN IMPORT: Application initialized.")

elif IS_ON_RENDER: # This means the file is being imported by Gunicorn (its __name__ is not '__main__')
    print("RENDER WSGI MODULE LOAD: Initializing application...")
    # is_update_only_mode is False because Gunicorn is not for updating data, only serving.
    initialize_app_for_server(is_update_only_mode=False) # Sets DYNAMIC_CANDLE_ANALYSIS_FILENAME, loads data, sets layout
    print("RENDER WSGI MODULE LOAD: Application initialized.")
