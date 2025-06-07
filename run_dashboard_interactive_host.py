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
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

# --- Global DataFrames & Dash App Initialization ---
signals_df_for_dashboard = pd.DataFrame()
ath_triggers_df_for_dashboard = pd.DataFrame()
growth_df_for_dashboard = pd.DataFrame() # For populating dropdown if other sources are empty
all_available_symbols_for_dashboard = []

LOADED_SIGNALS_FILE_DISPLAY_NAME = "N/A"
LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME = "N/A"

app = dash.Dash(__name__, suppress_callback_exceptions=True) # Suppress for dynamically added classNames in callbacks
app.title = "Stock Analysis Dashboard"
# server = app.server # Uncomment for Gunicorn deployment

# --- Data Loading Logic ---
def load_data_for_dashboard_from_repo():
    global signals_df_for_dashboard, ath_triggers_df_for_dashboard, growth_df_for_dashboard
    global all_available_symbols_for_dashboard
    # LOADED_SIGNALS_FILE_DISPLAY_NAME and LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME
    # are modified by the nested function which declares them global, so no need here.

    print(f"\n--- DASH APP: Loading Pre-calculated Data ---")
    current_date_str = datetime.now().strftime("%Y%m%d") # Defined in the outer function scope

    # Nested function to handle loading logic for each CSV type
    def load_csv_data(filename_template, df_global_name_str, display_name_global_str, date_cols=None):
        # Declare globals that this nested function will modify
        global signals_df_for_dashboard, ath_triggers_df_for_dashboard
        global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME

        expected_filename = filename_template.format(date_str=current_date_str)
        file_path = os.path.join(REPO_BASE_PATH, expected_filename)
        
        # Temporary variables for this load attempt
        loaded_df_for_this_call = pd.DataFrame() 
        status_display_name_for_this_call = f"{expected_filename} (Not Found)" # Default

        if os.path.exists(file_path):
            try:
                loaded_df_for_this_call = pd.read_csv(file_path)
                if date_cols:
                    for col in date_cols:
                        if col in loaded_df_for_this_call.columns:
                            loaded_df_for_this_call[col] = pd.to_datetime(loaded_df_for_this_call[col], errors='coerce')
                
                if df_global_name_str == "ath_triggers_df_for_dashboard": # Specific processing for ATH triggers
                    if 'CMP Proximity to Buy (%)' in loaded_df_for_this_call.columns and \
                       'ClosenessAbs (%)' not in loaded_df_for_this_call.columns:
                        proximity_numeric = pd.to_numeric(loaded_df_for_this_call['CMP Proximity to Buy (%)'], errors='coerce')
                        loaded_df_for_this_call['ClosenessAbs (%)'] = proximity_numeric.abs()
                    elif 'ClosenessAbs (%)' not in loaded_df_for_this_call.columns: # If both are missing
                         loaded_df_for_this_call['ClosenessAbs (%)'] = np.inf # Default for filtering
                
                status_display_name_for_this_call = expected_filename # Success
                print(f"DASH APP: Loaded {len(loaded_df_for_this_call)} records from '{expected_filename}'.")
            except Exception as e:
                print(f"DASH ERROR loading file '{expected_filename}': {e}")
                status_display_name_for_this_call = f"{expected_filename} (Error)"
                # loaded_df_for_this_call remains an empty DataFrame
        else:
            print(f"DASH WARNING: File '{expected_filename}' NOT FOUND.")
            # loaded_df_for_this_call remains an empty DataFrame

        # Assign to the correct global DataFrame and update the global display name variable
        if df_global_name_str == "signals_df_for_dashboard":
            signals_df_for_dashboard = loaded_df_for_this_call
            LOADED_SIGNALS_FILE_DISPLAY_NAME = status_display_name_for_this_call
        elif df_global_name_str == "ath_triggers_df_for_dashboard":
            ath_triggers_df_for_dashboard = loaded_df_for_this_call
            LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME = status_display_name_for_this_call

    # Call the nested function for each data type
    load_csv_data(SIGNALS_FILENAME_TEMPLATE, "signals_df_for_dashboard", "LOADED_SIGNALS_FILE_DISPLAY_NAME", date_cols=['Buy_Date', 'Sell_Date'])
    load_csv_data(ATH_TRIGGERS_FILENAME_TEMPLATE, "ath_triggers_df_for_dashboard", "LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME")
        
    # Populate symbols for individual analysis dropdown (this part is fine)
    symbols_s = signals_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist() if not signals_df_for_dashboard.empty and 'Symbol' in signals_df_for_dashboard.columns else []
    symbols_a = ath_triggers_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist() if not ath_triggers_df_for_dashboard.empty and 'Symbol' in ath_triggers_df_for_dashboard.columns else []
    symbols_g = []
    if os.path.exists(ACTIVE_GROWTH_DF_PATH):
        try:
            growth_df_for_dashboard = pd.read_csv(ACTIVE_GROWTH_DF_PATH)
            if 'Symbol' in growth_df_for_dashboard.columns:
                symbols_g = growth_df_for_dashboard['Symbol'].dropna().astype(str).str.upper().unique().tolist()
        except Exception as e:
            print(f"DASH WARNING: Could not load growth file '{ACTIVE_GROWTH_DF_PATH}' for dropdown: {e}")
            # growth_df_for_dashboard remains as previously defined or empty
    
    combined_symbols = set(symbols_s + symbols_a + symbols_g)
    all_available_symbols_for_dashboard = sorted(list(filter(None, combined_symbols))) # Filter out potential None/empty strings
    print(f"DASH APP: Symbols for individual analysis dropdown: {len(all_available_symbols_for_dashboard)}.")
    return True

