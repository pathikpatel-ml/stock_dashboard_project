#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
from datetime import datetime, date, timedelta
import numpy as np
import sys
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import yfinance as yf

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"
ATH_TRIGGERS_FILENAME_TEMPLATE = "ath_triggers_data_{date_str}.csv"
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv" # Source for chart dropdown symbols
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

# --- Global DataFrames & Dash App Initialization ---
signals_df_for_dashboard = pd.DataFrame()
ath_triggers_df_for_dashboard = pd.DataFrame()
growth_df_for_dashboard = pd.DataFrame()
all_available_symbols_for_dashboard = []

LOADED_SIGNALS_FILE_DISPLAY_NAME = "N/A" # Will be updated in load_data
LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME = "N/A" # Will be updated in load_data

# Initialize Dash app. CSS from 'assets' folder is automatically picked up.
app = dash.Dash(__name__) # Removed external_stylesheets to rely on assets/custom_styles.css
app.title = "Stock Analysis Dashboard"
server = app.server

# --- Data Loading Logic ---
def load_data_for_dashboard_from_repo():
    global signals_df_for_dashboard, ath_triggers_df_for_dashboard, growth_df_for_dashboard
    global all_available_symbols_for_dashboard
    global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME

    print(f"\n--- DASH APP: Loading Pre-calculated Data ---")
    current_date_str = datetime.now().strftime("%Y%m%d")

    # 1. Load Candle Signals Data
    expected_signals_filename = SIGNALS_FILENAME_TEMPLATE.format(date_str=current_date_str)
    signals_file_path = os.path.join(REPO_BASE_PATH, expected_signals_filename)
    if os.path.exists(signals_file_path):
        try:
            signals_df_for_dashboard = pd.read_csv(signals_file_path)
            signals_df_for_dashboard['Buy_Date'] = pd.to_datetime(signals_df_for_dashboard['Buy_Date'], errors='coerce')
            signals_df_for_dashboard['Sell_Date'] = pd.to_datetime(signals_df_for_dashboard['Sell_Date'], errors='coerce')
            LOADED_SIGNALS_FILE_DISPLAY_NAME = expected_signals_filename # Store full name for status
        except Exception as e:
            print(f"DASH ERROR loading signals file '{expected_signals_filename}': {e}")
            signals_df_for_dashboard = pd.DataFrame()
            LOADED_SIGNALS_FILE_DISPLAY_NAME = f"{expected_signals_filename} (Error)"
    else:
        print(f"DASH WARNING: Daily signals file '{expected_signals_filename}' NOT FOUND.")
        signals_df_for_dashboard = pd.DataFrame()
        LOADED_SIGNALS_FILE_DISPLAY_NAME = f"{expected_signals_filename} (Not Found)"

    # 2. Load ATH Triggers Data
    expected_ath_triggers_filename = ATH_TRIGGERS_FILENAME_TEMPLATE.format(date_str=current_date_str)
    ath_triggers_file_path = os.path.join(REPO_BASE_PATH, expected_ath_triggers_filename)
    if os.path.exists(ath_triggers_file_path):
        try:
            ath_triggers_df_for_dashboard = pd.read_csv(ath_triggers_file_path)
            if 'CMP Proximity to Buy (%)' in ath_triggers_df_for_dashboard.columns and \
               'ClosenessAbs (%)' not in ath_triggers_df_for_dashboard.columns:
                proximity_numeric = pd.to_numeric(ath_triggers_df_for_dashboard['CMP Proximity to Buy (%)'], errors='coerce')
                ath_triggers_df_for_dashboard['ClosenessAbs (%)'] = proximity_numeric.abs()
            elif 'ClosenessAbs (%)' not in ath_triggers_df_for_dashboard.columns:
                 ath_triggers_df_for_dashboard['ClosenessAbs (%)'] = np.inf
            LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME = expected_ath_triggers_filename
        except Exception as e:
            print(f"DASH ERROR loading ATH triggers file '{expected_ath_triggers_filename}': {e}")
            ath_triggers_df_for_dashboard = pd.DataFrame()
            LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME = f"{expected_ath_triggers_filename} (Error)"
    else:
        print(f"DASH WARNING: Daily ATH triggers file '{expected_ath_triggers_filename}' NOT FOUND.")
        ath_triggers_df_for_dashboard = pd.DataFrame()
        LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME = f"{expected_ath_triggers_filename} (Not Found)"
        
    # 3. Populate symbols for individual analysis dropdown
    symbols_from_signals = []
    if not signals_df_for_dashboard.empty and 'Symbol' in signals_df_for_dashboard.columns:
        symbols_from_signals = signals_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist()
    symbols_from_ath = []
    if not ath_triggers_df_for_dashboard.empty and 'Symbol' in ath_triggers_df_for_dashboard.columns:
        symbols_from_ath = ath_triggers_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist()
    symbols_from_growth_file = []
    if os.path.exists(ACTIVE_GROWTH_DF_PATH):
        try:
            growth_df_for_dashboard = pd.read_csv(ACTIVE_GROWTH_DF_PATH)
            if 'Symbol' in growth_df_for_dashboard.columns:
                symbols_from_growth_file = growth_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist()
        except Exception as e: print(f"DASH WARNING: Could not load growth file '{ACTIVE_GROWTH_DF_PATH}': {e}")
    
    combined_symbols = set(symbols_from_signals + symbols_from_ath + symbols_from_growth_file)
    all_available_symbols_for_dashboard = sorted(list(filter(None, combined_symbols))) # Filter out potential None/empty strings
    print(f"DASH APP: Symbols for dropdown: {len(all_available_symbols_for_dashboard)}. Signals: {len(signals_df_for_dashboard)}, ATH Triggers: {len(ath_triggers_df_for_dashboard)}")
    return True

