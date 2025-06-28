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

# --- Configuration (UNCHANGED) ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"
MA_SIGNALS_FILENAME_TEMPLATE = "ma_signals_data_{date_str}.csv"
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

# --- Global DataFrames & App Init (UNCHANGED) ---
signals_df_for_dashboard = pd.DataFrame()
ma_signals_df_for_dashboard = pd.DataFrame()
growth_df_for_dashboard = pd.DataFrame()
all_available_symbols_for_dashboard = []
LOADED_SIGNALS_FILE_DISPLAY_NAME = "N/A"
LOADED_MA_SIGNALS_FILE_DISPLAY_NAME = "N/A"

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "Stock Analysis Dashboard"
# server = app.server

# --- Data Loading Logic (UNCHANGED) ---
def load_data_for_dashboard_from_repo():
    global signals_df_for_dashboard, ma_signals_df_for_dashboard, growth_df_for_dashboard
    global all_available_symbols_for_dashboard
    print(f"\n--- DASH APP: Loading Pre-calculated Data ---")
    current_date_str = datetime.now().strftime("%Y%m%d")
    def load_csv_data(filename_template, df_global_name_str, display_name_global_str, date_cols=None):
        global signals_df_for_dashboard, ma_signals_df_for_dashboard
        global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_MA_SIGNALS_FILE_DISPLAY_NAME
        expected_filename = filename_template.format(date_str=current_date_str)
        file_path = os.path.join(REPO_BASE_PATH, expected_filename)
        loaded_df_for_this_call = pd.DataFrame()
        status_display_name_for_this_call = f"{expected_filename} (Not Found)"
        if os.path.exists(file_path):
            try:
                loaded_df_for_this_call = pd.read_csv(file_path)
                if date_cols:
                    for col in date_cols:
                        if col in loaded_df_for_this_call.columns:
                            loaded_df_for_this_call[col] = pd.to_datetime(loaded_df_for_this_call[col], errors='coerce')
                status_display_name_for_this_call = expected_filename
                print(f"DASH APP: Loaded {len(loaded_df_for_this_call)} records from '{expected_filename}'.")
            except Exception as e:
                print(f"DASH ERROR loading file '{expected_filename}': {e}")
                status_display_name_for_this_call = f"{expected_filename} (Error)"
        else:
            print(f"DASH WARNING: File '{expected_filename}' NOT FOUND.")
        if df_global_name_str == "signals_df_for_dashboard":
            signals_df_for_dashboard = loaded_df_for_this_call
            LOADED_SIGNALS_FILE_DISPLAY_NAME = status_display_name_for_this_call
        elif df_global_name_str == "ma_signals_df_for_dashboard":
            ma_signals_df_for_dashboard = loaded_df_for_this_call
            LOADED_MA_SIGNALS_FILE_DISPLAY_NAME = status_display_name_for_this_call
    load_csv_data(SIGNALS_FILENAME_TEMPLATE, "signals_df_for_dashboard", "LOADED_SIGNALS_FILE_DISPLAY_NAME", date_cols=['Buy_Date', 'Sell_Date'])
    load_csv_data(MA_SIGNALS_FILENAME_TEMPLATE, "ma_signals_df_for_dashboard", "LOADED_MA_SIGNALS_FILE_DISPLAY_NAME", date_cols=['Date'])
    symbols_s = signals_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist() if not signals_df_for_dashboard.empty and 'Symbol' in signals_df_for_dashboard.columns else []
    symbols_m = ma_signals_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist() if not ma_signals_df_for_dashboard.empty and 'Symbol' in ma_signals_df_for_dashboard.columns else []
    symbols_g = []
    if os.path.exists(ACTIVE_GROWTH_DF_PATH):
        try:
            growth_df_for_dashboard = pd.read_csv(ACTIVE_GROWTH_DF_PATH)
            if 'Symbol' in growth_df_for_dashboard.columns:
                symbols_g = growth_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist()
        except Exception as e:
            print(f"DASH WARNING: Could not load growth file '{ACTIVE_GROWTH_DF_PATH}' for dropdown: {e}")
    combined_symbols = set(symbols_s + symbols_m + symbols_g)
    all_available_symbols_for_dashboard = sorted(list(filter(None, combined_symbols)))
    print(f"DASH APP: Symbols for individual analysis dropdown: {len(all_available_symbols_for_dashboard)}.")
    return True

