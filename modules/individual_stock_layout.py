# modules/individual_stock_layout.py
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import data_manager
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from datetime import date, timedelta

def create_individual_stock_layout():
    return html.Div(className='section-container', children=[
        html.H3("Individual Stock Analysis"),
        html.Div(className='control-bar', children=[
            dcc.Dropdown(id='company-dropdown',
                         options=[{'label': sym, 'value': sym} for sym in data_manager.all_available_symbols],
                         value=data_manager.all_available_symbols[0] if data_manager.all_available_symbols else None,
                         placeholder="Select Company"),
            dcc.DatePickerRange(id='date-picker-range', min_date_allowed=date(2000,1,1), max_date_allowed=date.today()+timedelta(days=1),
                                initial_visible_month=date.today(), start_date=(date.today()-timedelta(days=365*2)),
                                end_date=date.today(), display_format='YYYY-MM-DD', style={'min-width': '240px'})
        ]),
        dcc.Loading(type="circle", children=dcc.Graph(id='price-chart')),
        html.H4("V20 Signals for Selected Company"), 
        dcc.Loading(type="circle", children=[html.Div(id='v20-signals-detail-table-container', className='dash-table-container')])
    ])

def fetch_chart_data(symbol_ns):
    try:
        hist_data = yf.Ticker(symbol_ns).history(period="5y", interval="1d", auto_adjust=False, actions=False, timeout=15)
        return hist_data.reset_index()
    except: return pd.DataFrame()

def register_individual_stock_callbacks(app):
    @app.callback(
        Output('price-chart', 'figure'),
        [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')]
    )
    def update_chart(selected_company, start_date, end_date):
        if not selected_company: return go.Figure().update_layout(title="Select a Company")
        start_obj, end_obj = pd.to_datetime(start_date), pd.to_datetime(end_date)
        hist_df = fetch_chart_data(f"{selected_company}.NS")
        fig = go.Figure()
        if not hist_df.empty:
            chart_df = hist_df[(hist_df['Date'] >= start_obj) & (hist_df['Date'] <= end_obj)]
            if not chart_df.empty:
                fig.add_trace(go.Candlestick(x=chart_df['Date'], open=chart_df['Open'], high=chart_df['High'], low=chart_df['Low'], close=chart_df['Close'], name='OHLC'))
                for p in [20, 50, 200]: fig.add_trace(go.Scatter(x=chart_df['Date'], y=chart_df['Close'].rolling(p).mean(), name=f'SMA{p}'))
        v20_sigs = data_manager.signals_df[data_manager.signals_df['Symbol'] == selected_company]
        ma_sigs = data_manager.ma_signals_df[data_manager.ma_signals_df['Symbol'] == selected_company]
        # (Plotting logic for V20 and MA signals on the chart can be added here as before)
        fig.update_layout(title=f'{selected_company} Analysis', xaxis_rangeslider_visible=False)
        return fig

    @app.callback(
        Output('v20-signals-detail-table-container', 'children'),
        [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')]
    )
    def update_detail_table(selected_company, start_date, end_date):
        if not selected_company: return html.Div("Select a company.")
        df = data_manager.signals_df
        if df.empty: return html.Div("V20 signals data not loaded.")
        company_df = df[(df['Symbol'] == selected_company) & (df['Buy_Date'] >= pd.to_datetime(start_date)) & (df['Buy_Date'] <= pd.to_datetime(end_date))]
        if company_df.empty: return html.Div(f"No V20 signals for {selected_company} in this range.")
        return dash_table.DataTable(data=company_df.to_dict('records'), columns=[{'name': i, 'id': i} for i in company_df.columns])
