import dash_bootstrap_components as dbc
from dash import dcc, html


# ── Wizard progress indicator ──────────────────────────────────────────────

def _progress_bar(current_step: int) -> html.Div:
    steps = [
        (1, "fas fa-code", "Dev Account"),
        (2, "fas fa-key", "API Keys"),
        (3, "fas fa-plug", "Connect"),
        (4, "fas fa-sliders-h", "Preferences"),
    ]
    items = []
    for i, (n, icon, label) in enumerate(steps):
        if n < current_step:
            badge_color, text_class = "success", ""
            badge_content = html.I(className="fas fa-check")
        elif n == current_step:
            badge_color, text_class = "primary", "fw-semibold"
            badge_content = str(n)
        else:
            badge_color, text_class = "secondary", "text-muted"
            badge_content = str(n)

        items.append(
            html.Div([
                dbc.Badge(
                    badge_content,
                    color=badge_color,
                    className="wizard-badge",
                    style={"width": "2rem", "height": "2rem",
                           "display": "inline-flex", "alignItems": "center",
                           "justifyContent": "center", "borderRadius": "50%",
                           "fontSize": "0.85rem"},
                ),
                html.Div(label, className=f"wizard-step-label small {text_class}",
                         style={"marginTop": "4px"}),
            ], className="wizard-step text-center",
               style={"flex": "1"})
        )
        if i < len(steps) - 1:
            connector_color = "#22c55e" if current_step > n else "#334155"
            items.append(
                html.Div(style={
                    "flex": "1", "height": "2px", "background": connector_color,
                    "marginTop": "1rem", "alignSelf": "flex-start",
                })
            )

    return html.Div(
        items,
        style={
            "display": "flex", "alignItems": "flex-start",
            "padding": "1rem 0", "marginBottom": "1.5rem",
        }
    )


# ── Step cards ─────────────────────────────────────────────────────────────

def _step1_card() -> html.Div:
    return dbc.Card(className="section-container", children=dbc.CardBody([
        html.H5([html.I(className="fas fa-code me-2 text-primary"),
                 "Create a Kite Connect Developer Account"],
                className="mb-3"),
        html.P("You need a free Kite Connect API key to use GTT automation. "
               "This is a one-time setup.", className="text-muted"),
        html.Hr(),
        dbc.ListGroup([
            dbc.ListGroupItem([
                dbc.Badge("1", color="primary", className="me-2"),
                html.Span("Go to "), html.Strong("developers.kite.trade"),
                html.Span(" and sign up (use any email — it's free)"),
            ], className="border-0 ps-0"),
            dbc.ListGroupItem([
                dbc.Badge("2", color="primary", className="me-2"),
                html.Span("After login, click "),
                html.Strong("My Apps → Create new app"),
            ], className="border-0 ps-0"),
            dbc.ListGroupItem([
                dbc.Badge("3", color="primary", className="me-2"),
                html.Span("App type: "),
                dbc.Badge("Personal", color="success", className="me-1"),
                html.Span("(free, includes GTT + portfolio)"),
            ], className="border-0 ps-0"),
            dbc.ListGroupItem([
                dbc.Badge("4", color="primary", className="me-2"),
                html.Span("Set Redirect URL to:"),
                html.Br(),
                html.Code(
                    "https://stock-dashboard-project.onrender.com/kite/callback",
                    style={"background": "#0f172a", "padding": "2px 6px",
                           "borderRadius": "4px", "fontSize": "0.8rem"},
                ),
            ], className="border-0 ps-0"),
        ], flush=True, className="mb-4"),
        html.Div(
            className="d-flex justify-content-between align-items-center",
            children=[
                html.A(
                    [html.I(className="fas fa-external-link-alt me-1"),
                     "Open developers.kite.trade"],
                    href="https://developers.kite.trade",
                    target="_blank",
                    className="btn btn-outline-primary btn-sm",
                ),
                dbc.Button(
                    ["I have my API Key & Secret ",
                     html.I(className="fas fa-arrow-right ms-1")],
                    id="wizard-step1-next",
                    color="primary",
                    n_clicks=0,
                ),
            ],
        ),
    ]))


