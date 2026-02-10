import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc

def create_screener_layout():
    return dbc.Container([
        # Header
        dbc.Row([
            dbc.Col([
                html.H2("Stock Screener", className="text-primary mb-3"),
                html.P("Filter and analyze stocks with comprehensive metrics", className="text-muted")
            ])
        ], className="mb-4"),
        
        dbc.Row([
            # Left Sidebar - Filters
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(html.H5("Filters", className="mb-0")),
                    dbc.CardBody([
                        # NSE Category Filter
                        html.Label("NSE Categories:", className="fw-bold"),
                        dcc.Dropdown(
                            id='category-filter',
                            placeholder="Select categories...",
                            multi=True,
                            className="mb-3"
                        ),
                        
                        # Net Profit Filter
                        html.Label("Net Profit (Cr):", className="fw-bold"),
                        dcc.RangeSlider(
                            id='net-profit-filter',
                            min=-1000, max=10000, step=100,
                            marks={i: f'{i}' for i in range(0, 10001, 2000)},
                            value=[-1000, 10000],
                            className="mb-3"
                        ),
                        
                        # Latest Quarter Profit Filter
                        html.Label("Latest Quarter Profit (Cr):", className="fw-bold"),
                        dcc.RangeSlider(
                            id='quarter-profit-filter',
                            min=-500, max=5000, step=50,
                            marks={i: f'{i}' for i in range(0, 5001, 1000)},
                            value=[-500, 5000],
                            className="mb-3"
                        ),
                        
                        # ROCE Filter
                        html.Label("ROCE (%):", className="fw-bold"),
                        dcc.RangeSlider(
                            id='roce-filter',
                            min=-50, max=100, step=5,
                            marks={i: f'{i}%' for i in range(0, 101, 25)},
                            value=[-50, 100],
                            className="mb-3"
                        ),
                        
                        # ROE Filter
                        html.Label("ROE (%):", className="fw-bold"),
                        dcc.RangeSlider(
                            id='roe-filter',
                            min=-50, max=100, step=5,
                            marks={i: f'{i}%' for i in range(0, 101, 25)},
                            value=[-50, 100],
                            className="mb-3"
                        ),
                        
                        # Debt to Equity Filter
                        html.Label("Debt to Equity:", className="fw-bold"),
                        dcc.RangeSlider(
                            id='debt-equity-filter',
                            min=0, max=5, step=0.1,
                            marks={i: f'{i}' for i in range(0, 6)},
                            value=[0, 5],
                            className="mb-3"
                        ),
                        
                        # Public Holding Filter
                        html.Label("Public Holding (%):", className="fw-bold"),
                        dcc.RangeSlider(
                            id='public-holding-filter',
                            min=0, max=100, step=5,
                            marks={i: f'{i}%' for i in range(0, 101, 25)},
                            value=[0, 100],
                            className="mb-3"
                        ),
                        
                        # Moving Average Filters
                        html.Hr(),
                        html.Label("Moving Average Filters:", className="fw-bold"),
                        
                        # MA10 Filter
                        html.Label("MA10 Position:", className="small"),
                        dcc.Dropdown(
                            id='ma10-filter',
                            options=[
                                {'label': 'All', 'value': 'all'},
                                {'label': 'Above MA10', 'value': 'above'},
                                {'label': 'Below MA10', 'value': 'below'},
                                {'label': 'Golden Cross (MA10)', 'value': 'golden'},
                                {'label': 'Death Cross (MA10)', 'value': 'death'}
                            ],
                            value='all',
                            className="mb-2"
                        ),
                        
                        # MA50 Filter
                        html.Label("MA50 Position:", className="small"),
                        dcc.Dropdown(
                            id='ma50-filter',
                            options=[
                                {'label': 'All', 'value': 'all'},
                                {'label': 'Above MA50', 'value': 'above'},
                                {'label': 'Below MA50', 'value': 'below'}
                            ],
                            value='all',
                            className="mb-2"
                        ),
                        
                        # MA200 Filter
                        html.Label("MA200 Position:", className="small"),
                        dcc.Dropdown(
                            id='ma200-filter',
                            options=[
                                {'label': 'All', 'value': 'all'},
                                {'label': 'Above MA200', 'value': 'above'},
                                {'label': 'Below MA200', 'value': 'below'}
                            ],
                            value='all',
                            className="mb-3"
                        ),
                        
                        # Action Buttons
                        html.Hr(),
                        dbc.Row([
                            dbc.Col([
                                dbc.Button("Apply Filters", id="apply-filters-btn", 
                                         color="primary", className="w-100 mb-2")
                            ]),
                            dbc.Col([
                                dbc.Button("Clear All", id="clear-filters-btn", 
                                         color="secondary", className="w-100 mb-2")
                            ])
                        ])
                    ])
                ])
            ], width=3),
            
            # Main Content Area
            dbc.Col([
                # Summary Stats
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H4(id="total-stocks", children="0", className="text-primary"),
                                html.P("Total Stocks", className="mb-0")
                            ])
                        ])
                    ], width=3),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H4(id="avg-roce", children="0%", className="text-success"),
                                html.P("Avg ROCE", className="mb-0")
                            ])
                        ])
                    ], width=3),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H4(id="avg-roe", children="0%", className="text-info"),
                                html.P("Avg ROE", className="mb-0")
                            ])
                        ])
                    ], width=3),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.H4(id="avg-profit", children="0Cr", className="text-warning"),
                                html.P("Avg Profit", className="mb-0")
                            ])
                        ])
                    ], width=3)
                ], className="mb-4"),
                
                # Stock List Table
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("Filtered Stocks", className="mb-0"),
                        html.Small("Click on a stock to view V20 signals and technical analysis", 
                                 className="text-muted")
                    ]),
                    dbc.CardBody([
                        dash_table.DataTable(
                            id='stocks-table',
                            columns=[
                                {'name': 'Symbol', 'id': 'Symbol', 'type': 'text'},
                                {'name': 'Company', 'id': 'Company Name', 'type': 'text'},
                                {'name': 'Net Profit', 'id': 'Net Profit', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                                {'name': 'Q Profit', 'id': 'Latest Quarter Profit', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                                {'name': 'ROCE %', 'id': 'ROCE', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                                {'name': 'ROE %', 'id': 'ROE', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                                {'name': 'D/E', 'id': 'Debt to Equity', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                                {'name': 'Public %', 'id': 'Public Holding', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                                {'name': 'Price', 'id': 'Current_Price', 'type': 'numeric', 'format': {'specifier': '.2f'}},
                                {'name': 'MA10', 'id': 'MA10_Signal', 'type': 'text'},
                                {'name': 'MA50', 'id': 'MA50_Signal', 'type': 'text'},
                                {'name': 'MA200', 'id': 'MA200_Signal', 'type': 'text'}
                            ],
                            data=[],
                            sort_action="native",
                            filter_action="native",
                            page_action="native",
                            page_current=0,
                            page_size=20,
                            row_selectable="single",
                            selected_rows=[],
                            style_cell={'textAlign': 'left', 'fontSize': '12px'},
                            style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold'},
                            style_data_conditional=[
                                {
                                    'if': {'filter_query': '{MA10_Signal} = Above'},
                                    'backgroundColor': '#d4edda',
                                    'color': 'black',
                                },
                                {
                                    'if': {'filter_query': '{MA50_Signal} = Above'},
                                    'backgroundColor': '#d1ecf1',
                                    'color': 'black',
                                }
                            ]
                        )
                    ])
                ])
            ], width=9)
        ]),
        
        # Selected Stock Detail Panel (Hidden by default)
        dbc.Row([
            dbc.Col([
                html.Div(id="stock-detail-panel", children=[], style={'display': 'none'})
            ])
        ], className="mt-4")
        
    ], fluid=True)