# --- yfinance Data Fetching (ONLY for Individual Stock Analysis Chart) ---
def fetch_historical_data_for_graph(symbol_nse_with_suffix):
    try:
        stock_ticker = yf.Ticker(symbol_nse_with_suffix)
        hist_data = stock_ticker.history(period="5y", interval="1d", auto_adjust=False, actions=False, timeout=15)
        if hist_data.empty: return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        required_ohlc = ['Open', 'High', 'Low', 'Close']
        if not all(col in hist_data.columns for col in required_ohlc): return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=required_ohlc, inplace=True)
        return hist_data
    except Exception as e: print(f"DASH ERROR fetching chart data for {symbol_nse_with_suffix}: {e}"); return pd.DataFrame()

# --- Helper for "Stocks Nearest to Buy Signal" ---
def get_nearest_to_buy_from_loaded_signals(signals_df_local):
    if signals_df_local.empty or 'Symbol' not in signals_df_local.columns: return pd.DataFrame()
    df_to_process = signals_df_local.copy()
    if 'Latest Close Price' not in df_to_process.columns:
        print("DASH (NearestBuy): 'Latest Close Price' not in signals file. Fetching CMPs...")
        unique_symbols = df_to_process['Symbol'].dropna().astype(str).str.upper().unique()
        if not unique_symbols.any(): return pd.DataFrame()
        yf_symbols = [f"{s}.NS" for s in unique_symbols]; latest_prices_map = {}
        chunk_size = 50
        for i in range(0, len(yf_symbols), chunk_size):
            chunk = yf_symbols[i:i + chunk_size]
            try:
                data = yf.download(tickers=chunk, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=20) # Shorter period for CMP
                if not data.empty:
                    for sym_ns in chunk:
                        base_sym = sym_ns.replace(".NS", "")
                        try:
                            price_series = data.get((sym_ns, 'Close')) if isinstance(data.columns, pd.MultiIndex) else data.get('Close')
                            if price_series is not None and not price_series.dropna().empty: latest_prices_map[base_sym] = price_series.dropna().iloc[-1]
                        except Exception: pass
            except Exception as e_yf: print(f"DASH (NearestBuy): yf.download error: {e_yf}")
        df_to_process['Latest Close Price'] = df_to_process['Symbol'].astype(str).str.upper().map(latest_prices_map)
        df_to_process.dropna(subset=['Latest Close Price'], inplace=True)
    if df_to_process.empty: return pd.DataFrame()
    results = []
    for _idx, row in df_to_process.iterrows():
        symbol, buy_target, cmp = str(row.get('Symbol','')).upper(), row.get('Buy_Price_Low'), row.get('Latest Close Price')
        if not symbol or pd.isna(buy_target) or buy_target == 0 or pd.isna(cmp): continue
        prox_pct = ((cmp - buy_target) / buy_target) * 100
        buy_date_str = pd.to_datetime(row.get('Buy_Date')).strftime('%Y-%m-%d') if pd.notna(row.get('Buy_Date')) else 'N/A'
        results.append({'Symbol': symbol, 'Signal Buy Date': buy_date_str, 'Target Buy Price (Low)': round(buy_target, 2),
                        'Latest Close Price': round(cmp, 2), 'Proximity to Buy (%)': round(prox_pct, 2),
                        'Closeness (%)': round(abs(prox_pct), 2),
                        'Potential Gain (%)': round(row.get('Sequence_Gain_Percent', np.nan), 2)})
    if not results: return pd.DataFrame()
    return pd.DataFrame(results).sort_values(by=['Closeness (%)', 'Symbol']).reset_index(drop=True)

