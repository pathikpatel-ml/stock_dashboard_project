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
    # Path for files written to the Render Disk (candle signals, run tracker)
    FIXED_BASE_PATH = os.path.join(RENDER_DISK_MOUNT_BASE, RENDER_DATA_SUBFOLDER)
    if not os.path.exists(FIXED_BASE_PATH):
        try:
            os.makedirs(FIXED_BASE_PATH, exist_ok=True)
            print(f"RENDER: Created data directory on disk: {FIXED_BASE_PATH}")
        except Exception as e:
            print(f"RENDER ERROR: Could not create data directory {FIXED_BASE_PATH}. Error: {e}")
            # If this fails, subsequent file writes will fail.
            # Consider exiting or having a fallback if critical.
            # For now, we'll let it try and fail later if dir creation fails.

    # Name of the growth/symbol list file (assumed to be in the Git repo root)
    SERVER_GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
    # Full path to the growth file located within the deployed application code (Git repo)
    # os.path.dirname(__file__) gives the directory of the current script
    ACTIVE_GROWTH_DF_PATH = os.path.join(os.path.dirname(__file__), SERVER_GROWTH_FILE_NAME)

    if not os.path.exists(ACTIVE_GROWTH_DF_PATH):
        print(f"RENDER CRITICAL ERROR: Growth file '{SERVER_GROWTH_FILE_NAME}' not found at expected repo path: '{ACTIVE_GROWTH_DF_PATH}'")
        # This is a fatal error for Render deployment if the file is missing from the repo
        # You might want to sys.exit(1) here in a real deployment if this happens
else:
    # Local Windows configuration
    FIXED_BASE_PATH = "C:\\Users\\Admin\\Desktop\\mayur\\last qtr profit high ever base on v200 screener\\"
    ACTIVE_GROWTH_DF_PATH = "" # Will be set by input() in local main_script_flow

# File to track the last run date for candle analysis (will be in FIXED_BASE_PATH)
LAST_RUN_DATE_TRACKER_FILE = os.path.join(FIXED_BASE_PATH, "candle_analysis_last_run.txt")
# Global for today's candle analysis filename (will be in FIXED_BASE_PATH)
DYNAMIC_CANDLE_ANALYSIS_FILENAME = ""


# --- Candle Analysis Functions ---
def fetch_historical_data_yf(symbol_nse):
    try:
        stock_ticker = yf.Ticker(symbol_nse)
        hist_data = stock_ticker.history(period="max", interval="1d", auto_adjust=False, actions=True)
        if hist_data.empty: return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        required_ohlc = ['Open', 'High', 'Low', 'Close']
        if not all(col in hist_data.columns for col in required_ohlc): return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=required_ohlc, inplace=True)
        return hist_data
    except Exception: return pd.DataFrame()