def create_stock_detail_panel(symbol, v20_data, ma_data):
    """Create detailed panel for selected stock"""
    return dbc.Card([
        dbc.CardHeader([
            html.H4(f"{symbol} - Detailed Analysis", className="mb-0"),
            dbc.Button("×", id="close-detail-panel", color="link", className="float-end")
        ]),
        dbc.CardBody([
            dbc.Row([
                # V20 Signals
                dbc.Col([
                    html.H5("V20 Signals"),
                    dash_table.DataTable(
                        id=f'v20-table-{symbol}',
                        data=v20_data.to_dict('records') if not v20_data.empty else [],
                        columns=[
                            {'name': 'Signal Date', 'id': 'Signal Buy Date'},
                            {'name': 'Target Price', 'id': 'Target Buy Price (Low)'},
                            {'name': 'Current Price', 'id': 'Latest Close Price'},
                            {'name': 'Proximity %', 'id': 'Proximity to Buy (%)'},
                            {'name': 'Potential Gain %', 'id': 'Potential Gain (%)'}
                        ],
                        style_cell={'textAlign': 'left', 'fontSize': '12px'}
                    )
                ], width=6),
                
                # Technical Analysis
                dbc.Col([
                    html.H5("Technical Analysis"),
                    html.Div(id=f'ma-analysis-{symbol}', children=[
                        html.P(f"Current Price: ₹{ma_data.get('Current_Price', 'N/A')}"),
                        html.P(f"MA10: ₹{ma_data.get('MA10', 'N/A')} ({ma_data.get('MA10_Signal', 'N/A')})"),
                        html.P(f"MA50: ₹{ma_data.get('MA50', 'N/A')} ({ma_data.get('MA50_Signal', 'N/A')})"),
                        html.P(f"MA200: ₹{ma_data.get('MA200', 'N/A')} ({ma_data.get('MA200_Signal', 'N/A')})"),
                        html.Hr(),
                        html.H6("Signals:"),
                        html.Ul([
                            html.Li(signal) for signal in ma_data.get('signals', [])
                        ] if ma_data.get('signals') else [html.Li("No specific signals")])
                    ])
                ], width=6)
            ])
        ])
    ])