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
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv" # V20 Strategy
MA_SIGNALS_FILENAME_TEMPLATE = "ma_signals_data_{date_str}.csv" # NEW Moving Average Signals
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv" # For dropdown primarily
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

# --- Global DataFrames & Dash App Initialization ---
signals_df_for_dashboard = pd.DataFrame() # For V20
ma_signals_df_for_dashboard = pd.DataFrame() # For MA Signals
growth_df_for_dashboard = pd.DataFrame()
all_available_symbols_for_dashboard = []

LOADED_SIGNALS_FILE_DISPLAY_NAME = "N/A" # For V20
LOADED_MA_SIGNALS_FILE_DISPLAY_NAME = "N/A" # For MA Signals

app = dash.Dash(__name__, suppress_callback_exceptions=True)
app.title = "Stock Analysis Dashboard"
# server = app.server

# --- Data Loading Logic ---
def load_data_for_dashboard_from_repo():
    global signals_df_for_dashboard, ma_signals_df_for_dashboard, growth_df_for_dashboard
    global all_available_symbols_for_dashboard
    # Global display names are modified by the nested function
    print(f"\n--- DASH APP: Loading Pre-calculated Data ---")
    current_date_str = datetime.now().strftime("%Y%m%d")

    def load_csv_data(filename_template, df_global_name_str, display_name_global_str, date_cols=None):
        global signals_df_for_dashboard, ma_signals_df_for_dashboard # Add ma_signals_df
        global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_MA_SIGNALS_FILE_DISPLAY_NAME # Add MA display name

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
                
                # No specific processing needed for MA signals like ClosenessAbs for ATH was
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
        elif df_global_name_str == "ma_signals_df_for_dashboard": # Changed from ath_triggers
            ma_signals_df_for_dashboard = loaded_df_for_this_call
            LOADED_MA_SIGNALS_FILE_DISPLAY_NAME = status_display_name_for_this_call # Changed

    # Load V20 (Candle) Signals
    load_csv_data(SIGNALS_FILENAME_TEMPLATE, "signals_df_for_dashboard", "LOADED_SIGNALS_FILE_DISPLAY_NAME", date_cols=['Buy_Date', 'Sell_Date'])
    # Load MA Signals
    load_csv_data(MA_SIGNALS_FILENAME_TEMPLATE, "ma_signals_df_for_dashboard", "LOADED_MA_SIGNALS_FILE_DISPLAY_NAME", date_cols=['Date']) # 'Date' is the event date in MA signals
        
    symbols_s = signals_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist() if not signals_df_for_dashboard.empty and 'Symbol' in signals_df_for_dashboard.columns else []
    symbols_m = ma_signals_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist() if not ma_signals_df_for_dashboard.empty and 'Symbol' in ma_signals_df_for_dashboard.columns else [] # Symbols from MA
    symbols_g = []
    if os.path.exists(ACTIVE_GROWTH_DF_PATH):
        try:
            growth_df_for_dashboard = pd.read_csv(ACTIVE_GROWTH_DF_PATH)
            if 'Symbol' in growth_df_for_dashboard.columns:
                symbols_g = growth_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist()
        except Exception as e:
            print(f"DASH WARNING: Could not load growth file '{ACTIVE_GROWTH_DF_PATH}' for dropdown: {e}")
    
    combined_symbols = set(symbols_s + symbols_m + symbols_g) # Include symbols from MA signals
    all_available_symbols_for_dashboard = sorted(list(filter(None, combined_symbols)))
    print(f"DASH APP: Symbols for individual analysis dropdown: {len(all_available_symbols_for_dashboard)}.")
    return True

# --- yfinance Data Fetching (Individual Stock Chart) ---
# UNCHANGED
def fetch_historical_data_for_graph(symbol_nse_with_suffix):
    try:
        stock_ticker = yf.Ticker(symbol_nse_with_suffix)
        # Fetch enough data to potentially show MAs on chart later
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