def analyze_stock_candles(base_symbol, hist_data_df):
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
    # Uses ACTIVE_GROWTH_DF_PATH (passed as current_growth_file_path)
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
        time.sleep(0.05)
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
    global DYNAMIC_CANDLE_ANALYSIS_FILENAME, ACTIVE_GROWTH_DF_PATH, LAST_RUN_DATE_TRACKER_FILE, FIXED_BASE_PATH
    current_date_str = datetime.now().strftime("%Y%m%d")
    DYNAMIC_CANDLE_ANALYSIS_FILENAME = os.path.join(FIXED_BASE_PATH, f"stock_candle_signals_from_listing_{current_date_str}.csv")
    last_run_date_str = ""
    if os.path.exists(LAST_RUN_DATE_TRACKER_FILE):
        try:
            with open(LAST_RUN_DATE_TRACKER_FILE, 'r') as f: last_run_date_str = f.read().strip()
        except Exception: pass
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
    global DYNAMIC_CANDLE_ANALYSIS_FILENAME, ACTIVE_GROWTH_DF_PATH
    print(f"\n--- Loading Data for Dashboard ---")
    print(f"Dashboard loading candle signals from: {DYNAMIC_CANDLE_ANALYSIS_FILENAME}")
    available_symbols_from_signals = []
    try:
        signals_df_for_dashboard = pd.read_csv(DYNAMIC_CANDLE_ANALYSIS_FILENAME)
        signals_df_for_dashboard['Buy_Date'] = pd.to_datetime(signals_df_for_dashboard['Buy_Date'])
        signals_df_for_dashboard['Sell_Date'] = pd.to_datetime(signals_df_for_dashboard['Sell_Date'])
        if 'Symbol' in signals_df_for_dashboard.columns:
            available_symbols_from_signals = sorted(signals_df_for_dashboard['Symbol'].astype(str).str.strip().dropna().unique())
        print(f"Dashboard: Loaded {len(signals_df_for_dashboard)} signals. Unique symbols from signals: {len(available_symbols_from_signals)}")
    except FileNotFoundError: print(f"Dashboard WARNING: Signals file '{os.path.basename(DYNAMIC_CANDLE_ANALYSIS_FILENAME)}' not found."); signals_df_for_dashboard = pd.DataFrame(columns=['Symbol']); available_symbols_from_signals = []
    except Exception as e: print(f"Dashboard ERROR loading signals file: {e}"); signals_df_for_dashboard = pd.DataFrame(columns=['Symbol']); available_symbols_from_signals = []
    
    print(f"Dashboard loading growth data from: {ACTIVE_GROWTH_DF_PATH}")
    available_symbols_from_growth = []
    if ACTIVE_GROWTH_DF_PATH and os.path.exists(ACTIVE_GROWTH_DF_PATH):
        try:
            growth_df_for_dashboard = pd.read_csv(ACTIVE_GROWTH_DF_PATH)
            if 'Symbol' in growth_df_for_dashboard.columns:
                available_symbols_from_growth = sorted(growth_df_for_dashboard['Symbol'].astype(str).str.strip().dropna().unique())
            print(f"Dashboard: Loaded {len(growth_df_for_dashboard)} companies from growth file. Unique symbols: {len(available_symbols_from_growth)}")
        except Exception as e: print(f"Dashboard ERROR loading growth file: {e}"); growth_df_for_dashboard = pd.DataFrame(columns=['Symbol']); available_symbols_from_growth = []
    else: print(f"Dashboard WARNING: Growth file path '{ACTIVE_GROWTH_DF_PATH}' invalid or file not found."); growth_df_for_dashboard = pd.DataFrame(columns=['Symbol']); available_symbols_from_growth = []

    all_available_symbols_for_dashboard = sorted(list(set(available_symbols_from_signals + available_symbols_from_growth)))
    print(f"Dashboard: TOTAL unique symbols for dropdown: {len(all_available_symbols_for_dashboard)}.")
    return True

def get_nearest_to_buy_data(signals_df_input): # No changes to this function's core logic
    if signals_df_input.empty: return pd.DataFrame()
    if 'Symbol' not in signals_df_input.columns: return pd.DataFrame()
    all_unique_symbols = signals_df_input['Symbol'].dropna().unique()
    if not all_unique_symbols.any(): return pd.DataFrame()
    yf_symbols_to_fetch = [f"{s}.NS" for s in all_unique_symbols]
    dl_market_data = None
    try: dl_market_data = yf.download(yf_symbols_to_fetch, period="5d", progress=False, auto_adjust=False, group_by='ticker', timeout=20)
    except Exception: pass
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
                elif 'Close' in dl_market_data.columns and len(all_unique_symbols) == 1:
                    s = dl_market_data['Close'].dropna(); latest_close = s.iloc[-1] if not s.empty else np.nan
            except Exception: pass
        if pd.isna(latest_close): continue
        prox_pct = ((latest_close - buy_target) / buy_target) * 100
        buy_date_str = pd.to_datetime(signal_row['Buy_Date']).strftime('%Y-%m-%d') if pd.notna(signal_row['Buy_Date']) else 'N/A'
        results.append({'Symbol': symbol, 'Signal Buy Date': buy_date_str, 'Target Buy Price (Low)': round(buy_target, 2), 'Latest Close Price': round(latest_close, 2), 'Proximity to Buy (%)': round(prox_pct, 2), 'Closeness (%)': round(abs(prox_pct), 2), 'Potential Gain (%)': round(signal_row.get('Sequence_Gain_Percent', np.nan), 2)})
    if not results: return pd.DataFrame()
    return pd.DataFrame(results).sort_values(by=['Closeness (%)', 'Symbol', 'Signal Buy Date']).reset_index(drop=True)

