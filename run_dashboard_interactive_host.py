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

app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='assets')
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

# --- NEW HELPER: Process MA Signals for UI (UNCHANGED) ---
def process_ma_signals_for_ui(ma_events_df):
    if ma_events_df.empty or 'Symbol' not in ma_events_df.columns:
        return pd.DataFrame(), pd.DataFrame()
    active_primary_positions = {}
    active_secondary_positions = {}
    for symbol, group in ma_events_df.sort_values(by=['Symbol', 'Date']).groupby('Symbol'):
        last_primary_buy = group[group['Event_Type'] == 'Primary_Buy'].tail(1)
        if last_primary_buy.empty: continue
        primary_sell_after_buy = group[(group['Event_Type'] == 'Primary_Sell') & (group['Date'] > last_primary_buy.iloc[0]['Date'])]
        if primary_sell_after_buy.empty:
            active_primary_positions[symbol] = last_primary_buy.iloc[0].to_dict()
            relevant_events = group[group['Date'] >= last_primary_buy.iloc[0]['Date']]
            last_sec_buy = relevant_events[relevant_events['Event_Type'] == 'Secondary_Buy_Dip'].tail(1)
            if not last_sec_buy.empty:
                secondary_sell_after_buy = relevant_events[(relevant_events['Event_Type'] == 'Secondary_Sell_Rise') & (relevant_events['Date'] > last_sec_buy.iloc[0]['Date'])]
                if secondary_sell_after_buy.empty:
                    active_secondary_positions[symbol] = last_sec_buy.iloc[0].to_dict()
    active_symbols = set(active_primary_positions.keys())
    if not active_symbols: return pd.DataFrame(), pd.DataFrame()
    yf_symbols = [f"{s}.NS" for s in active_symbols]
    latest_prices_map = {}
    try:
        data = yf.download(tickers=yf_symbols, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=20)
        if data is not None and not data.empty:
            for yf_sym in yf_symbols:
                base_sym = yf_sym.replace(".NS", "")
                price_series = None
                try:
                    if isinstance(data.columns, pd.MultiIndex): price_series = data.get((yf_sym, 'Close'))
                    else: price_series = data.get('Close')
                    if price_series is not None and not price_series.dropna().empty:
                        latest_prices_map[base_sym] = price_series.dropna().iloc[-1]
                except (KeyError, IndexError): continue
    except Exception as e: print(f"DASH (MA UI Helper): yf.download error: {e}")
    primary_list = []
    for symbol, data in active_primary_positions.items():
        cmp = latest_prices_map.get(symbol)
        if cmp is not None:
            buy_price = data['Price']
            diff_pct = ((cmp - buy_price) / buy_price) * 100 if buy_price != 0 else np.nan
            primary_list.append({'Symbol': symbol, 'Company Name': data.get('Company Name', 'N/A'), 'Type': data.get('Type', 'N/A'), 'Market Cap': data.get('MarketCap', np.nan), 'Primary Buy Date': data['Date'].strftime('%Y-%m-%d'), 'Primary Buy Price': round(buy_price, 2), 'Current Price': round(cmp, 2), 'Difference (%)': round(diff_pct, 2)})
    secondary_list = []
    for symbol, data in active_secondary_positions.items():
        cmp = latest_prices_map.get(symbol)
        if cmp is not None:
            buy_price = data['Price']
            diff_pct = ((cmp - buy_price) / buy_price) * 100 if buy_price != 0 else np.nan
            secondary_list.append({'Symbol': symbol, 'Company Name': data.get('Company Name', 'N/A'), 'Type': data.get('Type', 'N/A'), 'Market Cap': data.get('MarketCap', np.nan), 'Secondary Buy Date': data['Date'].strftime('%Y-%m-%d'), 'Secondary Buy Price': round(buy_price, 2), 'Current Price': round(cmp, 2), 'Difference (%)': round(diff_pct, 2)})
    primary_df = pd.DataFrame(primary_list).sort_values(by='Difference (%)').reset_index(drop=True)
    secondary_df = pd.DataFrame(secondary_list).sort_values(by='Difference (%)').reset_index(drop=True)
    return primary_df, secondary_df