# --- App Layout Creation Function ---
def create_app_layout():
    global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME, all_available_symbols_for_dashboard
    
    def get_status_text(file_display_name_full):
        if "(Not Found)" in file_display_name_full: return "Not Found"
        if "(Error)" in file_display_name_full: return "Error Loading"
        if "N/A" == file_display_name_full : return "Unavailable"
        # Try to extract date for "Loaded" status
        try: # Example: stock_candle_signals_from_listing_20240608.csv -> 20240608
            date_part = file_display_name_full.split('_')[-1].split('.')[0]
            datetime.strptime(date_part, "%Y%m%d") # Validate if it's a date
            return f"Loaded ({date_part})"
        except: return "Loaded (Unknown Date)" # Fallback if parsing fails

    signals_status_text = get_status_text(LOADED_SIGNALS_FILE_DISPLAY_NAME)
    ath_status_text = get_status_text(LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME)

    return html.Div([
        html.H1("Stock Analysis Dashboard"),
        html.Div(html.P(f"Daily Signals: {signals_status_text} | ATH Triggers: {ath_status_text}"), id="app-subtitle"),

        html.Div([
            html.H3("Stocks Nearest to Buy Signal"),
            html.Div([
                html.Label("Max Proximity to Buy (%):"),
                dcc.Input(id='proximity-threshold-input', type='number', value=20, min=0, max=100, step=1, style={'width':'60px'}),
                html.Button('Apply Filter', id='refresh-nearest-button')
            ], className='control-bar'),
            dcc.Loading(id="loading-nearest-table", type="circle", children=[html.Div(id='nearest-to-buy-table-container')])
        ], className='section-container'),

        html.Div([
            html.H3("Individual Stock Analysis"),
            html.Div([
                dcc.Dropdown(id='company-dropdown',
                             options=[{'label': sym, 'value': sym} for sym in all_available_symbols_for_dashboard],
                             value=all_available_symbols_for_dashboard[0] if all_available_symbols_for_dashboard else None,
                             placeholder="Select Company", style={'width': '300px', 'minWidth':'250px'}),
                dcc.DatePickerRange(id='date-picker-range', min_date_allowed=date(2000,1,1), max_date_allowed=date.today() + timedelta(days=1),
                                    initial_visible_month=date.today(), start_date=(date.today()-timedelta(days=365*2)),
                                    end_date=date.today(), display_format='YYYY-MM-DD')
            ], className='control-bar'),
            dcc.Loading(id="loading-chart", type="circle", children=dcc.Graph(id='price-chart')),
            html.H4("Signals for Selected Company"),
            dcc.Loading(id="loading-signals-table", type="circle", children=[html.Div(id='signals-table-container')])
        ], className='section-container'),

        html.Div([
            html.H3("Strategic ATH Triggers"),
            html.Div([
                html.Label("Max Proximity to ATH Buy Trigger (%):"),
                dcc.Input(id='ath-proximity-filter-input', type='number', value=10, min=0, max=100, step=1, style={'width': '60px'}),
                html.Button('Apply ATH Filter', id='refresh-ath-triggers-button')
            ], className='control-bar'),
            dcc.Loading(id="loading-ath-triggers-table-multi", type="circle", children=[html.Div(id='ath-triggers-table-container-multi')])
        ], className='section-container'),
        html.Footer("Stock Analysis Dashboard © " + str(datetime.now().year), 
                    style={'textAlign':'center', 'marginTop':'40px', 'padding':'15px', 'fontSize':'0.8em', 'color':'#888', 'borderTop':'1px solid #eee'})
    ])

