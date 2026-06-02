import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html


def create_kite_settings_layout():
    return dbc.Container(
        fluid=True,
        className="p-4",
        children=[
            html.H4("Zerodha Kite Settings", className="mb-4 section-title"),

            dbc.Row([
                # ── Left column: credentials + connection ──────────────────
                dbc.Col(md=6, children=[

                    dbc.Card(className="mb-4 section-container", children=dbc.CardBody([
                        html.H6("API Credentials", className="card-title mb-3"),

                        dbc.Label("API Key"),
                        dbc.Input(
                            id="kite-api-key-input",
                            type="text",
                            placeholder="Paste your Kite API Key",
                            className="mb-3",
                        ),

                        dbc.Label("API Secret"),
                        dbc.Input(
                            id="kite-api-secret-input",
                            type="password",
                            placeholder="Paste your Kite API Secret",
                            className="mb-3",
                        ),

                        dbc.Button(
                            [html.I(className="fas fa-save me-2"), "Save Credentials"],
                            id="save-kite-creds-btn",
                            color="primary",
                            size="sm",
                            className="me-2",
                            n_clicks=0,
                        ),
                        html.Div(id="kite-creds-status", className="mt-2 small"),
                    ])),

                    dbc.Card(className="mb-4 section-container", children=dbc.CardBody([
                        html.H6("Kite Connection", className="card-title mb-3"),

                        html.Div(id="kite-connection-status", className="mb-3"),

                        dbc.Button(
                            [html.I(className="fas fa-external-link-alt me-2"),
                             "Connect Zerodha"],
                            id="connect-kite-btn",
                            color="success",
                            size="sm",
                            className="me-2",
                            n_clicks=0,
                        ),
                        html.Div(
                            "After clicking, log in on Kite — you'll be redirected back automatically.",
                            className="small text-muted mt-2",
                        ),
                        html.Div(id="kite-token-status", className="mt-2 small"),

                        # Hidden location used to redirect to Kite login URL
                        dcc.Location(id="kite-login-redirect", refresh=True),
                    ])),
                ]),

                # ── Right column: preferences + GTT log ────────────────────
                dbc.Col(md=6, children=[

                    dbc.Card(className="mb-4 section-container", children=dbc.CardBody([
                        html.H6("GTT Preferences", className="card-title mb-3"),

                        dbc.Label(id="proximity-threshold-label",
                                  children="Proximity Threshold: 2.0%"),
                        dcc.Slider(
                            id="proximity-threshold-slider",
                            min=0.5, max=10.0, step=0.5, value=2.0,
                            marks={i: f"{i}%" for i in range(1, 11)},
                            className="mb-4",
                        ),

                        dbc.Label(id="max-allocation-label",
                                  children="Max Allocation per Stock: 3.0%"),
                        dcc.Slider(
                            id="max-allocation-slider",
                            min=0.5, max=10.0, step=0.5, value=3.0,
                            marks={i: f"{i}%" for i in range(1, 11)},
                            className="mb-4",
                        ),

                        dbc.Switch(
                            id="gtt-enabled-switch",
                            label="Enable Automatic GTT Creation (runs 8:30 AM IST, Mon–Fri)",
                            value=False,
                            className="mb-3",
                        ),

                        dbc.Button(
                            [html.I(className="fas fa-save me-2"), "Save Preferences"],
                            id="save-kite-prefs-btn",
                            color="primary",
                            size="sm",
                            n_clicks=0,
                        ),
                        html.Div(id="kite-prefs-status", className="mt-2 small"),
                    ])),

                    dbc.Card(className="section-container", children=dbc.CardBody([
                        html.H6("Today's GTT Log", className="card-title mb-3"),
                        dbc.Button(
                            [html.I(className="fas fa-play me-2"),
                             "Run GTT Job Now (test)"],
                            id="run-gtt-job-btn",
                            color="warning",
                            size="sm",
                            className="mb-3",
                            n_clicks=0,
                        ),
                        html.Div(id="gtt-log-container"),
                    ])),
                ]),
            ]),

            # Interval to auto-refresh connection status
            dcc.Interval(id="kite-status-interval", interval=30_000, n_intervals=0),

            # Stores page load trigger
            dcc.Store(id="kite-settings-loaded"),
        ],
    )