# --- Helper for "Stocks V20 Strategy Buy Signal" ---
# UNCHANGED
def get_nearest_to_buy_from_loaded_signals(signals_df_local):
    if signals_df_local.empty or 'Symbol' not in signals_df_local.columns: return pd.DataFrame()
    df_to_process = signals_df_local.copy()
    if 'Latest Close Price' not in df_to_process.columns:
        print("DASH (V20 NearestBuy): 'Latest Close Price' not in V20 signals file. Fetching CMPs...")
        unique_symbols = df_to_process['Symbol'].dropna().astype(str).str.upper().unique()
        if not unique_symbols.any(): return pd.DataFrame()
        yf_symbols = [f"{s}.NS" for s in unique_symbols]; latest_prices_map = {}
        chunk_size = 50 # Adjusted for potentially more symbols
        for i in range(0, len(yf_symbols), chunk_size):
            chunk = yf_symbols[i:i + chunk_size]
            try:
                # Using '1d' period for current price, '2d' can be a fallback
                data = yf.download(tickers=chunk, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=20)
                if data is not None and not data.empty:
                    for sym_ns_original_case in chunk: # Iterate using original case from yf_symbols
                        base_sym = sym_ns_original_case.replace(".NS", "")
                        # Try to access data: handle MultiIndex or simple DataFrame
                        price_series = None
                        if isinstance(data.columns, pd.MultiIndex):
                            if (sym_ns_original_case, 'Close') in data.columns:
                                price_series = data[(sym_ns_original_case, 'Close')]
                            elif (sym_ns_original_case.upper(), 'Close') in data.columns: # Fallback for case sensitivity
                                price_series = data[(sym_ns_original_case.upper(), 'Close')]
                        elif sym_ns_original_case in data : # if data is a dict of DFs (older yfinance or specific calls)
                             if 'Close' in data[sym_ns_original_case].columns:
                                price_series = data[sym_ns_original_case]['Close']
                        elif 'Close' in data.columns and len(chunk) == 1: # Single symbol fetch returned flat DF
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

# --- App Layout Creation Function ---
def create_app_layout():
    global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_MA_SIGNALS_FILE_DISPLAY_NAME, all_available_symbols_for_dashboard
    
    def get_status_span(file_display_name_full): # Keep this helper
        status_text = "Unavailable"; status_class = "status-unavailable"
        if "(Not Found)" in file_display_name_full: status_text = "Not Found"; status_class = "status-error"
        elif "(Error)" in file_display_name_full: status_text = "Error"; status_class = "status-error"
        elif "N/A" != file_display_name_full:
            try: 
                date_part = file_display_name_full.split('_')[-1].split('.')[0]
                datetime.strptime(date_part, "%Y%m%d")
                status_text = f"Loaded ({date_part})"
                status_class = "status-loaded"
            except: status_text = "Loaded (date?)"; status_class = "status-loaded"
        return html.Span(status_text, className=status_class)

    # MA Signal Event Types for Dropdown Filter
    ma_event_types = []
    if not ma_signals_df_for_dashboard.empty and 'Event_Type' in ma_signals_df_for_dashboard.columns:
        ma_event_types = [{'label': etype, 'value': etype} for etype in ma_signals_df_for_dashboard['Event_Type'].unique()]
        ma_event_types.insert(0, {'label': 'All Event Types', 'value': 'ALL'})


    return html.Div(className="app-container", children=[
        html.H1("Stock Analysis Dashboard"),
        html.Div(id="app-subtitle", children=[
            html.Span("V20 Signals: "), get_status_span(LOADED_SIGNALS_FILE_DISPLAY_NAME), # V20
            html.Span("  |  MA Signals: "), get_status_span(LOADED_MA_SIGNALS_FILE_DISPLAY_NAME) # MA
        ]),

        # Section for V20 Strategy Signals
        html.Div(className='section-container', children=[
            html.H3("Stocks V20 Strategy Buy Signal"), # Title for V20
            html.Div(className='control-bar', children=[
                html.Label("Max Proximity (%):"),
                dcc.Input(id='v20-proximity-threshold-input', type='number', value=20, min=0, max=100, step=1), # Unique ID
                html.Button('Apply Filter', id='refresh-v20-signals-button') # Unique ID
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='v20-signals-table-container', className='dash-table-container')]) # Unique ID
        ]),

        # Section for Individual Stock Analysis (Graphs, etc.) - Can show V20 and MA signals on chart
        html.Div(className='section-container', children=[
            html.H3("Individual Stock Analysis"), # General title
            html.Div(className='control-bar', children=[
                dcc.Dropdown(id='company-dropdown',
                             options=[{'label': sym, 'value': sym} for sym in all_available_symbols_for_dashboard],
                             value=all_available_symbols_for_dashboard[0] if all_available_symbols_for_dashboard else None,
                             placeholder="Select Company"),
                dcc.DatePickerRange(id='date-picker-range', min_date_allowed=date(2000,1,1), 
                                    max_date_allowed=date.today() + timedelta(days=1),
                                    initial_visible_month=date.today(), 
                                    start_date=(date.today()-timedelta(days=365*2)), # Default 2 years
                                    end_date=date.today(), display_format='YYYY-MM-DD',
                                    style={'min-width': '240px'}
                                   )
            ]),
            dcc.Loading(type="circle", children=dcc.Graph(id='price-chart')),
            # This table can show V20 signals. We might add another for MA signals for the selected stock or combine.
            html.H4("V20 Signals for Selected Company"), 
            dcc.Loading(type="circle", children=[html.Div(id='v20-signals-detail-table-container', className='dash-table-container')])
        ]),

        # Section for Moving Average (MA) Signals
        html.Div(className='section-container', children=[
            html.H3("Moving Average (MA) Signals"), # New Title
            html.Div(className='control-bar', children=[
                html.Label("Filter by Event Type:"),
                dcc.Dropdown(id='ma-event-type-filter', options=ma_event_types, value='ALL', # Default to ALL
                             placeholder="Select Event Type", style={'min-width': '200px', 'margin-right': '10px'}),
                html.Label("Filter by Symbol:"),
                dcc.Input(id='ma-symbol-filter-input', type='text', placeholder="Enter Symbol (e.g., RELIANCE)",
                          style={'margin-right': '10px'}),
                html.Button('Apply MA Filters', id='refresh-ma-signals-button')
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='ma-signals-table-container', className='dash-table-container')]) # Unique ID
        ]),
        html.Footer("Stock Analysis Dashboard © " + str(datetime.now().year))
    ])