def create_app_layout(): # No changes to this function's core logic
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

# --- Dash Callbacks ---
@app.callback(Output('nearest-to-buy-table-container', 'children'), [Input('refresh-nearest-button', 'n_clicks')], [State('proximity-threshold-input', 'value')])
def update_nearest_to_buy_table(n_clicks, proximity_threshold_from_ui): # No changes to this function's core logic
    ctx = dash.callback_context
    if not ctx.triggered and n_clicks == 0: return html.Div(html.P("Click 'Refresh Table' to load.", style={'textAlign': 'center', 'padding': '20px'}), style={'border': '1px dashed #ccc', 'borderRadius': '5px', 'margin': '20px'})
    if signals_df_for_dashboard.empty: return html.P("No signal data available.", style={'color': 'red', 'textAlign': 'center'})
    proximity_threshold = float(proximity_threshold_from_ui if proximity_threshold_from_ui is not None else 20.0)
    all_prox_df = get_nearest_to_buy_data(signals_df_for_dashboard)
    if all_prox_df.empty: return html.P("No proximity data.", style={'textAlign': 'center'})
    display_df = all_prox_df[all_prox_df['Closeness (%)'] <= proximity_threshold].copy()
    if display_df.empty: return html.P(f"No stocks currently within +/-{proximity_threshold}% of signal buy price.", style={'textAlign': 'center'})
    cols = [{"name": i, "id": i} for i in ['Symbol', 'Signal Buy Date', 'Target Buy Price (Low)', 'Latest Close Price', 'Proximity to Buy (%)', 'Potential Gain (%)']]
    return dash_table.DataTable(id='nearest-table', columns=cols, data=display_df.to_dict('records'), page_size=15, style_table={'overflowX': 'auto', 'width': '100%'}, style_cell={'textAlign': 'left', 'padding': '8px', 'fontSize': '14px', 'minWidth': '80px', 'width': '130px', 'maxWidth': '180px', 'border': '1px solid #eee'}, style_header={'backgroundColor': '#e9ecef', 'fontWeight': 'bold', 'borderBottom': '2px solid #dee2e6'}, style_data_conditional=[{'if': {'row_index': 'odd'},'backgroundColor': '#f8f9fa'}], sort_action="native", sort_mode="single", sort_by=[])