# --- Callbacks ---
# Section 1: Stocks Nearest to Buy
@app.callback(Output('nearest-to-buy-table-container', 'children'), [Input('refresh-nearest-button', 'n_clicks')], [State('proximity-threshold-input', 'value')], prevent_initial_call=False)
def update_nearest_to_buy_table(_n_clicks, proximity_value):
    global signals_df_for_dashboard
    if signals_df_for_dashboard.empty: return html.P(f"Daily signals data unavailable. Status: {get_status_text(LOADED_SIGNALS_FILE_DISPLAY_NAME)}", className="status-message error")
    
    processed_signals_df = get_nearest_to_buy_from_loaded_signals(signals_df_for_dashboard.copy())
    if processed_signals_df.empty: return html.P("No stocks meet criteria after processing.", className="status-message warning")
    
    try: proximity_threshold = float(proximity_value)
    except: proximity_threshold = 20.0 # Default
    if not (0 <= proximity_threshold <= 100): proximity_threshold = 20.0

    filtered_df = processed_signals_df[processed_signals_df['Closeness (%)'] <= proximity_threshold]
    if filtered_df.empty: return html.P(f"No stocks within {proximity_threshold}% of buy signal.", className="status-message")
    
    return dash_table.DataTable(data=filtered_df.to_dict('records'), columns=[{'name': i, 'id': i} for i in filtered_df.columns if i != 'Closeness (%)'], page_size=15, sort_action="native", filter_action="native")