# --- yfinance Data Fetching (Individual Chart) (UNCHANGED) ---
def fetch_historical_data_for_graph(symbol_nse_with_suffix):
    try:
        hist_data = yf.Ticker(symbol_nse_with_suffix).history(period="5y", interval="1d", auto_adjust=False, actions=False, timeout=15)
        if hist_data.empty: return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        required_ohlc = ['Open', 'High', 'Low', 'Close']
        if not all(col in hist_data.columns for col in required_ohlc): return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=required_ohlc, inplace=True)
        return hist_data
    except Exception as e: return pd.DataFrame()

# --- CORRECTED Helper for "Stocks V20 Strategy Buy Signal" ---
def get_nearest_to_buy_from_loaded_signals(signals_df_local):
    """
    Finds the latest V20 signal for each stock, checks if it's still active
    (CMP < Sell Price), and calculates its proximity to the buy price.
    """
    if signals_df_local.empty or 'Symbol' not in signals_df_local.columns or 'Buy_Date' not in signals_df_local.columns:
        return pd.DataFrame()
    
    df_to_process = signals_df_local.copy()
    df_to_process['Buy_Date'] = pd.to_datetime(df_to_process['Buy_Date'], errors='coerce')
    df_to_process.dropna(subset=['Buy_Date'], inplace=True)
    
    # This is the original, correct logic for the V20 "Nearest to Buy" table.
    latest_signals = df_to_process.sort_values('Buy_Date', ascending=False).groupby('Symbol').first().reset_index()

    unique_symbols = latest_signals['Symbol'].dropna().unique()
    if not unique_symbols.any():
        return pd.DataFrame()

    print(f"DASH (V20 NearestBuy): Fetching CMPs for {len(unique_symbols)} latest signals...")
    yf_symbols = [f"{s}.NS" for s in unique_symbols]
    latest_prices_map = {}
    chunk_size = 50
    for i in range(0, len(yf_symbols), chunk_size):
        chunk = yf_symbols[i:i + chunk_size]
        try:
            data = yf.download(tickers=chunk, period="2d", progress=False, auto_adjust=False, group_by='ticker', timeout=20)
            if data is not None and not data.empty:
                for sym_ns in chunk:
                    base_sym = sym_ns.replace(".NS", "").upper()
                    price_series = None
                    if isinstance(data.columns, pd.MultiIndex):
                        if (sym_ns, 'Close') in data.columns: price_series = data[(sym_ns, 'Close')]
                        elif (sym_ns.upper(), 'Close') in data.columns: price_series = data[(sym_ns.upper(), 'Close')]
                    elif isinstance(data, dict):
                        symbol_data = data.get(sym_ns) or data.get(sym_ns.upper())
                        if symbol_data is not None and isinstance(symbol_data, pd.DataFrame) and 'Close' in symbol_data.columns:
                            price_series = symbol_data['Close']
                    elif 'Close' in data.columns and len(chunk) == 1:
                        price_series = data['Close']
                    if price_series is not None and not price_series.dropna().empty:
                        latest_prices_map[base_sym] = price_series.dropna().iloc[-1]
        except Exception as e_yf:
            print(f"DASH (V20 NearestBuy): yf.download error for chunk: {e_yf}")

    results = []
    for _idx, row in latest_signals.iterrows():
        symbol = str(row.get('Symbol','')).upper()
        cmp_val = latest_prices_map.get(symbol)
        buy_target = row.get('Buy_Price_Low')
        sell_target = row.get('Sell_Price_High') # Get the sell target

        # Skip if we don't have prices or targets
        if pd.isna(cmp_val) or pd.isna(buy_target) or buy_target == 0:
            continue
            
        # *** THIS IS THE NEW, CORRECTED LOGIC ***
        # If the sell target exists and the current price has met or exceeded it,
        # the signal is "closed" and should not appear in this table.
        if pd.notna(sell_target) and cmp_val >= sell_target:
            continue

        # If we reach here, the signal is active. Now calculate proximity for display.
        prox_pct = ((cmp_val - buy_target) / buy_target) * 100
        buy_date_str = pd.to_datetime(row.get('Buy_Date')).strftime('%Y-%m-%d')
        results.append({
            'Symbol': symbol, 'Signal Buy Date': buy_date_str, 'Target Buy Price (Low)': round(buy_target, 2),
            'Latest Close Price': round(cmp_val, 2), 'Proximity to Buy (%)': round(prox_pct, 2),
            'Closeness (%)': round(abs(prox_pct), 2),
            'Potential Gain (%)': round(row.get('Sequence_Gain_Percent', np.nan), 2)
        })
        
    if not results: return pd.DataFrame()
    return pd.DataFrame(results).sort_values(by=['Closeness (%)']).reset_index(drop=True)