@app.callback([Output('price-chart', 'figure'), Output('signals-table-container', 'children')], [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def update_graph_and_table(selected_symbol, start_date_str, end_date_str): # No changes to this function's core logic
    fig = go.Figure(); table_content = html.P("Please select a company.", style={'textAlign': 'center'})
    if not selected_symbol: fig.update_layout(title="Select a Company", xaxis_rangeslider_visible=False, xaxis=dict(visible=False), yaxis=dict(visible=False), plot_bgcolor='rgba(0,0,0,0)'); return fig, html.Div(table_content, style={'border': '1px dashed #ccc', 'borderRadius': '5px', 'padding': '20px', 'margin': '20px'})
    if not start_date_str or not end_date_str: fig.update_layout(title="Select date range.", xaxis_rangeslider_visible=False); return fig, table_content
    symbol_yf = f"{selected_symbol}.NS"
    try:
        start_dt = datetime.strptime(start_date_str.split(' ')[0], '%Y-%m-%d'); end_dt = datetime.strptime(end_date_str.split(' ')[0], '%Y-%m-%d')
        if start_dt > end_dt: fig.update_layout(title="Start date after end date.", xaxis_rangeslider_visible=False); return fig, html.P("Error: Start date after end date.", style={'color': 'red'})
        hist = yf.download(symbol_yf, start=start_dt, end=end_dt+timedelta(days=1), progress=False, auto_adjust=False)
    except Exception: fig.update_layout(title=f"Could not load data for {selected_symbol}", xaxis_rangeslider_visible=False); return fig, html.P(f"Error fetching data for {selected_symbol}.", style={'color': 'red'})
    if hist.empty: fig.update_layout(title=f"No data for {selected_symbol} in range", xaxis_rangeslider_visible=False); return fig, html.P(f"No data for {selected_symbol} in range.")
    fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name=f'{selected_symbol} Price'))
    comp_signals_df = pd.DataFrame()
    if not signals_df_for_dashboard.empty and all(c in signals_df_for_dashboard.columns for c in ['Symbol','Buy_Date','Sell_Date']):
        comp_signals_df = signals_df_for_dashboard[(signals_df_for_dashboard['Symbol']==selected_symbol) & (signals_df_for_dashboard['Buy_Date']>=start_dt) & (signals_df_for_dashboard['Sell_Date']<=end_dt)].copy()
    if not comp_signals_df.empty:
        buys = comp_signals_df.dropna(subset=['Buy_Date','Buy_Price_Low']); sells = comp_signals_df.dropna(subset=['Sell_Date','Sell_Price_High'])
        if not buys.empty: fig.add_trace(go.Scatter(x=buys['Buy_Date'], y=buys['Buy_Price_Low'], mode='markers', marker=dict(color='green',size=10,symbol='triangle-up'), name='Buy', hovertext=[f"Buy: {r['Buy_Price_Low']:.2f}<br>{r['Buy_Date']:%Y-%m-%d}<br>Gain: {r['Sequence_Gain_Percent']:.2f}%" for _,r in buys.iterrows()], hoverinfo='text'))
        if not sells.empty: fig.add_trace(go.Scatter(x=sells['Sell_Date'], y=sells['Sell_Price_High'], mode='markers', marker=dict(color='red',size=10,symbol='triangle-down'), name='Sell', hovertext=[f"Sell: {r['Sell_Price_High']:.2f}<br>{r['Sell_Date']:%Y-%m-%d}<br>Gain: {r['Sequence_Gain_Percent']:.2f}%" for _,r in sells.iterrows()], hoverinfo='text'))
        disp_df = pd.DataFrame({'Buy Date': comp_signals_df['Buy_Date'].dt.strftime('%Y-%m-%d'), 'Buy Price (Low)': comp_signals_df['Buy_Price_Low'].round(2), 'Sell Date': comp_signals_df['Sell_Date'].dt.strftime('%Y-%m-%d'), 'Sell Price (High)': comp_signals_df['Sell_Price_High'].round(2), 'Gain (%)': comp_signals_df['Sequence_Gain_Percent'].round(2), 'Days in Seq.': comp_signals_df['Days_in_Sequence']})
        table_content = dash_table.DataTable(columns=[{"name":i,"id":i} for i in disp_df.columns], data=disp_df.to_dict('records'), page_size=10, style_table={'overflowX':'auto','width':'100%'}, style_cell={'textAlign':'left','padding':'8px','fontSize':'14px'}, style_header={'backgroundColor':'#e9ecef','fontWeight':'bold','borderBottom':'2px solid #dee2e6'}, style_data_conditional=[{'if':{'row_index':'odd'},'backgroundColor':'#f8f9fa'}])
    else: table_content = html.P("No signals for this company in selected date range.", style={'textAlign':'center'})
    fig.update_layout(title=f'Price & Signals: {selected_symbol}', xaxis_title='Date', yaxis_title='Price (INR)', xaxis_rangeslider_visible=True, legend_title_text='Legend', hovermode="x unified", margin=dict(l=40,r=40,t=60,b=40))
    return fig, table_content