# --- yfinance Data Fetching (Individual Stock Chart) ---
# ... (fetch_historical_data_for_graph function remains the same)
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
# ... (get_nearest_to_buy_from_loaded_signals function remains the same, assumes 'Latest Close Price' might need fetching)
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
                data = yf.download(tickers=chunk, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=20)
                if not data.empty:
                    for sym_ns in chunk:
                        base_sym = sym_ns.replace(".NS", "")
                        try:
                            price_series = data.get((sym_ns, 'Close')) if isinstance(data.columns, pd.MultiIndex) else data.get('Close')
                            if price_series is not None and not price_series.dropna().empty: latest_prices_map[base_sym] = price_series.dropna().iloc[-1]
                        except Exception: pass
            except Exception as e_yf: print(f"DASH (NearestBuy): yf.download error: {e_yf}")
        df_to_process['Latest Close Price'] = df_to_process['Symbol'].astype(str).str.upper().map(latest_prices_map)
        df_to_process.dropna(subset=['Latest Close Price'], inplace=True) # Critical: remove rows if CMP fetch failed
    if df_to_process.empty: return pd.DataFrame() # Check again after potential dropna
    results = []
    for _idx, row in df_to_process.iterrows():
        symbol, buy_target, cmp_val = str(row.get('Symbol','')).upper(), row.get('Buy_Price_Low'), row.get('Latest Close Price')
        if not symbol or pd.isna(buy_target) or buy_target == 0 or pd.isna(cmp_val): continue
        prox_pct = ((cmp_val - buy_target) / buy_target) * 100
        buy_date_str = pd.to_datetime(row.get('Buy_Date')).strftime('%Y-%m-%d') if pd.notna(row.get('Buy_Date')) else 'N/A'
        results.append({'Symbol': symbol, 'Signal Buy Date': buy_date_str, 'Target Buy Price (Low)': round(buy_target, 2),
                        'Latest Close Price': round(cmp_val, 2), 'Proximity to Buy (%)': round(prox_pct, 2),
                        'Closeness (%)': round(abs(prox_pct), 2), # Keep for sorting
                        'Potential Gain (%)': round(row.get('Sequence_Gain_Percent', np.nan), 2)})
    if not results: return pd.DataFrame()
    return pd.DataFrame(results).sort_values(by=['Closeness (%)', 'Symbol']).reset_index(drop=True)


