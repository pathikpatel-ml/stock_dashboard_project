#!/usr/bin/env python
# coding: utf-8

import os
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import sys
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objects as go
import yfinance as yf

# --- Configuration (paths relative to this script in the Git repo) ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))

GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"
LOADED_SIGNALS_FILE_DISPLAY_NAME = "N/A (Not Loaded)" # Updated by data loading

# --- Global DataFrames & Dash App Initialization ---
signals_df_for_dashboard = pd.DataFrame()
growth_df_for_dashboard = pd.DataFrame()
all_available_symbols_for_dashboard = []

app = dash.Dash(__name__, external_stylesheets=['https://codepen.io/chriddyp/pen/bWLwgP.css'])
app.title = "Stock Signal Dashboard"
server = app.server

# --- Data Loading Logic (Reads from Git Repo files) ---
def load_data_for_dashboard_from_repo():
    global signals_df_for_dashboard, growth_df_for_dashboard, all_available_symbols_for_dashboard
    global LOADED_SIGNALS_FILE_DISPLAY_NAME

    print(f"\n--- DASH APP: Loading Data (expecting files in Git repo) ---")

    # 1. Load Growth Data
    print(f"DASH APP: Loading growth data from: {ACTIVE_GROWTH_DF_PATH}")
    available_symbols_from_growth = []
    if os.path.exists(ACTIVE_GROWTH_DF_PATH):
        try:
            growth_df_for_dashboard = pd.read_csv(ACTIVE_GROWTH_DF_PATH)
            if 'Symbol' in growth_df_for_dashboard.columns:
                available_symbols_from_growth = sorted(growth_df_for_dashboard['Symbol'].astype(str).str.strip().dropna().unique())
            print(f"DASH APP: Loaded {len(growth_df_for_dashboard)} companies from growth file. Unique symbols: {len(available_symbols_from_growth)}")
        except Exception as e:
            print(f"DASH APP ERROR: Could not load growth file '{ACTIVE_GROWTH_DF_PATH}': {e}")
            growth_df_for_dashboard = pd.DataFrame(columns=['Symbol'])
    else:
        print(f"DASH APP WARNING: Growth file '{GROWTH_FILE_NAME}' not found at '{ACTIVE_GROWTH_DF_PATH}'.")
        growth_df_for_dashboard = pd.DataFrame(columns=['Symbol'])

    # 2. Load Candle Signals Data for the Current Day
    current_date_str = datetime.now().strftime("%Y%m%d")
    expected_signals_filename = SIGNALS_FILENAME_TEMPLATE.format(date_str=current_date_str)
    signals_file_path_in_repo = os.path.join(REPO_BASE_PATH, expected_signals_filename)

    print(f"DASH APP: Attempting to load today's candle signals from: {signals_file_path_in_repo}")
    available_symbols_from_signals = []
    if os.path.exists(signals_file_path_in_repo):
        try:
            signals_df_for_dashboard = pd.read_csv(signals_file_path_in_repo)
            # Ensure datetime conversion, handling potential errors by making them NaT
            signals_df_for_dashboard['Buy_Date'] = pd.to_datetime(signals_df_for_dashboard['Buy_Date'], errors='coerce')
            signals_df_for_dashboard['Sell_Date'] = pd.to_datetime(signals_df_for_dashboard['Sell_Date'], errors='coerce')
            if 'Symbol' in signals_df_for_dashboard.columns:
                available_symbols_from_signals = sorted(signals_df_for_dashboard['Symbol'].astype(str).str.strip().dropna().unique())
            print(f"DASH APP: Loaded {len(signals_df_for_dashboard)} signals from '{expected_signals_filename}'. Unique symbols: {len(available_symbols_from_signals)}")
            LOADED_SIGNALS_FILE_DISPLAY_NAME = expected_signals_filename
        except Exception as e:
            print(f"DASH APP ERROR: Could not load or parse signals file '{expected_signals_filename}': {e}")
            signals_df_for_dashboard = pd.DataFrame(columns=['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence'])
            LOADED_SIGNALS_FILE_DISPLAY_NAME = f"{expected_signals_filename} (Error Loading)"
    else:
        print(f"DASH APP WARNING: Today's signals file '{expected_signals_filename}' NOT FOUND in the repository path '{signals_file_path_in_repo}'.")
        print("The dashboard will operate with empty signal data. Ensure the generation script has run and committed today's file.")
        signals_df_for_dashboard = pd.DataFrame(columns=['Symbol', 'Buy_Date', 'Buy_Price_Low', 'Sell_Date', 'Sell_Price_High', 'Sequence_Gain_Percent', 'Days_in_Sequence'])
        LOADED_SIGNALS_FILE_DISPLAY_NAME = f"{expected_signals_filename} (Not Found in Repo)"

    all_available_symbols_for_dashboard = sorted(list(set(available_symbols_from_signals + available_symbols_from_growth)))
    print(f"DASH APP: TOTAL unique symbols for dropdown: {len(all_available_symbols_for_dashboard)}.")
    return True

