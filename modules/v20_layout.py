# modules/v20_layout.py
import dash_bootstrap_components as dbc
from dash import dcc, html


def create_v20_layout():
    return html.Div(className="section-container", children=[

        # ── Header row ──────────────────────────────────────────────────────
        html.Div(
            className="d-flex justify-content-between align-items-center mb-3",
            children=[
                html.Div([
                    html.H5(
                        [html.I(className="fas fa-chart-line me-2 text-primary"),
                         "V20 Strategy — Buy Signals"],
                        className="mb-0 fw-semibold",
                    ),
                    # Sentiment inline badge (filled by callback)
                    html.Div(
                        id="v20-sentiment-display",
                        className="d-flex align-items-center gap-2 mt-1",
                        children=[
                            html.Span("Sentiment:", className="text-muted small"),
                            html.Span(
                                id="v20-sentiment-score",
                                children="—",
                                className="fw-semibold small",
                            ),
                            html.Span(id="v20-sentiment-label", children=""),
                        ],
                    ),
                ]),
                # Control row
                html.Div(
                    className="d-flex align-items-center gap-2 flex-wrap",
                    children=[
                        html.Span(
                            "Proximity %:",
                            className="text-muted small",
                            style={"whiteSpace": "nowrap"},
                        ),
                        dcc.Input(
                            id="v20-proximity-filter-input",
                            type="number",
                            value=100,
                            min=0,
                            step=5,
                            style={"width": "70px", "fontSize": "13px"},
                            className="form-control form-control-sm",
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-check me-1"), "Apply"],
                            id="apply-v20-filter-button",
                            color="secondary",
                            size="sm",
                            outline=True,
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-sync me-1"), "Refresh Prices"],
                            id="refresh-v20-live-data-button",
                            color="primary",
                            size="sm",
                        ),
                        dbc.Button(
                            [html.I(className="fas fa-chart-bar me-1"), "Indicators"],
                            id="refresh-v20-indicators-button",
                            color="success",
                            size="sm",
                            outline=True,
                        ),
                    ],
                ),
            ],
        ),

        html.Div(id="v20-refresh-status-message", className="mb-2"),

        # ── Main data table (primary focus) ─────────────────────────────────
        dcc.Loading(
            type="circle",
            color="#3b82f6",
            children=[html.Div(id="v20-signals-table-container")],
        ),

        # ── Notifications panel — collapsed by default ───────────────────────
        dbc.Card(
            className="mt-4",
            style={"background": "#1e293b", "border": "1px solid #334155"},
            children=[
                dbc.CardHeader(
                    dbc.Button(
                        [html.I(className="fas fa-bell me-2"), "Live Notifications"],
                        id="v20-notifications-toggle",
                        color="link",
                        n_clicks=0,
                        className="text-start w-100 p-0 text-decoration-none",
                        style={"color": "#94a3b8", "fontSize": "0.88rem"},
                    ),
                    style={"background": "transparent", "border": "none", "padding": "10px 16px"},
                ),
                dbc.Collapse(
                    id="v20-notifications-collapse",
                    is_open=False,
                    children=dbc.CardBody(
                        html.Div(
                            id="v20-notifications-container",
                            className="notifications-container",
                        ),
                        style={"padding": "8px 16px"},
                    ),
                ),
            ],
        ),

        # ── Technical Indicators — collapsed by default ──────────────────────
        dbc.Card(
            className="mt-3",
            style={"background": "#1e293b", "border": "1px solid #334155"},
            children=[
                dbc.CardHeader(
                    dbc.Button(
                        [html.I(className="fas fa-wave-square me-2"),
                         "Technical Indicators Overview"],
                        id="v20-indicators-toggle",
                        color="link",
                        n_clicks=0,
                        className="text-start w-100 p-0 text-decoration-none",
                        style={"color": "#94a3b8", "fontSize": "0.88rem"},
                    ),
                    style={"background": "transparent", "border": "none", "padding": "10px 16px"},
                ),
                dbc.Collapse(
                    id="v20-indicators-collapse",
                    is_open=False,
                    children=dbc.CardBody(
                        html.Div(id="v20-indicators-grid", className="indicators-grid"),
                        style={"padding": "8px 16px"},
                    ),
                ),
            ],
        ),

        # Historical Performance Panel — revealed when a BUY signal row is clicked
        dcc.Loading(
            type="dot",
            children=[html.Div(id="v20-stock-history-panel", style={"display": "none"})],
        ),

        # ── Intervals ─────────────────────────────────────────────────────────
        dcc.Interval(
            id="v20-auto-refresh-interval",
            interval=300_000,  # 5 minutes
            n_intervals=0,
        ),
        # Polls every 8s during startup until data is ready, then disables itself
        dcc.Interval(
            id="startup-data-poll",
            interval=8000,
            n_intervals=0,
            disabled=False,
        ),
    ])