def _step2_card(api_key_saved: bool = False) -> html.Div:
    placeholder = "•••• saved (enter new key to update)" if api_key_saved else "Paste your API Key"
    return dbc.Card(className="section-container", children=dbc.CardBody([
        html.H5([html.I(className="fas fa-key me-2 text-primary"),
                 "Enter Your API Credentials"],
                className="mb-3"),
        html.P(["Find these in your Kite developer app under ",
                html.Strong("My Apps → your app → API details"),
                "."],
               className="text-muted small mb-4"),
        dbc.Label("API Key"),
        dbc.Input(id="kite-api-key-input", type="text",
                  placeholder=placeholder, className="mb-3"),
        dbc.Label("API Secret"),
        dbc.Input(id="kite-api-secret-input", type="password",
                  placeholder="Paste your API Secret", className="mb-4"),
        html.Div(id="kite-creds-status", className="mb-3"),
        html.Div(
            className="d-flex justify-content-between",
            children=[
                dbc.Button(
                    [html.I(className="fas fa-arrow-left me-1"), "Back"],
                    id="wizard-step2-back",
                    color="secondary",
                    outline=True,
                    n_clicks=0,
                ),
                dbc.Button(
                    [html.I(className="fas fa-save me-1"), "Save & Continue"],
                    id="save-kite-creds-btn",
                    color="primary",
                    n_clicks=0,
                ),
            ],
        ),
    ]))


def _step3_card(connection_badge) -> html.Div:
    return dbc.Card(className="section-container", children=dbc.CardBody([
        html.H5([html.I(className="fas fa-plug me-2 text-primary"),
                 "Connect Your Zerodha Account"],
                className="mb-3"),
        html.Div(
            className="d-flex align-items-center mb-4",
            children=[
                html.Span("Status: ", className="text-muted me-2"),
                connection_badge,
            ],
        ),
        dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"),
             "Click the button below to log in with your Zerodha User ID "
             "(e.g. AB1234). You'll be redirected back here automatically."],
            color="info",
            className="mb-4",
            style={"fontSize": "0.88rem"},
        ),
        dbc.Button(
            [html.I(className="fas fa-external-link-alt me-2"),
             "Connect Zerodha Account"],
            id="connect-kite-btn",
            color="success",
            size="lg",
            className="w-100 mb-3",
            n_clicks=0,
        ),
        html.Div(id="kite-token-status", className="mb-3"),
        html.Div(
            className="d-flex justify-content-between",
            children=[
                dbc.Button(
                    [html.I(className="fas fa-arrow-left me-1"), "Back"],
                    id="wizard-step3-back",
                    color="secondary",
                    outline=True,
                    n_clicks=0,
                ),
                dbc.Button(
                    ["Continue ", html.I(className="fas fa-arrow-right ms-1")],
                    id="wizard-step3-next",
                    color="primary",
                    n_clicks=0,
                ),
            ],
        ),
        dcc.Location(id="kite-login-redirect", refresh=True),
    ]))