# --- Application Entry Point ---
def main_local_interactive_run():
    global ACTIVE_GROWTH_DF_PATH # Allow modification
    print("--- Stock Signal Dashboard Launcher (Local Interactive Mode) ---")
    print(f"Symbol list files should be placed in: {FIXED_BASE_PATH}")
    print("----------------------------------------")
    while True:
        growth_file_name_input = input(f"Enter NAME of symbol list CSV (e.g., my_stocks.csv) in '{FIXED_BASE_PATH}': ")
        if not growth_file_name_input.lower().endswith('.csv'): growth_file_name_input += ".csv"
        # Set ACTIVE_GROWTH_DF_PATH for local run based on input
        ACTIVE_GROWTH_DF_PATH = os.path.join(FIXED_BASE_PATH, growth_file_name_input)
        if os.path.exists(ACTIVE_GROWTH_DF_PATH):
            print(f"Found symbol list file: {ACTIVE_GROWTH_DF_PATH}")
            break
        else:
            print(f"ERROR: File '{growth_file_name_input}' NOT FOUND in '{FIXED_BASE_PATH}'.")
            retry = input("Try again? (yes/no): ").lower()
            if retry != 'yes': print("Exiting application."); sys.exit()
    
    initialize_app_data_and_layout() # This will use the ACTIVE_GROWTH_DF_PATH set above
    print("\n--- Starting Dash Web Server Locally ---")
    print("Open your browser and go to: http://127.0.0.1:8050/")
    print("Press CTRL+C in this window to stop the server.")
    app.run(debug=True)
    print("Application has finished or was closed by the user.")
    input("Press Enter to exit local mode...")

def main_scheduled_task_run():
    global ACTIVE_GROWTH_DF_PATH # Allow modification
    print("--- Running in --update-only mode (Scheduled Task) ---")
    # ACTIVE_GROWTH_DF_PATH is already set for Render context by the logic at the top of the file.
    # For local test of --update-only, it would use the default local FIXED_BASE_PATH and needs a growth file.
    # This assumes SERVER_GROWTH_FILE_NAME is the one to use for scheduled tasks if no other provided.
    if not IS_ON_RENDER and not ACTIVE_GROWTH_DF_PATH: # Local --update-only needs a path
        print("Local --update-only: ACTIVE_GROWTH_DF_PATH not set. Please run interactively first or hardcode a default for local testing of this mode.")
        default_local_growth_file = "Master_company_market_trend_analysis_20250525.csv" # Example
        ACTIVE_GROWTH_DF_PATH = os.path.join(FIXED_BASE_PATH, default_local_growth_file)
        print(f"Using default local growth file for update: {ACTIVE_GROWTH_DF_PATH}")

    if not ACTIVE_GROWTH_DF_PATH or not os.path.exists(ACTIVE_GROWTH_DF_PATH):
        print(f"CRITICAL ERROR for Scheduled Task: Growth file path '{ACTIVE_GROWTH_DF_PATH}' is invalid or file does not exist.")
        sys.exit(1)

    if ensure_candle_analysis_updated(): # Uses ACTIVE_GROWTH_DF_PATH
        print("Scheduled task: Candle analysis update successful.")
    else:
        print("Scheduled task: Candle analysis update FAILED.")
    sys.exit() # Exit after the task

def main_wsgi_server_initialization():
    # This function is intended to be called when the WSGI server (Gunicorn on Render) imports the module.
    # It ensures data is loaded and the layout is set.
    # ACTIVE_GROWTH_DF_PATH is set by the IS_ON_RENDER block at the top.
    print(f"--- Initializing App Data for WSGI Server (e.g., Render) ---")
    print(f"WSGI: Using growth file: {ACTIVE_GROWTH_DF_PATH}")
    print(f"WSGI: Data will be written/read from disk path: {FIXED_BASE_PATH}")
    initialize_app_data_and_layout()
    print(f"--- App Data and Layout Initialized for WSGI Server. {len(all_available_symbols_for_dashboard)} symbols in dropdown. ---")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run Stock Dashboard or update candle data.")
    parser.add_argument('--update-only', action='store_true', help='Only run candle analysis update and exit.')
    args = parser.parse_args()

    if args.update_only:
        main_scheduled_task_run()
    elif not IS_ON_RENDER: # If not update-only and not on Render, it's a local interactive run
        main_local_interactive_run()
    # If IS_ON_RENDER and not --update-only, this script is being imported by the WSGI server.
    # The WSGI server will then use the 'server' object (app.server).
    # The initialization for Render should happen *before* the WSGI server tries to use 'app.layout'.
    # So, if it's on Render and not an update task, we initialize here too.
    elif IS_ON_RENDER:
        main_wsgi_server_initialization()