# --- App Layout Creation Function ---
def create_app_layout():
    global LOADED_SIGNALS_FILE_DISPLAY_NAME, LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME, all_available_symbols_for_dashboard
    
    def get_status_span(file_display_name_full):
        status_text = "Unavailable"
        status_class = "status-unavailable"
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

    return html.Div(className="app-container", children=[
        html.H1("Stock Analysis Dashboard"),
        html.Div(id="app-subtitle", children=[
            html.Span("Daily Signals: "), get_status_span(LOADED_SIGNALS_FILE_DISPLAY_NAME),
            html.Span("  |  ATH Triggers: "), get_status_span(LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME)
        ]),

        html.Div(className='section-container', children=[
            html.H3("Stocks V20 Strategy Buy Signal"),
            html.Div(className='control-bar', children=[
                html.Label("Max Proximity (%):"),
                dcc.Input(id='proximity-threshold-input', type='number', value=20, min=0, max=100, step=1),
                html.Button('Apply Filter', id='refresh-nearest-button')
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='nearest-to-buy-table-container', className='dash-table-container')])
        ]),

        html.Div(className='section-container', children=[
            html.H3("Individual Stock Analysis For V20 Strategy"),
            html.Div(className='control-bar', children=[
                dcc.Dropdown(id='company-dropdown',
                             options=[{'label': sym, 'value': sym} for sym in all_available_symbols_for_dashboard],
                             value=all_available_symbols_for_dashboard[0] if all_available_symbols_for_dashboard else None,
                             placeholder="Select Company"),
                dcc.DatePickerRange(id='date-picker-range', min_date_allowed=date(2000,1,1), 
                                    max_date_allowed=date.today() + timedelta(days=1),
                                    initial_visible_month=date.today(), 
                                    start_date=(date.today()-timedelta(days=365*2)),
                                    end_date=date.today(), display_format='YYYY-MM-DD',
                                    style={'min-width': '240px'}
                                   )
            ]),
            dcc.Loading(type="circle", children=dcc.Graph(id='price-chart')),
            html.H4("Signals for Selected Company"),
            dcc.Loading(type="circle", children=[html.Div(id='signals-table-container', className='dash-table-container')])
        ]),

        html.Div(className='section-container', children=[
            html.H3("Stocks ATH Strategy Buy Signal"),
            html.Div(className='control-bar', children=[
                html.Label("Max Proximity to ATH Buy Trigger (%):"),
                dcc.Input(id='ath-proximity-filter-input', type='number', value=10, min=0, max=100, step=1),
                html.Button('Apply Filter', id='refresh-ath-triggers-button') # Changed button text
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='ath-triggers-table-container-multi', className='dash-table-container')])
        ]),
        html.Footer("Stock Analysis Dashboard © " + str(datetime.now().year))
    ])

# --- Callbacks ---
# Section 1: Stocks Nearest to Buy
@app.callback(Output('nearest-to-buy-table-container', 'children'),
              [Input('refresh-nearest-button', 'n_clicks')],
              [State('proximity-threshold-input', 'value')],
              prevent_initial_call=True) # prevent_initial_call can be True if initial load is handled differently or not desired. Set to False for load on start.
def update_nearest_to_buy_table(_n_clicks, proximity_value):
    # This callback now only applies filter to already processed data.
    # Data loading and initial processing (like CMP fetch if needed) happens via `load_data_for_dashboard_from_repo`
    # and `get_nearest_to_buy_from_loaded_signals`
    
    # For explicit refresh button, we might re-call get_nearest_to_buy_from_loaded_signals
    # if CMP fetching is part of it and needs to be fresh on button click.
    # For simplicity with pre-calculated files, this button MAINLY re-applies the filter.
    # If signals_df_for_dashboard itself is updated (e.g. app restarts with new daily file), the table will reflect that.
    
    global signals_df_for_dashboard
    if signals_df_for_dashboard.empty:
        return html.Div(f"Daily signals data unavailable. Status: {get_status_span(LOADED_SIGNALS_FILE_DISPLAY_NAME).children}", className="status-message error") # Use children to get text
    
    # Re-process with the global signals_df to ensure it's using the latest loaded data,
    # especially if CMPs are fetched on-the-fly within this function.
    processed_signals_df = get_nearest_to_buy_from_loaded_signals(signals_df_for_dashboard.copy())
    
    if processed_signals_df.empty:
        return html.Div("No stocks meet criteria after processing (potential CMP fetch issue).", className="status-message warning")
    
    try: proximity_threshold = float(proximity_value if proximity_value is not None else 20) # Handle None
    except: proximity_threshold = 20.0 
    if not (0 <= proximity_threshold <= 100): proximity_threshold = 20.0

    filtered_df = processed_signals_df[processed_signals_df['Closeness (%)'] <= proximity_threshold]
    if filtered_df.empty:
        return html.Div(f"No stocks within {proximity_threshold}% of buy signal.", className="status-message info")
    
    # Exclude 'Closeness (%)' from display columns as it's a helper for sorting/filtering
    display_columns = [col for col in filtered_df.columns if col != 'Closeness (%)']
    # Inside update_nearest_to_buy_table callback
    return dash_table.DataTable(
        data=filtered_df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in display_columns],
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={
            'overflowX': 'auto', # Crucial for horizontal scrolling
            'minWidth': '100%'   # Ensures table tries to use available width before scrolling
        }
        # other style_cell, style_header props will be picked from CSS
    )
    # return dash_table.DataTable(
    #     data=filtered_df.to_dict('records'),
    #     columns=[{'name': i, 'id': i} for i in display_columns],
    #     page_size=15,
    #     sort_action="native",
    #     filter_action="native",
    #     # style_* props will be picked from CSS, but can be added for specifics
    # )
    