# --- yfinance Data Fetching for Callbacks ---
def fetch_historical_data_for_graph(symbol_nse_with_suffix):
    try:
        stock_ticker = yf.Ticker(symbol_nse_with_suffix)
        hist_data = stock_ticker.history(period="5y", interval="1d", auto_adjust=False, actions=False, timeout=15) # 5 years for graph
        if hist_data.empty: return pd.DataFrame()
        hist_data = hist_data.reset_index()
        if 'Date' not in hist_data.columns: return pd.DataFrame()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None) # Ensure timezone naive
        required_ohlc = ['Open', 'High', 'Low', 'Close']
        if not all(col in hist_data.columns for col in required_ohlc): return pd.DataFrame()
        for col in required_ohlc: hist_data[col] = pd.to_numeric(hist_data[col], errors='coerce')
        hist_data.dropna(subset=required_ohlc, inplace=True)
        return hist_data
    except Exception as e:
        print(f"DASH APP ERROR fetching graph data for {symbol_nse_with_suffix}: {e}")
        return pd.DataFrame()

def get_nearest_to_buy_data_live(signals_df_input):
    if signals_df_input.empty or 'Symbol' not in signals_df_input.columns:
        return pd.DataFrame()
    all_unique_symbols = signals_df_input['Symbol'].dropna().astype(str).unique()
    if not all_unique_symbols.any(): return pd.DataFrame()

    yf_symbols_to_fetch = [f"{s.upper().strip()}.NS" for s in all_unique_symbols]
    latest_prices_map = {}

    if yf_symbols_to_fetch:
        try:
            data = yf.download(tickers=yf_symbols_to_fetch, period="5d", progress=False, auto_adjust=False, group_by='ticker', timeout=30)
            if not data.empty:
                for symbol_ns_key in yf_symbols_to_fetch:
                    base_symbol = symbol_ns_key.replace(".NS", "")
                    try:
                        if isinstance(data.columns, pd.MultiIndex): # Multiple symbols
                            if (symbol_ns_key, 'Close') in data.columns:
                                s_close = data[(symbol_ns_key, 'Close')].dropna()
                                if not s_close.empty: latest_prices_map[base_symbol] = s_close.iloc[-1]
                        elif 'Close' in data.columns and len(yf_symbols_to_fetch) == 1 : # Single symbol
                             s_close = data['Close'].dropna()
                             if not s_close.empty: latest_prices_map[base_symbol] = s_close.iloc[-1]
                    except KeyError:
                        pass
        except Exception as e:
            print(f"DASH APP WARNING: yf.download for nearest-to-buy prices failed: {e}. Table might be incomplete.")

    results = []
    for _idx, signal_row in signals_df_input.iterrows():
        symbol = signal_row.get('Symbol')
        buy_target = signal_row.get('Buy_Price_Low')

        if pd.isna(symbol) or pd.isna(buy_target) or buy_target == 0: continue

        latest_close = latest_prices_map.get(str(symbol).strip(), np.nan)
        if pd.isna(latest_close): continue

        prox_pct = ((latest_close - buy_target) / buy_target) * 100
        buy_date_dt = signal_row.get('Buy_Date')
        buy_date_str = buy_date_dt.strftime('%Y-%m-%d') if pd.notna(buy_date_dt) else 'N/A'

        results.append({
            'Symbol': symbol,
            'Signal Buy Date': buy_date_str,
            'Target Buy Price (Low)': round(buy_target, 2),
            'Latest Close Price': round(latest_close, 2),
            'Proximity to Buy (%)': round(prox_pct, 2),
            'Closeness (%)': round(abs(prox_pct), 2),
            'Potential Gain (%)': round(signal_row.get('Sequence_Gain_Percent', np.nan), 2)
        })

    if not results: return pd.DataFrame()
    return pd.DataFrame(results).sort_values(by=['Closeness (%)', 'Symbol', 'Signal Buy Date']).reset_index(drop=True)


