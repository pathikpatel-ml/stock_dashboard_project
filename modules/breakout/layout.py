"""
Dash layout for the Multi-Year Breakout strategy tab.

A single ``create_breakout_layout()`` returns the strategy section with an inner ``dcc.Tabs``
holding the six dashboard modules (doc §9.1):
  1. Breakout Alerts Feed     2. Near-Breakout Watchlist   3. Active Positions Tracker
  4. Historical / Backtest     5. Delivery Volume Analyzer   6. Alerts & Notifications

Component IDs are prefixed ``bo-`` to stay clear of the V20 (``v20-``) namespace. Styling reuses
the existing CSS classes (``section-container``, ``control-bar``, ``dash-table-container``, ``btn*``).
"""
from dash import dcc, html


def _module_alerts_feed():
    return html.Div([
        html.Div(className="control-bar", children=[
            html.Div(className="action-buttons", children=[
                html.Button([html.I(className="fa-solid fa-rotate me-2"), "Refresh"],
                            id="refresh-breakout-button", className="btn btn-primary"),
            ]),
            html.Div(id="bo-signals-meta", style={"fontSize": "13px", "color": "#6c757d"}),
        ]),
        html.P("Newly detected valid multi-year breakout setups. Click a row for the full trade plan "
               "+ historical backtest.", className="module-help"),
        dcc.Loading(type="circle", children=[
            html.Div(id="bo-signals-container", className="dash-table-container")
        ]),
        dcc.Loading(type="dot", children=[
            html.Div(id="bo-signal-detail-panel", style={"display": "none"})
        ]),
    ])


def _module_watchlist():
    return html.Div([
        html.P("Stocks within 3% of a valid multi-year resistance, ranked by Priority Score "
               "(age + delivery + proximity).", className="module-help"),
        dcc.Loading(type="circle", children=[
            html.Div(id="bo-watchlist-container", className="dash-table-container")
        ]),
    ])


def _module_positions():
    return html.Div([
        html.P("Live tracking of positions you recorded in breakout_positions.csv "
               "(P&L, T1 status, weekly 21-EMA trail, colour-coded SL).", className="module-help"),
        dcc.Loading(type="circle", children=[
            html.Div(id="bo-positions-container", className="dash-table-container")
        ]),
    ])


def _module_backtest():
    return html.Div([
        html.Div(className="control-bar", children=[
            html.Div(className="filter-group", children=[
                html.Label("Symbol:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Input(id="bo-backtest-symbol-input", type="text", placeholder="e.g. SANGHVIMOV",
                          debounce=True, style={"width": "160px"}),
                html.Button([html.I(className="fa-solid fa-play me-1"), "Run Backtest"],
                            id="bo-backtest-run-button", className="btn btn-success btn-sm"),
            ]),
        ]),
        html.P("Simulates the full hybrid plan (entry at breakout close, SL, T1 50% exit, "
               "21-EMA weekly trail) on the stock's historical multi-year breakout.",
               className="module-help"),
        dcc.Loading(type="circle", children=[html.Div(id="bo-backtest-result")]),
    ])


def _module_delivery():
    return html.Div([
        html.Div(className="control-bar", children=[
            html.Div(className="filter-group", children=[
                html.Label("Symbol:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Input(id="bo-delivery-symbol-input", type="text", placeholder="e.g. APOLLOHOSP",
                          debounce=True, style={"width": "160px"}),
                html.Button([html.I(className="fa-solid fa-magnifying-glass me-1"), "Analyze"],
                            id="bo-delivery-run-button", className="btn btn-primary btn-sm"),
            ]),
        ]),
        html.P("Delivery-volume (Smart Money) trend from NSE Bhav Copy — daily detail + monthly "
               "average. Green > 60%, red < 40%.", className="module-help"),
        dcc.Loading(type="circle", children=[
            dcc.Graph(id="bo-delivery-chart", config={"displayModeBar": False}),
            html.Div(id="bo-delivery-table", className="dash-table-container"),
        ]),
    ])


def _module_notifications():
    return html.Div([
        html.P("In-app alerts generated from the current signals, watchlist, and your positions.",
               className="module-help"),
        html.Div(id="bo-alerts-container", className="notifications-container"),
    ])


def create_breakout_layout():
    return html.Div(className="section-container", children=[
        html.H3("📈 Multi-Year Breakout Swing Strategy"),
        html.Div(id="bo-staleness-banner"),

        dcc.Interval(id="bo-auto-refresh-interval", interval=300000, n_intervals=0),  # 5 min

        dcc.Tabs(id="bo-inner-tabs", value="bo-tab-alerts", children=[
            dcc.Tab(label="🚀 Breakout Alerts", value="bo-tab-alerts", children=[_module_alerts_feed()]),
            dcc.Tab(label="👀 Watchlist", value="bo-tab-watchlist", children=[_module_watchlist()]),
            dcc.Tab(label="💼 Positions", value="bo-tab-positions", children=[_module_positions()]),
            dcc.Tab(label="🧪 Backtest", value="bo-tab-backtest", children=[_module_backtest()]),
            dcc.Tab(label="📦 Delivery Analyzer", value="bo-tab-delivery", children=[_module_delivery()]),
            dcc.Tab(label="🔔 Alerts", value="bo-tab-notifications", children=[_module_notifications()]),
        ]),
    ])