# --- Callbacks ---
# Callback for V20 Strategy Signals Table
@app.callback(Output('v20-signals-table-container', 'children'), # Updated ID
              [Input('refresh-v20-signals-button', 'n_clicks')], # Updated ID
              [State('v20-proximity-threshold-input', 'value')], # Updated ID
              prevent_initial_call=False) # Load on start
def update_v20_signals_table(_n_clicks, proximity_value):
    global signals_df_for_dashboard
    if signals_df_for_dashboard.empty:
        return html.Div(f"V20 signals data unavailable. Status: {LOADED_SIGNALS_FILE_DISPLAY_NAME}", className="status-message error")
    
    processed_signals_df = get_nearest_to_buy_from_loaded_signals(signals_df_for_dashboard.copy())
    
    if processed_signals_df.empty:
        return html.Div("No V20 stocks meet criteria after processing.", className="status-message warning")
    
    try: proximity_threshold = float(proximity_value if proximity_value is not None else 20)
    except: proximity_threshold = 20.0 
    if not (0 <= proximity_threshold <= 100): proximity_threshold = 20.0

    filtered_df = processed_signals_df[processed_signals_df['Closeness (%)'] <= proximity_threshold]
    if filtered_df.empty:
        return html.Div(f"No V20 stocks within {proximity_threshold}% of buy signal.", className="status-message info")
    
    display_columns = [col for col in filtered_df.columns if col != 'Closeness (%)']
    return dash_table.DataTable(
        data=filtered_df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in display_columns],
        page_size=15, sort_action="native", filter_action="native",
        style_table={'overflowX': 'auto', 'minWidth': '100%'}
    )

# Callback for Individual Stock Chart (Price and V20 Signals)
@app.callback(Output('price-chart', 'figure'),
              [Input('company-dropdown', 'value'),
               Input('date-picker-range', 'start_date'),
               Input('date-picker-range', 'end_date')])