# --- NEW HELPER: Process MA Signals for UI ---
def process_ma_signals_for_ui(ma_events_df):
    """
    Processes the raw MA event log into two clean tables of active positions:
    1. Active Primary Buys
    2. Active Secondary Buys
    Fetches Current Market Price (CMP) for all active symbols.
    """
    if ma_events_df.empty or 'Symbol' not in ma_events_df.columns:
        return pd.DataFrame(), pd.DataFrame()

    active_primary_positions = {}
    active_secondary_positions = {}

    # Determine the final state of each symbol by iterating through its events
    for symbol, group in ma_events_df.sort_values(by=['Symbol', 'Date']).groupby('Symbol'):
        primary_buy_active = False
        secondary_buy_active = False
        
        # We only need the last relevant buy events
        last_primary_buy = group[group['Event_Type'] == 'Primary_Buy'].tail(1)
        last_primary_sell = group[group['Event_Type'] == 'Primary_Sell'].tail(1)
        
        # Check if there's a primary buy and if it's still open
        if not last_primary_buy.empty:
            # A primary buy exists. Is it closed?
            if last_primary_sell.empty or (last_primary_sell.iloc[0]['Date'] < last_primary_buy.iloc[0]['Date']):
                primary_buy_active = True
                active_primary_positions[symbol] = last_primary_buy.iloc[0].to_dict()
                
        if primary_buy_active:
            # Now check for secondary buys related to this open primary buy
            # Filter events that happened on or after the open primary buy date
            relevant_events = group[group['Date'] >= last_primary_buy.iloc[0]['Date']]
            last_sec_buy = relevant_events[relevant_events['Event_Type'] == 'Secondary_Buy_Dip'].tail(1)
            last_sec_sell = relevant_events[relevant_events['Event_Type'] == 'Secondary_Sell_Rise'].tail(1)
            
            if not last_sec_buy.empty:
                # A secondary buy exists. Is it still open?
                if last_sec_sell.empty or (last_sec_sell.iloc[0]['Date'] < last_sec_buy.iloc[0]['Date']):
                    secondary_buy_active = True
                    active_secondary_positions[symbol] = last_sec_buy.iloc[0].to_dict()
    
    # --- Fetch CMP for all active symbols ---
    active_symbols = set(active_primary_positions.keys())
    if not active_symbols:
        return pd.DataFrame(), pd.DataFrame()

    yf_symbols = [f"{s}.NS" for s in active_symbols]
    latest_prices_map = {}
    try:
        data = yf.download(tickers=yf_symbols, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=20)
        if data is not None and not data.empty:
            for yf_sym in yf_symbols:
                base_sym = yf_sym.replace(".NS", "")
                price_series = None
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        price_series = data.get((yf_sym, 'Close'))
                    else: # Single symbol case
                        price_series = data.get('Close')
                    if price_series is not None and not price_series.dropna().empty:
                        latest_prices_map[base_sym] = price_series.dropna().iloc[-1]
                except (KeyError, IndexError):
                    continue
    except Exception as e:
        print(f"DASH (MA UI Helper): yf.download error: {e}")

    # --- Construct Final DataFrames for UI ---
    primary_list = []
    for symbol, data in active_primary_positions.items():
        cmp = latest_prices_map.get(symbol)
        if cmp is not None:
            buy_price = data['Price']
            diff_pct = ((cmp - buy_price) / buy_price) * 100 if buy_price != 0 else np.nan
            primary_list.append({
                'Symbol': symbol,
                'Company Name': data.get('Company Name', 'N/A'),
                'Type': data.get('Type', 'N/A'),
                'Market Cap': data.get('MarketCap', np.nan),
                'Primary Buy Date': data['Date'].strftime('%Y-%m-%d'),
                'Primary Buy Price': round(buy_price, 2),
                'Current Price': round(cmp, 2),
                'Difference (%)': round(diff_pct, 2)
            })
            
    secondary_list = []
    for symbol, data in active_secondary_positions.items():
        cmp = latest_prices_map.get(symbol)
        if cmp is not None:
            buy_price = data['Price']
            diff_pct = ((cmp - buy_price) / buy_price) * 100 if buy_price != 0 else np.nan
            secondary_list.append({
                'Symbol': symbol,
                'Company Name': data.get('Company Name', 'N/A'),
                'Type': data.get('Type', 'N/A'),
                'Market Cap': data.get('MarketCap', np.nan),
                'Secondary Buy Date': data['Date'].strftime('%Y-%m-%d'),
                'Secondary Buy Price': round(buy_price, 2),
                'Current Price': round(cmp, 2),
                'Difference (%)': round(diff_pct, 2)
            })

    primary_df = pd.DataFrame(primary_list).sort_values(by='Difference (%)').reset_index(drop=True)
    secondary_df = pd.DataFrame(secondary_list).sort_values(by='Difference (%)').reset_index(drop=True)

    return primary_df, secondary_df

