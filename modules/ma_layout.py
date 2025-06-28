# modules/ma_layout.py
from dash import dcc, html

def create_ma_layout():
    return html.Div(className='section-container', children=[
        html.H3("Moving Average (MA) Signals"),
        html.Div(className='control-bar', children=[
            html.Label("Select View:"),
            dcc.Dropdown(id='ma-view-selector-dropdown',
                         options=[{'label': 'Active Primary Buys', 'value': 'primary'}, {'label': 'Active Secondary Buys', 'value': 'secondary'}],
                         value='primary', clearable=False, style={'min-width': '250px'}),
            html.Button('Refresh MA Data', id='refresh-ma-data-button', n_clicks=0)
        ]),
        dcc.Loading(type="circle", children=[html.Div(id='ma-signals-table-container')])
    ])