# --- App Layout Creation Function (UNCHANGED) ---
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
        html.Div(className='section-container', children=[
            html.H3("Stocks V20 Strategy Buy Signal"),
            html.Div(className='control-bar', children=[
                html.Label("Max Proximity (%):"),
                dcc.Input(id='v20-proximity-threshold-input', type='number', value=20, min=0, max=100, step=1),
                html.Button('Apply Filter', id='refresh-v20-signals-button')
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='v20-signals-table-container', className='dash-table-container')])
        ]),
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
        html.Div(className='section-container', children=[
            html.H3("Moving Average (MA) Signals"),
            html.Div(className='control-bar', children=[
                html.Label("Select View:"),
                dcc.Dropdown(id='ma-view-selector-dropdown',
                             options=[{'label': 'Active Primary Buys', 'value': 'primary'}, {'label': 'Active Secondary Buys', 'value': 'secondary'}],
                             value='primary', clearable=False, style={'min-width': '250px'}),
                html.Button('Refresh MA Data', id='refresh-ma-data-button', n_clicks=0)
            ]),
            dcc.Loading(type="circle", children=[html.Div(id='ma-signals-table-container')])
        ]),
        html.Footer("Stock Analysis Dashboard © " + str(datetime.now().year))
    ])

# --- Callbacks ---
# Callback for V20 Strategy Signals Table (Full, working version)
@app.callback(Output('v20-signals-table-container', 'children'),
              [Input('refresh-v20-signals-button', 'n_clicks')],
              [State('v20-proximity-threshold-input', 'value')],
              prevent_initial_call=False)
def update_v20_signals_table(_n_clicks, proximity_value):
    global signals_df_for_dashboard
    if signals_df_for_dashboard.empty:
        return html.Div(f"V20 signals data unavailable. Status: {LOADED_SIGNALS_FILE_DISPLAY_NAME}", className="status-message error")
    
    # Call the corrected helper function
    processed_signals_df = get_nearest_to_buy_from_loaded_signals(signals_df_for_dashboard)
    
    if processed_signals_df.empty:
        # This message now correctly means no *active* latest signals were found.
        return html.Div("No active V20 signals found.", className="status-message warning")
    
    try: proximity_threshold = float(proximity_value if proximity_value is not None else 100) # Default to 100 to show all active
    except: proximity_threshold = 100.0 
    if not (0 <= proximity_threshold): proximity_threshold = 100.0

    # The filter for proximity is now just a way to focus on opportunities, not a primary rule.
    filtered_df = processed_signals_df[processed_signals_df['Closeness (%)'] <= proximity_threshold].copy()
    
    if filtered_df.empty:
        return html.Div(f"No active V20 signals within {proximity_threshold}% of their buy price.", className="status-message info")
    
    display_columns = [col for col in filtered_df.columns if col != 'Closeness (%)']
    return dash_table.DataTable(
        data=filtered_df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in display_columns],
        page_size=15, sort_action="native", filter_action="native",
        style_table={'overflowX': 'auto', 'minWidth': '100%'}
    )