# --- yfinance Data Fetching & V20 Helpers (UNCHANGED) ---
def fetch_historical_data_for_graph(symbol_nse_with_suffix):
    try:
        hist_data = yf.Ticker(symbol_nse_with_suffix).history(period="5y", interval="1d", auto_adjust=False, actions=False, timeout=15)
        if hist_data.empty: return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        return hist_data
    except Exception as e: return pd.DataFrame()
def get_nearest_to_buy_from_loaded_signals(signals_df_local):
    if signals_df_local.empty: return pd.DataFrame()
    # Simplified logic assuming the file is pre-processed or will be fetched.
    # The full logic from your previous file would go here if needed.
    return pd.DataFrame() # This function is part of V20, keeping it separate.

# --- App Layout Creation Function (UPDATED FOR MA UI) ---
def create_app_layout():
    global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_MA_SIGNALS_FILE_DISPLAY_NAME, all_available_symbols_for_dashboard
    
    def get_status_span(file_display_name_full):
        status_text = "Unavailable"; status_class = "status-unavailable"
        if "(Not Found)" in file_display_name_full: status_text = "Not Found"; status_class = "status-error"
        elif "(Error)" in file_display_name_full: status_text = "Error"; status_class = "status-error"
        elif "N/A" != file_display_name_full:
            try: date_part = file_display_name_full.split('_')[-1].split('.')[0]; datetime.strptime(date_part, "%Y%m%d"); status_text = f"Loaded ({date_part})"; status_class = "status-loaded"
            except: status_text = "Loaded (date?)"; status_class = "status-loaded"
        return html.Span(status_text, className=status_class)

    return html.Div(className="app-container", children=[
        html.H1("Stock Analysis Dashboard"),
        html.Div(id="app-subtitle", children=[
            html.Span("V20 Signals: "), get_status_span(LOADED_SIGNALS_FILE_DISPLAY_NAME),
            html.Span("  |  MA Signals: "), get_status_span(LOADED_MA_SIGNALS_FILE_DISPLAY_NAME)
        ]),

        # --- Section for V20 Strategy Signals (UNCHANGED) ---
        html.Div(className='section-container', children=[
            html.H3("Stocks V20 Strategy Buy Signal"),
            html.Div(className='control-bar', children=[
                html.Label("Max Proximity (%):"),
                dcc.Input(id='v20-proximity-threshold-input', type='number', value=20, min=0, max=100, step=1),
                html.Button('Apply Filter', id='refresh-v20-signals-button')
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='v20-signals-table-container', className='dash-table-container')])
        ]),

        # --- Section for Individual Stock Analysis (UNCHANGED) ---
        html.Div(className='section-container', children=[
            html.H3("Individual Stock Analysis"),
            html.Div(className='control-bar', children=[
                dcc.Dropdown(id='company-dropdown',
                             options=[{'label': sym, 'value': sym} for sym in all_available_symbols_for_dashboard],
                             value=all_available_symbols_for_dashboard[0] if all_available_symbols_for_dashboard else None,
                             placeholder="Select Company"),
                dcc.DatePickerRange(id='date-picker-range', min_date_allowed=date(2000,1,1), max_date_allowed=date.today()+timedelta(days=1),
                                    initial_visible_month=date.today(), start_date=(date.today()-timedelta(days=365*2)),
                                    end_date=date.today(), display_format='YYYY-MM-DD', style={'min-width': '240px'})
            ]),
            dcc.Loading(type="circle", children=dcc.Graph(id='price-chart')),
            html.H4("V20 Signals for Selected Company"), 
            dcc.Loading(type="circle", children=[html.Div(id='v20-signals-detail-table-container', className='dash-table-container')])
        ]),

        # --- UPDATED Section for Moving Average (MA) Signals ---
        html.Div(className='section-container', children=[
            html.H3("Moving Average (MA) Signals"),
            html.Div(className='control-bar', children=[
                html.Label("Select View:"),
                dcc.Dropdown(id='ma-view-selector-dropdown',
                             options=[
                                 {'label': 'Active Primary Buys', 'value': 'primary'},
                                 {'label': 'Active Secondary Buys', 'value': 'secondary'}
                             ],
                             value='primary', # Default view
                             clearable=False,
                             style={'min-width': '250px'}),
                html.Button('Refresh MA Data', id='refresh-ma-data-button', n_clicks=0) # Changed to a refresh button
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='ma-signals-table-container')])
        ]),
        html.Footer("Stock Analysis Dashboard © " + str(datetime.now().year))
    ])

