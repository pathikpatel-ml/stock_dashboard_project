# modules/v20_layout.py
from dash import dcc, html

def create_v20_layout():
    return html.Div(className='section-container', children=[
        html.H3("Stocks V20 Strategy Buy Signal"),
        html.Div(className='control-bar', children=[
            html.Button('Refresh Live Prices', id='refresh-v20-live-data-button'),
            html.Label("Filter by Proximity (%):", style={'marginLeft': '20px'}),
            dcc.Input(id='v20-proximity-filter-input', type='number', value=100, min=0, step=5, placeholder="e.g., 20"),
            html.Button('Apply Filter', id='apply-v20-filter-button')
        ]),
        html.Div(id='v20-refresh-status-message'),
        dcc.Loading(type="circle", children=[
            html.Div(id='v20-signals-table-container', className='dash-table-container')
        ])
    ])