# --- App Layout Creation Function ---
def create_app_layout():
    global LOADED_SIGNALS_FILE_DISPLAY_NAME, ACTIVE_GROWTH_DF_PATH, all_available_symbols_for_dashboard

    growth_file_display_name = os.path.basename(ACTIVE_GROWTH_DF_PATH) if ACTIVE_GROWTH_DF_PATH and os.path.exists(ACTIVE_GROWTH_DF_PATH) else f"{GROWTH_FILE_NAME} (Not Found in Repo)"

    return html.Div([
        html.H1("Stock Signal Dashboard", style={'textAlign': 'center', 'color': '#333', 'marginBottom': '10px'}),
        html.P(f"Source for Company List: {growth_file_display_name}", style={'textAlign': 'center', 'fontSize': 'small', 'color': '#555'}),
        html.P(f"Source for Trading Signals: {LOADED_SIGNALS_FILE_DISPLAY_NAME}", style={'textAlign': 'center', 'marginBottom': '25px', 'fontSize': 'small', 'color': '#555'}),

        html.Div([ # Nearest to Buy Section
            html.H3("Stocks Nearest to Buy Signal", style={'textAlign': 'center'}),
            html.Div([
                html.Label("Max Display Proximity (% from Buy Price, +/-):", style={'marginRight':'5px'}),
                dcc.Input(id='proximity-threshold-input', type='number', value=20, min=0, step=1, style={'marginLeft': '10px', 'marginRight': '20px', 'width':'60px'}),
                html.Button('Refresh Table', id='refresh-nearest-button', n_clicks=0, style={'backgroundColor': '#4CAF50', 'color': 'white', 'border': 'none', 'padding': '8px 12px', 'cursor': 'pointer', 'borderRadius':'5px'})
            ], style={'textAlign': 'center', 'marginBottom': '10px'}),
            dcc.Loading(id="loading-nearest-table", type="circle", children=[
                html.Div(id='nearest-to-buy-table-container', style={'margin': 'auto', 'width': '95%'})
            ])
        ], style={'marginBottom': '30px', 'padding': '20px', 'border': '1px solid #ddd', 'borderRadius': '8px', 'backgroundColor': '#f9f9f9'}),

        html.Div([ # Individual Stock Analysis Section
            html.H3("Individual Stock Analysis", style={'textAlign': 'center'}), # Removed marginTop, handled by div
            html.Div([
                dcc.Dropdown(
                    id='company-dropdown',
                    options=[{'label': sym, 'value': sym} for sym in all_available_symbols_for_dashboard],
                    value=all_available_symbols_for_dashboard[0] if all_available_symbols_for_dashboard else None,
                    placeholder="Select Company",
                    style={'width': '300px', 'display': 'inline-block', 'marginRight': '20px', 'verticalAlign': 'middle'}
                ),
                dcc.DatePickerRange(
                    id='date-picker-range',
                    min_date_allowed=datetime(2000,1,1),
                    max_date_allowed=datetime.now() + timedelta(days=1),
                    initial_visible_month=datetime.now(),
                    start_date=(datetime.now()-timedelta(days=365*2)).strftime('%Y-%m-%d'), # Default 2 years
                    end_date=datetime.now().strftime('%Y-%m-%d'),
                    display_format='YYYY-MM-DD',
                    style={'display': 'inline-block', 'verticalAlign': 'middle'}
                )
            ], style={'marginBottom': '20px', 'textAlign': 'center'}),
            dcc.Loading(id="loading-chart", type="circle", children=dcc.Graph(id='price-chart')),
            html.H4("Signals for Selected Company:", style={'marginTop': '20px', 'textAlign': 'center'}),
            dcc.Loading(id="loading-signals-table", type="circle", children=[
                 html.Div(id='signals-table-container', style={'margin': 'auto', 'width': '95%'})
            ])
        ], style={'marginTop': '30px', 'padding': '20px', 'border': '1px solid #ddd', 'borderRadius': '8px', 'backgroundColor': '#f9f9f9'}) # Added styling
    ])