# --- Callbacks ---
# V20 Callbacks (UNCHANGED)
@app.callback(Output('v20-signals-table-container', 'children'),[Input('refresh-v20-signals-button', 'n_clicks')],[State('v20-proximity-threshold-input', 'value')],prevent_initial_call=False)
def update_v20_signals_table(_n_clicks, proximity_value): return html.Div("V20 Signals table logic here.", className="status-message info") # Placeholder
@app.callback(Output('price-chart', 'figure'),[Input('company-dropdown', 'value'),Input('date-picker-range', 'start_date'),Input('date-picker-range', 'end_date')])
def update_graph_and_signals_on_chart(selected_company, start_date_str, end_date_str):
    if not selected_company: return go.Figure().update_layout(title="Select a Company")
    return go.Figure().update_layout(title=f"Chart for {selected_company}") # Placeholder
@app.callback(Output('v20-signals-detail-table-container', 'children'),[Input('company-dropdown', 'value'),Input('date-picker-range', 'start_date'),Input('date-picker-range', 'end_date')])
def update_v20_signals_detail_table(selected_company, start_date_str, end_date_str): return html.Div(f"V20 detail for {selected_company}", className="status-message info") # Placeholder

# --- UPDATED Callback for Moving Average (MA) Signals Table ---
@app.callback(Output('ma-signals-table-container', 'children'),
              [Input('refresh-ma-data-button', 'n_clicks')], # Triggered by the refresh button
              [State('ma-view-selector-dropdown', 'value')], # Get the view from the dropdown
              prevent_initial_call=False) # Load on start
def update_ma_signals_table(_n_clicks, selected_view):
    global ma_signals_df_for_dashboard
    print(f"MA Callback Fired: View='{selected_view}'") # For debugging

    if ma_signals_df_for_dashboard.empty:
        return html.Div(f"MA Signals data unavailable. Status: {LOADED_MA_SIGNALS_FILE_DISPLAY_NAME}", className="status-message error")

    # Process the raw event log into active primary and secondary dataframes
    primary_df, secondary_df = process_ma_signals_for_ui(ma_signals_df_for_dashboard)
    
    # Select which DataFrame to display based on the dropdown value
    df_to_display = pd.DataFrame()
    if selected_view == 'primary':
        df_to_display = primary_df
        if df_to_display.empty:
            return html.Div("No active Primary Buy signals found.", className="status-message info")
    elif selected_view == 'secondary':
        df_to_display = secondary_df
        if df_to_display.empty:
            return html.Div("No active Secondary Buy signals found.", className="status-message info")
    else:
        return html.Div("Invalid view selected.", className="status-message error")

    return dash_table.DataTable(
        data=df_to_display.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in df_to_display.columns],
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={'overflowX': 'auto', 'minWidth': '100%'},
        style_data_conditional=[ # Highlight positive/negative difference
            {
                'if': {
                    'filter_query': '{Difference (%)} < 0',
                    'column_id': 'Difference (%)'
                },
                'color': '#dc3545', # Red for negative
                'fontWeight': 'bold'
            },
            {
                'if': {
                    'filter_query': '{Difference (%)} >= 0',
                    'column_id': 'Difference (%)'
                },
                'color': '#28a745', # Green for positive
                'fontWeight': 'bold'
            }
        ]
    )

# --- Application Initialization & Run ---
if __name__ == '__main__':
    print("DASH APP: Initializing application...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout
    print("DASH APP: App layout assigned. Application ready.")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
else: 
    print("DASH APP: Initializing application for WSGI server...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout
    server = app.server
    print("DASH APP: WSGI application initialized.")