# Section 2: Individual Stock Chart
@app.callback(Output('price-chart', 'figure'), [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def update_graph(selected_company, start_date_str, end_date_str):
    if not selected_company: return go.Figure().update_layout(title="Select a Company", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    try: start_date_obj, end_date_obj = pd.to_datetime(start_date_str).normalize(), pd.to_datetime(end_date_str).normalize()
    except: return go.Figure().update_layout(title="Invalid Date Range", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    
    hist_df = fetch_historical_data_for_graph(f"{selected_company.upper()}.NS")
    if hist_df.empty: return go.Figure().update_layout(title=f"No Data for {selected_company}", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    
    df_filtered_chart = hist_df[(hist_df['Date'] >= start_date_obj) & (hist_df['Date'] <= end_date_obj)]
    if df_filtered_chart.empty: return go.Figure().update_layout(title=f"No Data for {selected_company} in Range", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    
    fig = go.Figure(data=[go.Candlestick(x=df_filtered_chart['Date'], open=df_filtered_chart['Open'], high=df_filtered_chart['High'], low=df_filtered_chart['Low'], close=df_filtered_chart['Close'], name='OHLC')])
    
    if not signals_df_for_dashboard.empty and 'Symbol' in signals_df_for_dashboard.columns:
        signals_on_chart = signals_df_for_dashboard[signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()].copy()
        for _, sig_row in signals_on_chart.iterrows():
            buy_dt, sell_dt = sig_row.get('Buy_Date'), sig_row.get('Sell_Date')
            if pd.isna(buy_dt): continue
            show_sig = (pd.notna(sell_dt) and buy_dt <= end_date_obj and sell_dt >= start_date_obj) or \
                       (pd.isna(sell_dt) and buy_dt <= end_date_obj)
            if show_sig:
                x_coords, y_coords = [buy_dt], [sig_row['Buy_Price_Low']]
                if pd.notna(sell_dt): x_coords.append(sell_dt); y_coords.append(sig_row['Sell_Price_High'])
                fig.add_trace(go.Scatter(x=x_coords, y=y_coords, mode='lines+markers', name=f"Signal ({'Closed' if pd.notna(sell_dt) else 'Open'})", line=dict(color='purple', width=1, dash='dot'), marker=dict(size=7)))
                fig.add_annotation(x=buy_dt, y=sig_row['Buy_Price_Low'], text="B", bgcolor="lightgreen", ax=0, ay=-20, font_size=10)
                if pd.notna(sell_dt): fig.add_annotation(x=sell_dt, y=sig_row['Sell_Price_High'], text="S", bgcolor="pink", ax=0, ay=20, font_size=10)
    
    fig.update_layout(title=f'{selected_company} Price Chart', xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

# Section 2: Signals Table
@app.callback(Output('signals-table-container', 'children'), [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def update_signals_table(selected_company, start_date_str, end_date_str):
    global signals_df_for_dashboard
    if not selected_company: return html.P("Select a company.", className="status-message")
    try: filter_start, filter_end = pd.to_datetime(start_date_str).normalize(), pd.to_datetime(end_date_str).normalize()
    except: return html.P("Invalid date range.", className="status-message error")

    if signals_df_for_dashboard.empty: return html.P(f"Signals data unavailable. Status: {get_status_text(LOADED_SIGNALS_FILE_DISPLAY_NAME)}", className="status-message error")
    
    company_sigs = signals_df_for_dashboard[signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()].copy()
    if company_sigs.empty: return html.P(f"No signals for {selected_company}.", className="status-message")

    valid_buy = company_sigs['Buy_Date'].notna()
    closed_filt = valid_buy & company_sigs['Sell_Date'].notna() & (company_sigs['Buy_Date'] <= filter_end) & (company_sigs['Sell_Date'] >= filter_start)
    open_filt = valid_buy & company_sigs['Sell_Date'].isna() & (company_sigs['Buy_Date'] <= filter_end)
    df_disp = company_sigs[closed_filt | open_filt].copy()

    if df_disp.empty: return html.P(f"No signals for {selected_company} in selected date range.", className="status-message")
    
    for col in ['Buy_Date', 'Sell_Date']:
        if col in df_disp.columns and pd.api.types.is_datetime64_any_dtype(df_disp[col]):
            df_disp[col] = df_disp[col].dt.strftime('%Y-%m-%d')
    df_disp.fillna('N/A', inplace=True)
    return dash_table.DataTable(data=df_disp.to_dict('records'), columns=[{'name': i, 'id': i} for i in df_disp.columns], page_size=10, sort_action="native")

# Section 3: Strategic ATH Triggers
@app.callback(Output('ath-triggers-table-container-multi', 'children'), [Input('refresh-ath-triggers-button', 'n_clicks')], [State('ath-proximity-filter-input', 'value')], prevent_initial_call=False)
def update_ath_triggers_multi_table(_n_clicks, proximity_value):
    global ath_triggers_df_for_dashboard
    if ath_triggers_df_for_dashboard.empty: return html.P(f"ATH Triggers data unavailable. Status: {get_status_text(LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME)}", className="status-message error")
    
    try: proximity_threshold = float(proximity_value)
    except: proximity_threshold = 10.0
    if not (0 <= proximity_threshold <= 100): proximity_threshold = 10.0

    if 'ClosenessAbs (%)' not in ath_triggers_df_for_dashboard.columns:
        return html.P("Required 'ClosenessAbs (%)' column missing in ATH data.", className="status-message error")
        
    data_to_filter = ath_triggers_df_for_dashboard.copy()
    filtered_df = data_to_filter[data_to_filter['ClosenessAbs (%)'] <= proximity_threshold]
    filtered_df_display = filtered_df.drop(columns=['ClosenessAbs (%)'], errors='ignore')

    if filtered_df_display.empty: return html.P(f"No companies found within {proximity_threshold}% of ATH Buy Trigger.", className="status-message")
    return dash_table.DataTable(data=filtered_df_display.to_dict('records'), columns=[{'name': i, 'id': i} for i in filtered_df_display.columns], page_size=20, sort_action="native", filter_action="native")

# --- Application Initialization & Run ---
if __name__ == '__main__':
    print("DASH APP: Initializing application...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout # Assign layout after data load for dropdown population
    print("DASH APP: App layout assigned. Application ready.")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
else: # For Gunicorn or other WSGI servers
    print("DASH APP: Initializing application for WSGI server...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout
    server = app.server # Expose server for Gunicorn
    print("DASH APP: WSGI application initialized.")
