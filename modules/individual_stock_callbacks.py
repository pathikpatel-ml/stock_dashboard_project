# modules/individual_stock_callbacks.py
from dash import html, dash_table
from dash.dependencies import Input, Output
import data_manager
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go

def fetch_chart_data(symbol_ns):
    """Helper function to fetch historical data for the chart."""
    try:
        hist_data = yf.Ticker(symbol_ns).history(period="5y", interval="1d", auto_adjust=False, actions=False, timeout=15)
        if hist_data.empty: return pd.DataFrame()
        hist_data = hist_data.reset_index()
        hist_data['Date'] = pd.to_datetime(hist_data['Date']).dt.tz_localize(None)
        return hist_data
    except Exception as e:
        print(f"Chart Data Fetch Error for {symbol_ns}: {e}")
        return pd.DataFrame()

def register_individual_stock_callbacks(app):
    """Registers all callbacks for the individual stock analysis section."""

    @app.callback(
        Output('price-chart', 'figure'),
        [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')]
    )
    def update_chart(selected_company, start_date_str, end_date_str):
        if not selected_company:
            return go.Figure().update_layout(title="Select a Company", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

        try:
            start_obj = pd.to_datetime(start_date_str)
            end_obj = pd.to_datetime(end_date_str)
        except:
            return go.Figure().update_layout(title="Invalid Date Range", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')

        hist_df = fetch_chart_data(f"{selected_company}.NS")
        fig = go.Figure()

        if not hist_df.empty:
            chart_df = hist_df[(hist_df['Date'] >= start_obj) & (hist_df['Date'] <= end_obj)]
            if not chart_df.empty:
                fig.add_trace(go.Candlestick(x=chart_df['Date'], open=chart_df['Open'], high=chart_df['High'], low=chart_df['Low'], close=chart_df['Close'], name='OHLC'))
                for period in [20, 50, 200]:
                    sma_series = chart_df['Close'].rolling(window=period, min_periods=1).mean()
                    fig.add_trace(go.Scatter(x=chart_df['Date'], y=sma_series, mode='lines', name=f'SMA{period}', line={'width': 1}))

        # Overlay V20 signals
        if not data_manager.signals_df.empty:
            v20_sigs = data_manager.signals_df[data_manager.signals_df['Symbol'] == selected_company]
            v20_sigs = v20_sigs[(v20_sigs['Buy_Date'] >= start_obj) & (v20_sigs['Buy_Date'] <= end_obj)]
            for _, row in v20_sigs.iterrows():
                fig.add_trace(go.Scatter(x=[row['Buy_Date']], y=[row['Buy_Price_Low']], mode='markers', name='V20 Buy', marker=dict(symbol='triangle-up', size=10, color='green')))
                if pd.notna(row['Sell_Date']) and row['Sell_Date'] <= end_obj:
                     fig.add_trace(go.Scatter(x=[row['Sell_Date']], y=[row['Sell_Price_High']], mode='markers', name='V20 Sell', marker=dict(symbol='triangle-down', size=10, color='red')))

        # Overlay MA signals
        if not data_manager.ma_signals_df.empty:
            ma_sigs = data_manager.ma_signals_df[data_manager.ma_signals_df['Symbol'] == selected_company]
            ma_sigs = ma_sigs[(ma_sigs['Date'] >= start_obj) & (ma_sigs['Date'] <= end_obj)]
            for _, row in ma_sigs.iterrows():
                event_type, event_color, event_symbol = row['Event_Type'], 'blue', 'circle'
                if 'Buy' in event_type: event_color = 'darkgreen'; event_symbol = 'triangle-up' if 'Primary' in event_type else 'diamond-up'
                elif 'Sell' in event_type: event_color = 'darkred'; event_symbol = 'triangle-down' if 'Primary' in event_type else 'diamond-down'
                fig.add_trace(go.Scatter(x=[row['Date']], y=[row['Price']], mode='markers', name=f"MA: {event_type}", marker=dict(symbol=event_symbol, color=event_color, size=8)))

        fig.update_layout(title=f'{selected_company} Analysis', xaxis_rangeslider_visible=False, legend=dict(orientation="h", yanchor="bottom", y=1.02))
        return fig

    @app.callback(
        Output('v20-signals-detail-table-container', 'children'),
        [Input('company-dropdown', 'value'), Input('date-picker-range', 'start_date'), Input('date-picker-range', 'end_date')]
    )
    def update_detail_table(selected_company, start_date_str, end_date_str):
        if not selected_company:
            return html.Div("Select a company.")

        df = data_manager.signals_df
        if df.empty:
            return html.Div("V20 signals data not loaded.")

        try:
            start_obj = pd.to_datetime(start_date_str)
            end_obj = pd.to_datetime(end_date_str)
        except:
            return html.Div("Invalid date range.")

        company_df = df[(df['Symbol'] == selected_company) & (df['Buy_Date'] >= start_obj) & (df['Buy_Date'] <= end_obj)].copy()

        if company_df.empty:
            return html.Div(f"No V20 signals for {selected_company} in this range.")

        # Format dates for display
        for col in ['Buy_Date', 'Sell_Date']:
            if col in company_df.columns:
                company_df[col] = company_df[col].dt.strftime('%Y-%m-%d')
        company_df.fillna('N/A', inplace=True)
        
        return dash_table.DataTable(
            data=company_df.to_dict('records'),
            columns=[{'name': i, 'id': i} for i in company_df.columns if i != 'Closeness (%)'],
            page_size=10,
            sort_action='native'
        )