# Section 2: Individual Stock Chart & Signals Table (Callbacks remain largely the same)
# ... (update_graph and update_signals_table callbacks from previous correct version)
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
                fig.add_annotation(x=buy_dt, y=sig_row['Buy_Price_Low'], text="B", bgcolor="rgba(144,238,144,0.7)", ax=0, ay=-20, font_size=10, borderpad=2, borderwidth=1) # Light green with alpha
                if pd.notna(sell_dt): fig.add_annotation(x=sell_dt, y=sig_row['Sell_Price_High'], text="S", bgcolor="rgba(255,192,203,0.7)", ax=0, ay=20, font_size=10, borderpad=2, borderwidth=1) # Pink with alpha
    fig.update_layout(title=f'{selected_company} Price Chart', xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(t=50, b=20, l=30, r=30)) # Add margin
    return fig

@app.callback(Output('signals-table-container', 'children'), [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def update_signals_table(selected_company, start_date_str, end_date_str):
    global signals_df_for_dashboard
    if not selected_company: return html.Div("Select a company.", className="status-message info")
    try: filter_start, filter_end = pd.to_datetime(start_date_str).normalize(), pd.to_datetime(end_date_str).normalize()
    except: return html.Div("Invalid date range.", className="status-message error")
    if signals_df_for_dashboard.empty: return html.Div(f"Signals data unavailable. Status: {get_status_span(LOADED_SIGNALS_FILE_DISPLAY_NAME).children}", className="status-message error")
    company_sigs = signals_df_for_dashboard[signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()].copy()
    if company_sigs.empty: return html.Div(f"No signals for {selected_company}.", className="status-message info")
    valid_buy = company_sigs['Buy_Date'].notna()
    closed_filt = valid_buy & company_sigs['Sell_Date'].notna() & (company_sigs['Buy_Date'] <= filter_end) & (company_sigs['Sell_Date'] >= filter_start)
    open_filt = valid_buy & company_sigs['Sell_Date'].isna() & (company_sigs['Buy_Date'] <= filter_end)
    df_disp = company_sigs[closed_filt | open_filt].copy()
    if df_disp.empty: return html.Div(f"No signals for {selected_company} in selected date range.", className="status-message info")
    for col in ['Buy_Date', 'Sell_Date']:
        if col in df_disp.columns and pd.api.types.is_datetime64_any_dtype(df_disp[col]):
            df_disp[col] = df_disp[col].dt.strftime('%Y-%m-%d')
    df_disp.fillna('N/A', inplace=True)
    # Inside update_signals_table callback
    return dash_table.DataTable(
        data=df_disp.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in df_disp.columns],
        page_size=10,
        sort_action="native",
        style_table={
            'overflowX': 'auto', # Crucial for horizontal scrolling
            'minWidth': '100%'
        }
    )
    
    # return dash_table.DataTable(data=df_disp.to_dict('records'), columns=[{'name': i, 'id': i} for i in df_disp.columns], page_size=10, sort_action="native")


# Section 3: Strategic ATH Triggers
@app.callback(Output('ath-triggers-table-container-multi', 'children'),
              [Input('refresh-ath-triggers-button', 'n_clicks')],
              [State('ath-proximity-filter-input', 'value')],
              prevent_initial_call=True) # Similar to signals table
def update_ath_triggers_multi_table(_n_clicks, proximity_value):
    global ath_triggers_df_for_dashboard
    if ath_triggers_df_for_dashboard.empty:
        return html.Div(f"ATH Triggers data unavailable. Status: {get_status_span(LOADED_ATH_TRIGGERS_FILE_DISPLAY_NAME).children}", className="status-message error")
    
    try: proximity_threshold = float(proximity_value if proximity_value is not None else 10)
    except: proximity_threshold = 10.0
    if not (0 <= proximity_threshold <= 100): proximity_threshold = 10.0

    if 'ClosenessAbs (%)' not in ath_triggers_df_for_dashboard.columns:
        return html.Div("Required 'ClosenessAbs (%)' column missing in ATH data.", className="status-message error")
        
    data_to_filter = ath_triggers_df_for_dashboard.copy()
    filtered_df = data_to_filter[data_to_filter['ClosenessAbs (%)'] <= proximity_threshold]
    
    # Exclude 'ClosenessAbs (%)' from display
    display_columns_ath = [col for col in filtered_df.columns if col != 'ClosenessAbs (%)']
    if filtered_df.empty: # Check after filtering
        return html.Div(f"No companies found within {proximity_threshold}% of ATH Buy Trigger.", className="status-message info")
    # Inside update_ath_triggers_multi_table callback
    return dash_table.DataTable(
        data=filtered_df_display.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in display_columns_ath],
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={
            'overflowX': 'auto', # Crucial for horizontal scrolling
            'minWidth': '100%'
        }
    )
    # return dash_table.DataTable(
    #     data=filtered_df.to_dict('records'),
    #     columns=[{'name': i, 'id': i} for i in display_columns_ath],
    #     page_size=20,
    #     sort_action="native",
    #     filter_action="native",
    # )

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