def update_graph_and_signals_on_chart(selected_company, start_date_str, end_date_str):
    if not selected_company:
        return go.Figure().update_layout(title="Select a Company", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    try:
        start_date_obj = pd.to_datetime(start_date_str).normalize()
        end_date_obj = pd.to_datetime(end_date_str).normalize()
    except:
        return go.Figure().update_layout(title="Invalid Date Range", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    symbol_ns = f"{selected_company.upper()}.NS"
    hist_df = fetch_historical_data_for_graph(symbol_ns)

    fig = go.Figure()
    if not hist_df.empty:
        df_filtered_chart = hist_df[(hist_df['Date'] >= start_date_obj) & (hist_df['Date'] <= end_date_obj)]
        if not df_filtered_chart.empty:
            fig.add_trace(go.Candlestick(x=df_filtered_chart['Date'],
                                         open=df_filtered_chart['Open'],
                                         high=df_filtered_chart['High'],
                                         low=df_filtered_chart['Low'],
                                         close=df_filtered_chart['Close'], name='OHLC'))
            # Add SMAs to chart from historical data
            df_filtered_chart['SMA20'] = df_filtered_chart['Close'].rolling(window=20, min_periods=1).mean()
            df_filtered_chart['SMA50'] = df_filtered_chart['Close'].rolling(window=50, min_periods=1).mean()
            df_filtered_chart['SMA200'] = df_filtered_chart['Close'].rolling(window=200, min_periods=1).mean()
            fig.add_trace(go.Scatter(x=df_filtered_chart['Date'], y=df_filtered_chart['SMA20'], mode='lines', name='SMA20', line=dict(color='blue', width=1)))
            fig.add_trace(go.Scatter(x=df_filtered_chart['Date'], y=df_filtered_chart['SMA50'], mode='lines', name='SMA50', line=dict(color='orange', width=1)))
            fig.add_trace(go.Scatter(x=df_filtered_chart['Date'], y=df_filtered_chart['SMA200'], mode='lines', name='SMA200', line=dict(color='purple', width=1)))
        else:
            fig.update_layout(title=f"No Price Data for {selected_company} in Range")
    else:
        fig.update_layout(title=f"No Price Data for {selected_company}")

    # Overlay V20 Signals
    if not signals_df_for_dashboard.empty and 'Symbol' in signals_df_for_dashboard.columns:
        v20_sigs_on_chart = signals_df_for_dashboard[
            (signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()) &
            (signals_df_for_dashboard['Buy_Date'] >= start_date_obj) &
            (signals_df_for_dashboard['Buy_Date'] <= end_date_obj) # Filter by Buy_Date in range
        ].copy()
        for _, sig_row in v20_sigs_on_chart.iterrows():
            fig.add_trace(go.Scatter(x=[sig_row['Buy_Date']], y=[sig_row['Buy_Price_Low']], mode='markers', name='V20 Buy', marker=dict(symbol='triangle-up', color='green', size=10)))
            if pd.notna(sig_row['Sell_Date']) and sig_row['Sell_Date'] <= end_date_obj:
                 fig.add_trace(go.Scatter(x=[sig_row['Sell_Date']], y=[sig_row['Sell_Price_High']], mode='markers', name='V20 Sell', marker=dict(symbol='triangle-down', color='red', size=10)))
    
    # Overlay MA Signal Events
    if not ma_signals_df_for_dashboard.empty and 'Symbol' in ma_signals_df_for_dashboard.columns:
        ma_events_on_chart = ma_signals_df_for_dashboard[
            (ma_signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()) &
            (ma_signals_df_for_dashboard['Date'] >= start_date_obj) & # Event Date
            (ma_signals_df_for_dashboard['Date'] <= end_date_obj)
        ].copy()
        for _, event_row in ma_events_on_chart.iterrows():
            event_type = event_row['Event_Type']
            event_color = 'blue'
            event_symbol = 'circle'
            event_size = 8
            if 'Buy' in event_type: event_color = 'darkgreen'; event_symbol = 'triangle-up' if 'Primary' in event_type else 'diamond-up';
            elif 'Sell' in event_type: event_color = 'darkred'; event_symbol = 'triangle-down' if 'Primary' in event_type else 'diamond-down';
            elif 'Open' in event_type: event_color = 'grey'; event_symbol = 'square';
            
            fig.add_trace(go.Scatter(x=[event_row['Date']], y=[event_row['Price']], mode='markers', name=f"MA: {event_type}",
                                     marker=dict(symbol=event_symbol, color=event_color, size=event_size, line=dict(width=1,color='DarkSlateGrey')),
                                     hovertext=f"{event_type}<br>{event_row['Details']}<br>Price: {event_row['Price']}", hoverinfo="text"))

    fig.update_layout(title=f'{selected_company} Analysis', xaxis_rangeslider_visible=False,
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      margin=dict(t=50, b=20, l=30, r=30))
    return fig

# Callback for V20 Signals Table for Selected Company
@app.callback(Output('v20-signals-detail-table-container', 'children'), # Updated ID
              [Input('company-dropdown', 'value'),
               Input('date-picker-range', 'start_date'),
               Input('date-picker-range', 'end_date')])
def update_v20_signals_detail_table(selected_company, start_date_str, end_date_str):
    global signals_df_for_dashboard
    if not selected_company: return html.Div("Select a company.", className="status-message info")
    try: filter_start, filter_end = pd.to_datetime(start_date_str).normalize(), pd.to_datetime(end_date_str).normalize()
    except: return html.Div("Invalid date range.", className="status-message error")
    if signals_df_for_dashboard.empty: return html.Div(f"V20 Signals data unavailable. Status: {LOADED_SIGNALS_FILE_DISPLAY_NAME}", className="status-message error")
    
    company_sigs = signals_df_for_dashboard[signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()].copy()
    if company_sigs.empty: return html.Div(f"No V20 signals for {selected_company}.", className="status-message info")
    
    # Filter signals within the selected date range
    df_disp = company_sigs[
        (company_sigs['Buy_Date'] >= filter_start) & (company_sigs['Buy_Date'] <= filter_end)
    ].copy()

    if df_disp.empty: return html.Div(f"No V20 signals for {selected_company} in selected date range.", className="status-message info")
    
    for col in ['Buy_Date', 'Sell_Date']:
        if col in df_disp.columns and pd.api.types.is_datetime64_any_dtype(df_disp[col]):
            df_disp[col] = df_disp[col].dt.strftime('%Y-%m-%d')
    df_disp.fillna('N/A', inplace=True)
    
    return dash_table.DataTable(
        data=df_disp.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in df_disp.columns if i != 'Closeness (%)'], # Exclude if present
        page_size=10, sort_action="native",
        style_table={'overflowX': 'auto', 'minWidth': '100%'}
    )

# Callback for Moving Average (MA) Signals Table
@app.callback(Output('ma-signals-table-container', 'children'), # Updated ID
              [Input('refresh-ma-signals-button', 'n_clicks')],
              [State('ma-event-type-filter', 'value'),
               State('ma-symbol-filter-input', 'value')],
              prevent_initial_call=False) # Load on start
def update_ma_signals_table(_n_clicks, selected_event_type, filter_symbol):
    global ma_signals_df_for_dashboard
    if ma_signals_df_for_dashboard.empty:
        return html.Div(f"MA Signals data unavailable. Status: {LOADED_MA_SIGNALS_FILE_DISPLAY_NAME}", className="status-message error")

    filtered_df = ma_signals_df_for_dashboard.copy()

    # Apply Event Type Filter
    if selected_event_type and selected_event_type != 'ALL':
        filtered_df = filtered_df[filtered_df['Event_Type'] == selected_event_type]

    # Apply Symbol Filter (case-insensitive partial match)
    if filter_symbol and filter_symbol.strip():
        search_term = filter_symbol.strip().upper()
        filtered_df = filtered_df[filtered_df['Symbol'].astype(str).str.upper().str.contains(search_term)]
    
    if filtered_df.empty:
        return html.Div("No MA signals match the current filter criteria.", className="status-message info")
    
    # Sort by Date descending to show recent events first for MA signals
    if 'Date' in filtered_df.columns:
        filtered_df['Date'] = pd.to_datetime(filtered_df['Date']) # Ensure it's datetime
        filtered_df = filtered_df.sort_values(by='Date', ascending=False)
        filtered_df['Date'] = filtered_df['Date'].dt.strftime('%Y-%m-%d') # Format back to string for display


    return dash_table.DataTable(
        data=filtered_df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in filtered_df.columns],
        page_size=20, # Show more MA events
        sort_action="native", # User can still sort
        filter_action="native", # Allow native Dash table filtering
        style_table={'overflowX': 'auto', 'minWidth': '100%'}
    )

# --- Application Initialization & Run ---
if __name__ == '__main__':
    print("DASH APP: Initializing application...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout # Assign the function, Dash calls it
    print("DASH APP: App layout assigned. Application ready.")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
else: 
    print("DASH APP: Initializing application for WSGI server...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout
    server = app.server 
    print("DASH APP: WSGI application initialized.")
