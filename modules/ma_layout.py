# modules/ma_layout.py
from dash import dcc, html

def create_ma_layout():
    return html.Div(className='section-container', children=[
        html.H3("Moving Average (MA) Signals"),
        
        # Notification Panel for MA
        html.Div(id='ma-notification-panel', className='notification-panel', children=[
            html.H4("🔔 MA Signal Notifications", style={'margin': '0 0 10px 0', 'color': '#007bff'}),
            html.Div(id='ma-notifications-container', className='notifications-container')
        ], style={
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6',
            'borderRadius': '5px',
            'padding': '15px',
            'marginBottom': '20px'
        }),
        
        # Market Sentiment for MA
        html.Div(id='ma-sentiment-display', className='sentiment-display', children=[
            html.Div([
                html.Span("📊 MA Market Sentiment: ", style={'fontWeight': 'bold', 'fontSize': '16px'}),
                html.Span(id='ma-sentiment-score', children='Loading...', 
                         style={'fontSize': '18px', 'fontWeight': 'bold', 'marginLeft': '10px'}),
                html.Span(id='ma-sentiment-label', children='', 
                         style={'marginLeft': '10px', 'fontSize': '14px'})
            ])
        ], style={
            'backgroundColor': '#e9ecef',
            'padding': '10px 15px',
            'borderRadius': '5px',
            'marginBottom': '15px',
            'border': '1px solid #ced4da'
        }),
        
        # Technical Indicators for MA
        html.Div(id='ma-indicators-summary', className='indicators-summary', children=[
            html.H4("📈 MA Technical Analysis", style={'margin': '0 0 10px 0', 'color': '#6f42c1'}),
            html.Div([
                html.Span("📊 RSI: <30 Oversold (Buy), >70 Overbought (Sell) | ", 
                         style={'fontSize': '12px', 'color': '#6c757d', 'fontStyle': 'italic'}),
                html.Span("📈 MACD: >0 Bullish Trend, <0 Bearish Trend", 
                         style={'fontSize': '12px', 'color': '#6c757d', 'fontStyle': 'italic'})
            ], style={'marginBottom': '15px'}),
            html.Div(id='ma-indicators-grid', className='indicators-grid')
        ], style={
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #6f42c1',
            'borderRadius': '5px',
            'padding': '15px',
            'marginBottom': '20px'
        }),
        
        html.Div(className='control-bar', children=[
            html.Label("Select View:", style={'fontWeight': 'bold'}),
            dcc.Dropdown(id='ma-view-selector-dropdown',
                         options=[
                             {'label': '🟢 Active Primary Buys', 'value': 'primary'}, 
                             {'label': '🔵 Active Secondary Buys', 'value': 'secondary'}
                         ],
                         value='primary', clearable=False, 
                         style={'min-width': '250px', 'marginLeft': '10px', 'marginRight': '20px'}),
            html.Button('🔄 Refresh MA Data', id='refresh-ma-data-button', n_clicks=0, 
                       className='btn btn-primary', style={'marginRight': '10px'}),
            html.Button('📊 Update MA Indicators', id='refresh-ma-indicators-button', 
                       className='btn btn-success')
        ], style={'marginBottom': '15px', 'display': 'flex', 'alignItems': 'center'}),
        
        # Auto-refresh for MA
        dcc.Interval(
            id='ma-auto-refresh-interval',
            interval=300000,  # 5 minutes
            n_intervals=0
        ),
        
        dcc.Loading(type="circle", children=[
            html.Div(id='ma-signals-table-container')
        ])
    ])
