"""
Stock Screener Callbacks - Handle all filter logic and stock selection interactions
"""
import pandas as pd
import dash
from dash import Input, Output, State, callback, ctx
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
from datetime import datetime, timedelta
import numpy as np

from data_manager import comprehensive_stocks_df, v20_signals_df
from modules.ma_calculator import calculate_moving_averages

@callback(
    [Output('filtered-stocks-table', 'data'),
     Output('filtered-stocks-table', 'columns'),
     Output('filter-summary', 'children')],
    [Input('apply-filters-btn', 'n_clicks'),
     Input('clear-filters-btn', 'n_clicks')],
    [State('nse-category-dropdown', 'value'),
     State('net-profit-slider', 'value'),
     State('quarterly-profit-slider', 'value'),
     State('roce-slider', 'value'),
     State('roe-slider', 'value'),
     State('debt-equity-slider', 'value'),
     State('public-holding-slider', 'value'),
     State('ma10-filter', 'value'),
     State('ma50-filter', 'value'),
     State('ma100-filter', 'value'),
     State('ma200-filter', 'value')]
)
def update_filtered_stocks(apply_clicks, clear_clicks, nse_categories, net_profit_range, 
                          quarterly_profit_range, roce_range, roe_range, debt_equity_range,
                          public_holding_range, ma10_filter, ma50_filter, ma100_filter, ma200_filter):
    """Apply filters and return filtered stock data"""
    
    if comprehensive_stocks_df.empty:
        return [], [], "No data available"
    
    df = comprehensive_stocks_df.copy()
    
    # Check if clear filters was clicked
    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'clear-filters-btn.n_clicks':
        # Return all stocks with no filters
        columns = [
            {'name': 'Symbol', 'id': 'Symbol', 'type': 'text'},
            {'name': 'Company Name', 'id': 'Company_Name', 'type': 'text'},
            {'name': 'Net Profit (Cr)', 'id': 'Net_Profit_Cr', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Latest Quarter Profit', 'id': 'Latest_Quarter_Profit', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'ROCE (%)', 'id': 'ROCE', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'ROE (%)', 'id': 'ROE', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Debt/Equity', 'id': 'Debt_to_Equity', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Public Holding (%)', 'id': 'Public_Holding_Percent', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Current Price', 'id': 'Current_Price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA10', 'id': 'MA10', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA50', 'id': 'MA50', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA100', 'id': 'MA100', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA200', 'id': 'MA200', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'NSE Categories', 'id': 'NSE_Categories', 'type': 'text'}
        ]
        return df.to_dict('records'), columns, f"Showing all {len(df)} stocks (no filters applied)"
    
    # Apply filters only if apply button was clicked
    if not (ctx.triggered and ctx.triggered[0]['prop_id'] == 'apply-filters-btn.n_clicks'):
        # Initial load - show all stocks
        columns = [
            {'name': 'Symbol', 'id': 'Symbol', 'type': 'text'},
            {'name': 'Company Name', 'id': 'Company_Name', 'type': 'text'},
            {'name': 'Net Profit (Cr)', 'id': 'Net_Profit_Cr', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Latest Quarter Profit', 'id': 'Latest_Quarter_Profit', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'ROCE (%)', 'id': 'ROCE', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'ROE (%)', 'id': 'ROE', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Debt/Equity', 'id': 'Debt_to_Equity', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Public Holding (%)', 'id': 'Public_Holding_Percent', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'Current Price', 'id': 'Current_Price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA10', 'id': 'MA10', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA50', 'id': 'MA50', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA100', 'id': 'MA100', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'MA200', 'id': 'MA200', 'type': 'numeric', 'format': {'specifier': '.2f'}},
            {'name': 'NSE Categories', 'id': 'NSE_Categories', 'type': 'text'}
        ]
        return df.to_dict('records'), columns, f"Showing all {len(df)} stocks (click Apply Filters to filter)"
    
    # Apply NSE Category filter
    if nse_categories:
        df = df[df['NSE_Categories'].apply(lambda x: any(cat in str(x) for cat in nse_categories) if pd.notna(x) else False)]
    
    # Apply numerical filters
    if net_profit_range:
        df = df[(df['Net_Profit_Cr'] >= net_profit_range[0]) & (df['Net_Profit_Cr'] <= net_profit_range[1])]
    
    if quarterly_profit_range:
        df = df[(df['Latest_Quarter_Profit'] >= quarterly_profit_range[0]) & (df['Latest_Quarter_Profit'] <= quarterly_profit_range[1])]
    
    if roce_range:
        df = df[(df['ROCE'] >= roce_range[0]) & (df['ROCE'] <= roce_range[1])]
    
    if roe_range:
        df = df[(df['ROE'] >= roe_range[0]) & (df['ROE'] <= roe_range[1])]
    
    if debt_equity_range:
        df = df[(df['Debt_to_Equity'] >= debt_equity_range[0]) & (df['Debt_to_Equity'] <= debt_equity_range[1])]
    
    if public_holding_range:
        df = df[(df['Public_Holding_Percent'] >= public_holding_range[0]) & (df['Public_Holding_Percent'] <= public_holding_range[1])]
    
    # Apply MA filters
    if ma10_filter == 'above':
        df = df[df['Current_Price'] > df['MA10']]
    elif ma10_filter == 'below':
        df = df[df['Current_Price'] < df['MA10']]
    
    if ma50_filter == 'above':
        df = df[df['Current_Price'] > df['MA50']]
    elif ma50_filter == 'below':
        df = df[df['Current_Price'] < df['MA50']]
    
    if ma100_filter == 'above':
        df = df[df['Current_Price'] > df['MA100']]
    elif ma100_filter == 'below':
        df = df[df['Current_Price'] < df['MA100']]
    
    if ma200_filter == 'above':
        df = df[df['Current_Price'] > df['MA200']]
    elif ma200_filter == 'below':
        df = df[df['Current_Price'] < df['MA200']]
    
    # Define columns
    columns = [
        {'name': 'Symbol', 'id': 'Symbol', 'type': 'text'},
        {'name': 'Company Name', 'id': 'Company_Name', 'type': 'text'},
        {'name': 'Net Profit (Cr)', 'id': 'Net_Profit_Cr', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'Latest Quarter Profit', 'id': 'Latest_Quarter_Profit', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'ROCE (%)', 'id': 'ROCE', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'ROE (%)', 'id': 'ROE', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'Debt/Equity', 'id': 'Debt_to_Equity', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'Public Holding (%)', 'id': 'Public_Holding_Percent', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'Current Price', 'id': 'Current_Price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'MA10', 'id': 'MA10', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'MA50', 'id': 'MA50', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'MA100', 'id': 'MA100', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'MA200', 'id': 'MA200', 'type': 'numeric', 'format': {'specifier': '.2f'}},
        {'name': 'NSE Categories', 'id': 'NSE_Categories', 'type': 'text'}
    ]
    
    # Summary
    avg_roce = df['ROCE'].mean() if not df.empty else 0
    avg_roe = df['ROE'].mean() if not df.empty else 0
    summary = f"Found {len(df)} stocks | Avg ROCE: {avg_roce:.2f}% | Avg ROE: {avg_roe:.2f}%"
    
    return df.to_dict('records'), columns, summary

@callback(
    [Output('selected-stock-detail', 'children'),
     Output('v20-signals-table', 'data'),
     Output('v20-signals-table', 'columns'),
     Output('ma-chart', 'figure')],
    [Input('filtered-stocks-table', 'active_cell')],
    [State('filtered-stocks-table', 'data')]
)
def update_stock_detail(active_cell, table_data):
    """Update stock detail panel when a stock is selected"""
    
    if not active_cell or not table_data:
        return "Select a stock from the table to view details", [], [], {}
    
    # Get selected stock
    row_index = active_cell['row']
    selected_stock = table_data[row_index]
    symbol = selected_stock['Symbol']
    
    # Get V20 signals for this stock
    v20_data = []
    v20_columns = []
    if not v20_signals_df.empty:
        stock_v20 = v20_signals_df[v20_signals_df['Symbol'] == symbol]
        if not stock_v20.empty:
            v20_data = stock_v20.to_dict('records')
            v20_columns = [
                {'name': 'Buy Date', 'id': 'Buy_Date', 'type': 'datetime'},
                {'name': 'Buy Price Low', 'id': 'Buy_Price_Low', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                {'name': 'Buy Price High', 'id': 'Buy_Price_High', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                {'name': 'Sell Date', 'id': 'Sell_Date', 'type': 'datetime'},
                {'name': 'Sell Price', 'id': 'Sell_Price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                {'name': 'Gain %', 'id': 'Sequence_Gain_Percent', 'type': 'numeric', 'format': {'specifier': '.2f'}}
            ]
    
    # Create MA chart
    ma_chart = create_ma_chart(symbol)
    
    # Stock detail summary
    detail_text = f"""
    **Selected Stock: {symbol}**
    
    **Company:** {selected_stock.get('Company_Name', 'N/A')}
    
    **Financial Metrics:**
    - Net Profit: ₹{selected_stock.get('Net_Profit_Cr', 0):.2f} Cr
    - Latest Quarter Profit: ₹{selected_stock.get('Latest_Quarter_Profit', 0):.2f} Cr
    - ROCE: {selected_stock.get('ROCE', 0):.2f}%
    - ROE: {selected_stock.get('ROE', 0):.2f}%
    - Debt/Equity: {selected_stock.get('Debt_to_Equity', 0):.2f}
    - Public Holding: {selected_stock.get('Public_Holding_Percent', 0):.2f}%
    
    **Technical Analysis:**
    - Current Price: ₹{selected_stock.get('Current_Price', 0):.2f}
    - MA10: ₹{selected_stock.get('MA10', 0):.2f}
    - MA50: ₹{selected_stock.get('MA50', 0):.2f}
    - MA100: ₹{selected_stock.get('MA100', 0):.2f}
    - MA200: ₹{selected_stock.get('MA200', 0):.2f}
    
    **NSE Categories:** {selected_stock.get('NSE_Categories', 'N/A')}
    """
    
    return detail_text, v20_data, v20_columns, ma_chart

def create_ma_chart(symbol):
    """Create moving average chart for selected stock"""
    try:
        # Fetch historical data
        ticker = yf.Ticker(f"{symbol}.NS")
        hist = ticker.history(period="1y")
        
        if hist.empty:
            return {}
        
        # Calculate MAs
        hist['MA10'] = hist['Close'].rolling(window=10).mean()
        hist['MA50'] = hist['Close'].rolling(window=50).mean()
        hist['MA100'] = hist['Close'].rolling(window=100).mean()
        hist['MA200'] = hist['Close'].rolling(window=200).mean()
        
        # Create chart
        fig = go.Figure()
        
        # Add price line
        fig.add_trace(go.Scatter(
            x=hist.index,
            y=hist['Close'],
            mode='lines',
            name='Close Price',
            line=dict(color='black', width=2)
        ))
        
        # Add MA lines
        fig.add_trace(go.Scatter(
            x=hist.index,
            y=hist['MA10'],
            mode='lines',
            name='MA10',
            line=dict(color='red', width=1)
        ))
        
        fig.add_trace(go.Scatter(
            x=hist.index,
            y=hist['MA50'],
            mode='lines',
            name='MA50',
            line=dict(color='blue', width=1)
        ))
        
        fig.add_trace(go.Scatter(
            x=hist.index,
            y=hist['MA100'],
            mode='lines',
            name='MA100',
            line=dict(color='green', width=1)
        ))
        
        fig.add_trace(go.Scatter(
            x=hist.index,
            y=hist['MA200'],
            mode='lines',
            name='MA200',
            line=dict(color='orange', width=1)
        ))
        
        fig.update_layout(
            title=f'{symbol} - Price & Moving Averages',
            xaxis_title='Date',
            yaxis_title='Price (₹)',
            height=400,
            showlegend=True
        )
        
        return fig
        
    except Exception as e:
        print(f"Error creating MA chart for {symbol}: {e}")
        return {}

@callback(
    Output('nse-category-dropdown', 'options'),
    Input('screener-page', 'id')  # Trigger on page load
)
def update_category_options(_):
    """Populate NSE category dropdown options"""
    if comprehensive_stocks_df.empty:
        return []
    
    # Extract all unique categories
    all_categories = set()
    for categories_str in comprehensive_stocks_df['NSE_Categories'].dropna():
        if isinstance(categories_str, str):
            categories = [cat.strip() for cat in categories_str.split(',')]
            all_categories.update(categories)
    
    return [{'label': cat, 'value': cat} for cat in sorted(all_categories)]

def register_screener_callbacks(app):
    """Register all screener-related callbacks with the app"""
    # All callbacks are already registered using @callback decorator
    # This function exists for consistency with the app structure
    pass