# --- Callbacks ---
@app.callback(
    Output('nearest-to-buy-table-container', 'children'),
    [Input('refresh-nearest-button', 'n_clicks')],
    [State('proximity-threshold-input', 'value')],
    prevent_initial_call=False
)
def update_nearest_to_buy_table(_n_clicks, proximity_threshold):
    global signals_df_for_dashboard
    if signals_df_for_dashboard.empty:
        return html.P(f"No signal data available. Today's signal file '{LOADED_SIGNALS_FILE_DISPLAY_NAME}' might be missing or could not be parsed.", style={'textAlign': 'center', 'color':'red', 'fontWeight':'bold'})

    nearest_df = get_nearest_to_buy_data_live(signals_df_for_dashboard)

    if nearest_df.empty:
        return html.P("No stocks currently meet criteria, or current price data could not be fetched for signal stocks.", style={'textAlign': 'center'})

    if proximity_threshold is not None and isinstance(proximity_threshold, (int, float)):
        nearest_df = nearest_df[nearest_df['Closeness (%)'] <= proximity_threshold]
    else:
        print(f"DASH APP Warning: Invalid proximity_threshold value: {proximity_threshold}")

    if nearest_df.empty:
        return html.P(f"No stocks within +/- {proximity_threshold}% of their buy signal price.", style={'textAlign': 'center'})

    return dash_table.DataTable(
        data=nearest_df.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in nearest_df.columns],
        page_size=15,
        sort_action="native",
        filter_action="native",
        style_table={'overflowX': 'auto', 'width': '100%'},
        style_cell={'textAlign': 'left', 'minWidth': '100px', 'width': '150px', 'maxWidth': '200px', 'whiteSpace': 'normal', 'padding': '5px', 'fontSize':'0.9em'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold', 'border': '1px solid grey'},
        style_data={'border': '1px solid grey'}
    )