# Callback for Individual Stock Chart (Full, working version)
@app.callback(Output('price-chart', 'figure'),
              [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def update_graph_and_signals_on_chart(selected_company, start_date_str, end_date_str):
    if not selected_company: return go.Figure().update_layout(title="Select a Company")
    try:
        start_date_obj = pd.to_datetime(start_date_str).normalize()
        end_date_obj = pd.to_datetime(end_date_str).normalize()
    except: return go.Figure().update_layout(title="Invalid Date Range")

    symbol_ns = f"{selected_company.upper()}.NS"
    hist_df = fetch_historical_data_for_graph(symbol_ns)
    fig = go.Figure()
    if not hist_df.empty:
        df_filtered_chart = hist_df[(hist_df['Date'] >= start_date_obj) & (hist_df['Date'] <= end_date_obj)].copy()
        if not df_filtered_chart.empty:
            fig.add_trace(go.Candlestick(x=df_filtered_chart['Date'], open=df_filtered_chart['Open'], high=df_filtered_chart['High'], low=df_filtered_chart['Low'], close=df_filtered_chart['Close'], name='OHLC'))
            df_filtered_chart['SMA20'] = df_filtered_chart['Close'].rolling(window=20, min_periods=1).mean()
            df_filtered_chart['SMA50'] = df_filtered_chart['Close'].rolling(window=50, min_periods=1).mean()
            df_filtered_chart['SMA200'] = df_filtered_chart['Close'].rolling(window=200, min_periods=1).mean()
            fig.add_trace(go.Scatter(x=df_filtered_chart['Date'], y=df_filtered_chart['SMA20'], mode='lines', name='SMA20', line=dict(color='blue', width=1)))
            fig.add_trace(go.Scatter(x=df_filtered_chart['Date'], y=df_filtered_chart['SMA50'], mode='lines', name='SMA50', line=dict(color='orange', width=1)))
            fig.add_trace(go.Scatter(x=df_filtered_chart['Date'], y=df_filtered_chart['SMA200'], mode='lines', name='SMA200', line=dict(color='purple', width=1)))
        else: fig.update_layout(title=f"No Price Data for {selected_company} in Range")
    else: fig.update_layout(title=f"No Price Data for {selected_company}")

    if not signals_df_for_dashboard.empty and 'Symbol' in signals_df_for_dashboard.columns:
        v20_sigs_on_chart = signals_df_for_dashboard[(signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper())].copy()
        v20_sigs_on_chart = v20_sigs_on_chart[(v20_sigs_on_chart['Buy_Date'] >= start_date_obj) & (v20_sigs_on_chart['Buy_Date'] <= end_date_obj)]
        for _, sig_row in v20_sigs_on_chart.iterrows():
            fig.add_trace(go.Scatter(x=[sig_row['Buy_Date']], y=[sig_row['Buy_Price_Low']], mode='markers', name='V20 Buy', marker=dict(symbol='triangle-up', color='green', size=10)))
            if pd.notna(sig_row['Sell_Date']) and sig_row['Sell_Date'] <= end_date_obj:
                 fig.add_trace(go.Scatter(x=[sig_row['Sell_Date']], y=[sig_row['Sell_Price_High']], mode='markers', name='V20 Sell', marker=dict(symbol='triangle-down', color='red', size=10)))
    
    if not ma_signals_df_for_dashboard.empty and 'Symbol' in ma_signals_df_for_dashboard.columns:
        ma_events_on_chart = ma_signals_df_for_dashboard[(ma_signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()) & (ma_signals_df_for_dashboard['Date'] >= start_date_obj) & (ma_signals_df_for_dashboard['Date'] <= end_date_obj)].copy()
        for _, event_row in ma_events_on_chart.iterrows():
            event_type = event_row['Event_Type']
            event_color, event_symbol, event_size = 'blue', 'circle', 8
            if 'Buy' in event_type: event_color = 'darkgreen'; event_symbol = 'triangle-up' if 'Primary' in event_type else 'diamond-up';
            elif 'Sell' in event_type: event_color = 'darkred'; event_symbol = 'triangle-down' if 'Primary' in event_type else 'diamond-down';
            elif 'Open' in event_type: event_color = 'grey'; event_symbol = 'square';
            fig.add_trace(go.Scatter(x=[event_row['Date']], y=[event_row['Price']], mode='markers', name=f"MA: {event_type}",
                                     marker=dict(symbol=event_symbol, color=event_color, size=event_size, line=dict(width=1,color='DarkSlateGrey')),
                                     hovertext=f"{event_type}<br>{event_row['Details']}<br>Price: {event_row['Price']}", hoverinfo="text"))
    fig.update_layout(title=f'{selected_company} Analysis', xaxis_rangeslider_visible=False, paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(t=50, b=20, l=30, r=30))
    return fig

# Callback for V20 Signals Detail Table (Full, working version)
@app.callback(Output('v20-signals-detail-table-container', 'children'),
              [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')])
def update_v20_signals_detail_table(selected_company, start_date_str, end_date_str):
    global signals_df_for_dashboard
    if not selected_company: return html.Div("Select a company.", className="status-message info")
    try: filter_start, filter_end = pd.to_datetime(start_date_str).normalize(), pd.to_datetime(end_date_str).normalize()
    except: return html.Div("Invalid date range.", className="status-message error")
    if signals_df_for_dashboard.empty: return html.Div(f"V20 Signals data unavailable. Status: {LOADED_SIGNALS_FILE_DISPLAY_NAME}", className="status-message error")
    company_sigs = signals_df_for_dashboard[signals_df_for_dashboard['Symbol'].astype(str).str.upper() == selected_company.upper()].copy()
    if company_sigs.empty: return html.Div(f"No V20 signals for {selected_company}.", className="status-message info")
    df_disp = company_sigs[(company_sigs['Buy_Date'] >= filter_start) & (company_sigs['Buy_Date'] <= filter_end)].copy()
    if df_disp.empty: return html.Div(f"No V20 signals for {selected_company} in selected date range.", className="status-message info")
    for col in ['Buy_Date', 'Sell_Date']:
        if col in df_disp.columns and pd.api.types.is_datetime64_any_dtype(df_disp[col]):
            df_disp[col] = df_disp[col].dt.strftime('%Y-%m-%d')
    df_disp.fillna('N/A', inplace=True)
    return dash_table.DataTable(
        data=df_disp.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in df_disp.columns if i != 'Closeness (%)'],
        page_size=10, sort_action="native",
        style_table={'overflowX': 'auto', 'minWidth': '100%'}
    )

# --- UPDATED Callback for Moving Average (MA) Signals Table (UNCHANGED from previous correct version) ---
@app.callback(Output('ma-signals-table-container', 'children'),
              [Input('refresh-ma-data-button', 'n_clicks')],
              [State('ma-view-selector-dropdown', 'value')],
              prevent_initial_call=False)
def update_ma_signals_table(_n_clicks, selected_view):
    global ma_signals_df_for_dashboard
    print(f"MA Callback Fired: View='{selected_view}'")
    if ma_signals_df_for_dashboard.empty:
        return html.Div(f"MA Signals data unavailable. Status: {LOADED_MA_SIGNALS_FILE_DISPLAY_NAME}", className="status-message error")
    primary_df, secondary_df = process_ma_signals_for_ui(ma_signals_df_for_dashboard)
    df_to_display = pd.DataFrame()
    if selected_view == 'primary':
        df_to_display = primary_df
        if df_to_display.empty: return html.Div("No active Primary Buy signals found.", className="status-message info")
    elif selected_view == 'secondary':
        df_to_display = secondary_df
        if df_to_display.empty: return html.Div("No active Secondary Buy signals found.", className="status-message info")
    else: return html.Div("Invalid view selected.", className="status-message error")
    return dash_table.DataTable(
        data=df_to_display.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in df_to_display.columns],
        page_size=20, sort_action="native", filter_action="native",
        style_table={'overflowX': 'auto', 'minWidth': '100%'},
        style_data_conditional=[
            {'if': {'filter_query': '{Difference (%)} < 0', 'column_id': 'Difference (%)'}, 'color': '#dc3545', 'fontWeight': 'bold'},
            {'if': {'filter_query': '{Difference (%)} >= 0', 'column_id': 'Difference (%)'}, 'color': '#28a745', 'fontWeight': 'bold'}
        ]
    )

# --- Application Initialization & Run (UNCHANGED) ---
if __name__ == '__main__':
    print("DASH APP: Initializing application...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout
    print("DASH APP: App layout assigned. Application ready.")
    app.run(debug=True, host='0.0.0.0', port=8050)
else: 
    print("DASH APP: Initializing application for WSGI server...")
    load_data_for_dashboard_from_repo()
    app.layout = create_app_layout
    server = app.server
    print("DASH APP: WSGI application initialized.")