def _step4_card(settings: dict, exclusions: list) -> html.Div:
    proximity_val = settings.get("proximity_threshold_pct", 2.0)
    allocation_val = settings.get("max_allocation_pct", 3.0)
    gtt_enabled = settings.get("gtt_enabled", False)

    exclusion_tags = [
        dbc.Badge(
            [sym, html.Span(" ×", id={"type": "del-exclusion", "symbol": sym},
                            style={"cursor": "pointer", "marginLeft": "4px"})],
            color="secondary",
            className="me-1 mb-1 p-2",
            style={"fontSize": "0.8rem"},
        )
        for sym in exclusions
    ]

    return dbc.Card(className="section-container", children=dbc.CardBody([
        html.H5([html.I(className="fas fa-sliders-h me-2 text-primary"),
                 "GTT Preferences"],
                className="mb-4"),

        dbc.Row([
            dbc.Col(md=6, children=[
                html.Label(id="proximity-threshold-label",
                           children=f"Proximity Threshold: {proximity_val}%",
                           className="small fw-semibold"),
                html.P("How close to the buy target before creating a GTT",
                       className="text-muted small mb-2"),
                dcc.Slider(
                    id="proximity-threshold-slider",
                    min=0.5, max=10.0, step=0.5, value=proximity_val,
                    marks={i: f"{i}%" for i in range(1, 11)},
                    className="mb-4",
                ),
            ]),
            dbc.Col(md=6, children=[
                html.Label(id="max-allocation-label",
                           children=f"Max Allocation per Stock: {allocation_val}%",
                           className="small fw-semibold"),
                html.P("Maximum % of your portfolio to allocate to one stock",
                       className="text-muted small mb-2"),
                dcc.Slider(
                    id="max-allocation-slider",
                    min=0.5, max=10.0, step=0.5, value=allocation_val,
                    marks={i: f"{i}%" for i in range(1, 11)},
                    className="mb-4",
                ),
            ]),
        ]),

        html.Hr(),

        html.Label("Excluded Stocks", className="small fw-semibold"),
        html.P("GTT orders will never be created for these stocks.",
               className="text-muted small mb-2"),
        html.Div(exclusion_tags, id="exclusion-tags", className="mb-2"),
        dbc.InputGroup([
            dbc.Input(
                id="exclusion-input",
                placeholder="Add stock symbol e.g. HINDCOPPER",
                maxLength=20,
            ),
            dbc.Button(
                [html.I(className="fas fa-plus me-1"), "Add"],
                id="add-exclusion-btn",
                color="secondary",
                outline=True,
                n_clicks=0,
            ),
        ], className="mb-4"),

        html.Hr(),

        dbc.Card(
            dbc.CardBody([
                dbc.Switch(
                    id="gtt-enabled-switch",
                    label=[
                        html.Strong("Enable Automatic GTT Creation"),
                        html.Br(),
                        html.Span(
                            "Runs at 8:30 AM IST, Mon–Fri. Only creates GTTs for "
                            "BUY / BUY NOW / STRONG BUY signals with MACD confirmation.",
                            className="text-muted small",
                        ),
                    ],
                    value=gtt_enabled,
                    className="mb-0",
                ),
            ]),
            className="mb-4",
            style={"background": "#0f172a", "border": "1px solid #334155"},
        ),

        html.Div(id="kite-prefs-status", className="mb-3"),

        html.Div(
            className="d-flex justify-content-between",
            children=[
                dbc.Button(
                    [html.I(className="fas fa-arrow-left me-1"), "Back"],
                    id="wizard-step4-back",
                    color="secondary",
                    outline=True,
                    n_clicks=0,
                ),
                dbc.Button(
                    [html.I(className="fas fa-check me-1"), "Save & Activate"],
                    id="save-kite-prefs-btn",
                    color="success",
                    n_clicks=0,
                ),
            ],
        ),
    ]))


# ── Connection badge helper ─────────────────────────────────────────────────

def _connection_badge_from_settings(settings: dict):
    """Return a dbc.Badge indicating Kite connection status."""
    import dash_bootstrap_components as dbc
    from dash import html
    if not settings.get("access_token_enc"):
        return dbc.Badge(
            [html.I(className="fas fa-times-circle me-1"), "Not Connected"],
            color="secondary", className="fs-6 p-2",
        )
    # Check token age via portfolio helper
    try:
        from modules.kite import portfolio as kite_portfolio
        valid = kite_portfolio.is_token_valid(settings.get("access_token_set_at"))
    except Exception:
        valid = False
    if valid:
        return dbc.Badge(
            [html.I(className="fas fa-circle me-1"), "Connected"],
            color="success", className="fs-6 p-2",
        )
    return dbc.Badge(
        [html.I(className="fas fa-exclamation-triangle me-1"), "Token Expired — Reconnect"],
        color="warning", className="fs-6 p-2",
    )


# ── Main wizard layout ──────────────────────────────────────────────────────

def create_kite_settings_layout():
    return dbc.Container(
        fluid=True,
        className="p-4",
        style={"maxWidth": "800px"},
        children=[
            html.H4([
                html.I(className="fas fa-chart-line me-2"),
                "Zerodha GTT Automation",
            ], className="mb-1"),
            html.P("Set up automatic GTT buy orders before market open.",
                   className="text-muted mb-4"),

            # Progress bar (updated by callback)
            html.Div(id="wizard-progress"),

            # Step content (updated by callback)
            html.Div(id="wizard-step-content"),

            # State
            dcc.Store(id="kite-wizard-step", data=None),
            dcc.Store(id="kite-settings-loaded"),

            # Test run card (always visible at bottom once connected)
            html.Div(id="wizard-test-run-section"),

            # Intervals
            dcc.Interval(id="kite-status-interval", interval=30_000, n_intervals=0),
        ],
    )
