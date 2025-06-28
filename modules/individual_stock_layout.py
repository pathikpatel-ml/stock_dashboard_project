# modules/individual_stock_layout.py
from dash import dcc, html
from datetime import date, timedelta
import data_manager # We still need this for the dropdown options

def create_individual_stock_layout():
    """Creates the layout for the Individual Stock Analysis section."""
    return html.Div(className='section-container', children=[
        html.H3("Individual Stock Analysis"),
        html.Div(className='control-bar', children=[
            dcc.Dropdown(
                id='company-dropdown',
                options=[{'label': sym, 'value': sym} for sym in data_manager.all_available_symbols],
                value=data_manager.all_available_symbols[0] if data_manager.all_available_symbols else None,
                placeholder="Select Company"
            ),
            dcc.DatePickerRange(
                id='date-picker-range',
                min_date_allowed=date(2000, 1, 1),
                max_date_allowed=date.today() + timedelta(days=1),
                initial_visible_month=date.today(),
                start_date=(date.today() - timedelta(days=365*2)),
                end_date=date.today(),
                display_format='YYYY-MM-DD',
                style={'min-width': '240px'}
            )
        ]),
        dcc.Loading(type="circle", children=dcc.Graph(id='price-chart')),
        html.H4("V20 Signals for Selected Company"),
        dcc.Loading(type="circle", children=[html.Div(id='v20-signals-detail-table-container', className='dash-table-container')])
    ])