@app.callback(
    Output('price-chart', 'figure'),
    [Input('company-dropdown', 'value'),
     Input('date-picker-range', 'start_date'),
     Input('date-picker-range', 'end_date')]
)
def update_graph(selected_company, start_date_str, end_date_str):
    if not selected_company:
        return go.Figure().update_layout(title="Please select a company", template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    try:
        # Convert to datetime objects (timezone-naive, date part only for filtering)
        start_date = pd.to_datetime(start_date_str).normalize()
        end_date = pd.to_datetime(end_date_str).normalize()
    except Exception as e:
        print(f"DASH APP Error parsing dates: {e}")
        return go.Figure().update_layout(title="Invalid date format", template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    hist_df = fetch_historical_data_for_graph(f"{selected_company.upper().strip()}.NS")
    if hist_df.empty:
        return go.Figure().update_layout(title=f"No historical data found for {selected_company}", template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    # Filter by date range AFTER fetching
    # Ensure hist_df['Date'] is also normalized if it has time components, already done in fetch_historical_data_for_graph
    hist_df_filtered = hist_df[(hist_df['Date'] >= start_date) & (hist_df['Date'] <= end_date)]
    if hist_df_filtered.empty:
        return go.Figure().update_layout(title=f"No data for {selected_company} in selected date range", template="plotly_white", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

    fig = go.Figure(data=[go.Candlestick(x=hist_df_filtered['Date'],
                                       open=hist_df_filtered['Open'],
                                       high=hist_df_filtered['High'],
                                       low=hist_df_filtered['Low'],
                                       close=hist_df_filtered['Close'],
                                       name='Candlestick')])

    if not signals_df_for_dashboard.empty:
        company_signals = signals_df_for_dashboard[signals_df_for_dashboard['Symbol'] == selected_company].copy()
        if not company_signals.empty:
            # Buy_Date and Sell_Date are already datetime objects, potentially NaT
            for _, row in company_signals.iterrows():
                buy_dt = row['Buy_Date']
                sell_dt = row['Sell_Date']

                # Check if dates are valid before comparison
                if pd.isna(buy_dt): continue # Cannot plot signal without buy date

                # Determine if signal is within plot range (start_date, end_date from DatePicker)
                # Signal is relevant if its period [buy_dt, sell_dt_or_infinity] overlaps with [start_date, end_date]
                
                # Case 1: Closed signal (sell_dt is not NaT)
                show_signal = False
                if pd.notna(sell_dt):
                    if (buy_dt <= end_date) and (sell_dt >= start_date):
                        show_signal = True
                # Case 2: Open signal (sell_dt is NaT) - show if it started before or during the range
                else: # sell_dt is NaT
                    if buy_dt <= end_date:
                         show_signal = True
                
                if show_signal:
                    # For plotting, if sell_dt is NaT, we might plot it up to end_date of graph or last known point
                    # Here, we plot line segment if both points are valid
                    plot_x_coords = [buy_dt]
                    plot_y_coords = [row['Buy_Price_Low']]
                    
                    if pd.notna(sell_dt):
                        plot_x_coords.append(sell_dt)
                        plot_y_coords.append(row['Sell_Price_High'])
                    
                    # Only add trace if we have at least a buy point, and if sell point exists, then two points
                    if len(plot_x_coords) > 0:
                        fig.add_trace(go.Scatter(
                            x=plot_x_coords,
                            y=plot_y_coords,
                            mode='lines+markers' if len(plot_x_coords) > 1 else 'markers',
                            name=f"Signal Gain: {row.get('Sequence_Gain_Percent', 0):.1f}%" if pd.notna(sell_dt) else "Open Signal",
                            line=dict(color='rgba(128,0,128,0.7)', width=2, dash='dot'),
                            marker=dict(symbol='circle', size=8, color='purple', line=dict(width=1, color='DarkSlateGrey'))
                        ))
                        fig.add_annotation(x=buy_dt, y=row['Buy_Price_Low'], text="B", showarrow=True, arrowhead=2, arrowcolor="green", bgcolor="rgba(200,255,200,0.7)", ax=0, ay=-25, font=dict(size=9))
                        if pd.notna(sell_dt): # Only add sell annotation if sell_dt is valid
                             fig.add_annotation(x=sell_dt, y=row['Sell_Price_High'], text="S", showarrow=True, arrowhead=2, arrowcolor="red", bgcolor="rgba(255,200,200,0.7)", ax=0, ay=25, font=dict(size=9))

    fig.update_layout(title=f'{selected_company} Price Chart', xaxis_rangeslider_visible=False,
                      xaxis_title='Date', yaxis_title='Price (INR)', template="plotly_white",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    return fig

@app.callback(
    Output('signals-table-container', 'children'),
    [Input('company-dropdown', 'value'),
     Input('date-picker-range', 'start_date'), # Added input
     Input('date-picker-range', 'end_date')]  # Added input
)
def update_signals_table(selected_company, start_date_str, end_date_str): # Added arguments
    if not selected_company:
        return html.P("Select a company to see its signals.", style={'textAlign': 'center'})

    if not start_date_str or not end_date_str:
        return html.P("Please select a valid date range.", style={'textAlign': 'center', 'color': 'red'})

    try:
        # Convert to datetime objects (timezone-naive, date part only for filtering)
        filter_start_date = pd.to_datetime(start_date_str).normalize()
        filter_end_date = pd.to_datetime(end_date_str).normalize()
    except Exception as e:
        return html.P(f"Invalid date format in date picker: {e}", style={'textAlign': 'center', 'color': 'red'})

    if signals_df_for_dashboard.empty:
        return html.P(f"No signal data loaded. Today's signal file '{LOADED_SIGNALS_FILE_DISPLAY_NAME}' may be missing or invalid.", style={'textAlign': 'center', 'color':'orange', 'fontWeight':'bold'})

    company_signals_df = signals_df_for_dashboard[signals_df_for_dashboard['Symbol'] == selected_company].copy()
    
    if company_signals_df.empty:
        return html.P(f"No signals found for {selected_company} in the loaded data.", style={'textAlign': 'center'})

    # Ensure Buy_Date and Sell_Date are datetime objects (already done at load, but errors='coerce' means some could be NaT)
    # Filter based on the selected date range
    # A signal (row_buy_date, row_sell_date) overlaps with (filter_start_date, filter_end_date) if:
    # row_buy_date <= filter_end_date AND (row_sell_date >= filter_start_date OR row_sell_date is NaT)

    # Create boolean masks for filtering
    # Ensure Buy_Date is not NaT for any valid signal to filter
    valid_buy_date = company_signals_df['Buy_Date'].notna()

    # Condition for closed signals (Sell_Date is not NaT)
    closed_signals_filter = valid_buy_date & \
                            company_signals_df['Sell_Date'].notna() & \
                            (company_signals_df['Buy_Date'] <= filter_end_date) & \
                            (company_signals_df['Sell_Date'] >= filter_start_date)

    # Condition for open signals (Sell_Date is NaT)
    # Show if Buy_Date is before or at filter_end_date (meaning it started and is ongoing)
    open_signals_filter = valid_buy_date & \
                          company_signals_df['Sell_Date'].isna() & \
                          (company_signals_df['Buy_Date'] <= filter_end_date)
    
    company_signals_df_filtered = company_signals_df[closed_signals_filter | open_signals_filter]

    if company_signals_df_filtered.empty:
        return html.P(f"No signals found for {selected_company} within the selected date range.", style={'textAlign': 'center'})

    # Convert datetime columns to string for display AFTER filtering
    df_to_display = company_signals_df_filtered.copy() # Work on a copy for display formatting
    for col in ['Buy_Date', 'Sell_Date']:
        if col in df_to_display.columns and pd.api.types.is_datetime64_any_dtype(df_to_display[col]):
            df_to_display[col] = df_to_display[col].dt.strftime('%Y-%m-%d')
    
    # Replace any remaining NaT (e.g. in Sell_Date for open signals) with 'N/A' for display
    df_to_display.fillna('N/A', inplace=True)


    return dash_table.DataTable(
        data=df_to_display.to_dict('records'),
        columns=[{'name': i, 'id': i} for i in df_to_display.columns if i != 'Symbol' or selected_company], # Simple way to keep all columns
        page_size=10,
        sort_action="native",
        style_table={'overflowX': 'auto', 'width': '100%'},
        style_cell={'textAlign': 'left', 'minWidth': '100px', 'width': '150px', 'maxWidth': '200px', 'whiteSpace': 'normal', 'padding': '5px', 'fontSize':'0.9em'},
        style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold', 'border': '1px solid grey'},
        style_data={'border': '1px solid grey'}
    )

# --- Application Initialization Sequence ---
print("DASH APP: Initializing application for web server...")
load_data_for_dashboard_from_repo()
app.layout = create_app_layout
print(f"DASH APP: App layout assigned. {len(all_available_symbols_for_dashboard)} symbols in dropdown.")
print("DASH APP: Application initialized successfully. Ready for requests.")

# --- Main execution block for local development server ---
if __name__ == '__main__':
    print("DASH APP: Starting Dash development server (for local testing)...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
