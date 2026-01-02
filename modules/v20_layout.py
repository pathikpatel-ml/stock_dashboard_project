# modules/v20_layout.py
from dash import dcc, html

def create_v20_layout():
    return html.Div(className='section-container', children=[
        html.H3("Stocks V20 Strategy Buy Signal"),
        
        # Notification Panel
        html.Div(id='v20-notification-panel', className='notification-panel', children=[
            html.H4("🔔 Live Notifications", style={'margin': '0 0 10px 0', 'color': '#007bff'}),
            html.Div(id='v20-notifications-container', className='notifications-container')
        ], style={
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6',
            'borderRadius': '5px',
            'padding': '15px',
            'marginBottom': '20px'
        }),
        
        # Market Sentiment Display
        html.Div(id='v20-sentiment-display', className='sentiment-display', children=[
            html.Div([
                html.Span("📊 Market Sentiment: ", style={'fontWeight': 'bold', 'fontSize': '16px'}),
                html.Span(id='v20-sentiment-score', children='Loading...', 
                         style={'fontSize': '18px', 'fontWeight': 'bold', 'marginLeft': '10px'}),
                html.Span(id='v20-sentiment-label', children='', 
                         style={'marginLeft': '10px', 'fontSize': '14px'})
            ])
        ], style={
            'backgroundColor': '#e9ecef',
            'padding': '10px 15px',
            'borderRadius': '5px',
            'marginBottom': '15px',
            'border': '1px solid #ced4da'
        }),
        
        # Technical Indicators Summary
        html.Div(id='v20-indicators-summary', className='indicators-summary', children=[
            html.H4("📈 Technical Indicators Overview", style={'margin': '0 0 15px 0', 'color': '#28a745'}),
            html.Div(id='v20-indicators-grid', className='indicators-grid')
        ], style={
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #28a745',
            'borderRadius': '5px',
            'padding': '15px',
            'marginBottom': '20px'
        }),
        
        html.Div(className='control-bar', children=[
            html.Button('🔄 Refresh Live Prices', id='refresh-v20-live-data-button', 
                       className='btn btn-primary', style={'marginRight': '10px'}),
            html.Button('📊 Update Indicators', id='refresh-v20-indicators-button', 
                       className='btn btn-success', style={'marginRight': '20px'}),
            html.Label("Filter by Proximity (%):", style={'marginLeft': '20px', 'fontWeight': 'bold'}),
            dcc.Input(id='v20-proximity-filter-input', type='number', value=100, min=0, step=5, 
                     placeholder="e.g., 20", style={'marginLeft': '10px', 'marginRight': '10px'}),
            html.Button('Apply Filter', id='apply-v20-filter-button', className='btn btn-secondary')
        ], style={'marginBottom': '15px'}),
        
        html.Div(id='v20-refresh-status-message'),
        
        # Auto-refresh interval component
        dcc.Interval(
            id='v20-auto-refresh-interval',
            interval=300000,  # 5 minutes
            n_intervals=0
        ),
        
        dcc.Loading(type="circle", children=[
            html.Div(id='v20-signals-table-container', className='dash-table-container')
        ])
    ])
