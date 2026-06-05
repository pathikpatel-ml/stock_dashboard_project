"""
Groww-specific UI components for the unified Broker Automation Setup tab.
Provides the broker-picker intro card, Groww wizard steps 1-4, and dashboard panels.
"""
import dash_bootstrap_components as dbc
from dash import dcc, html


# ── Broker picker (step 0 — shown to brand new users) ──────────────────────

def broker_picker_card() -> html.Div:
    """Landing card that lets a new user choose Zerodha or Groww."""
    return dbc.Card(className="section-container", children=dbc.CardBody([

        html.Div(className="text-center mb-4", children=[
            html.Div(style={"fontSize": "3rem", "marginBottom": "0.75rem"},
                     children=html.I(className="fas fa-robot text-primary")),
            html.H4("Automate Your GTT Buy Orders", className="fw-bold mb-2"),
            html.P(
                "Place GTT orders automatically at 8:30 AM IST before market open — "
                "based on your V20 STRONG BUY and Breakout signals.",
                className="text-muted",
                style={"maxWidth": "520px", "margin": "0 auto", "fontSize": "0.95rem"},
            ),
        ]),

        html.Hr(style={"borderColor": "#334155", "margin": "1.5rem 0"}),
        html.P("Choose your trading platform to get started:",
               className="fw-semibold mb-3 text-center"),

        dbc.Row(className="mb-4 g-3", children=[

            # Zerodha card
            dbc.Col(md=6, children=dbc.Card(
                dbc.CardBody([
                    html.Div(className="d-flex align-items-center mb-3", children=[
                        html.Div("Z", style={
                            "width": "40px", "height": "40px", "borderRadius": "8px",
                            "background": "#FF6600", "color": "white", "fontWeight": "700",
                            "fontSize": "1.2rem", "display": "flex", "alignItems": "center",
                            "justifyContent": "center", "marginRight": "12px", "flexShrink": "0",
                        }),
                        html.Div([
                            html.H6("Zerodha KiteConnect", className="mb-0 fw-bold"),
                            html.Small("India's #1 broker", className="text-muted"),
                        ]),
                    ]),
                    html.Ul([
                        html.Li("Mature, battle-tested API"),
                        html.Li("OAuth login (reconnect daily)"),
                        html.Li([html.A("developers.kite.trade",
                                         href="https://developers.kite.trade",
                                         target="_blank",
                                         style={"color": "#60a5fa", "fontSize": "0.82rem"})]),
                    ], className="text-muted small mb-3",
                       style={"paddingLeft": "18px", "lineHeight": "1.9"}),
                    dbc.Alert(
                        [html.I(className="fas fa-clock me-1"),
                         "Requires API subscription — ",
                         html.A("check pricing", href="https://developers.kite.trade",
                                target="_blank", className="alert-link")],
                        color="secondary", className="mb-3 py-2",
                        style={"fontSize": "0.8rem"},
                    ),
                    dbc.Button(
                        ["Use Zerodha ", html.I(className="fas fa-arrow-right ms-1")],
                        id="pick-zerodha-btn",
                        color="outline-primary",
                        className="w-100",
                        n_clicks=0,
                    ),
                ]),
                style={"background": "#1e293b", "border": "1px solid #334155", "height": "100%"},
            )),

            # Groww card
            dbc.Col(md=6, children=dbc.Card(
                dbc.CardBody([
                    html.Div(className="d-flex align-items-center mb-3", children=[
                        html.Div("G", style={
                            "width": "40px", "height": "40px", "borderRadius": "8px",
                            "background": "#00D09C", "color": "white", "fontWeight": "700",
                            "fontSize": "1.2rem", "display": "flex", "alignItems": "center",
                            "justifyContent": "center", "marginRight": "12px", "flexShrink": "0",
                        }),
                        html.Div([
                            html.H6("Groww Trade API", className="mb-0 fw-bold"),
                            html.Span(dbc.Badge("Auto-refresh available",
                                               color="success", className="ms-1",
                                               style={"fontSize": "0.65rem"})),
                        ]),
                    ]),
                    html.Ul([
                        html.Li([html.Strong("TOTP auto-refresh: "),
                                 html.Span("store secret once, never reconnect again",
                                           className="text-success")]),
                        html.Li("Full GTT (Smart Orders) support"),
                        html.Li([html.A("groww.in/trade-api",
                                         href="https://groww.in/trade-api",
                                         target="_blank",
                                         style={"color": "#60a5fa", "fontSize": "0.82rem"})]),
                    ], className="text-muted small mb-3",
                       style={"paddingLeft": "18px", "lineHeight": "1.9"}),
                    dbc.Alert(
                        [html.I(className="fas fa-clock me-1"),
                         "Requires API subscription — ",
                         html.A("check pricing", href="https://groww.in/trade-api",
                                target="_blank", className="alert-link")],
                        color="secondary", className="mb-3 py-2",
                        style={"fontSize": "0.8rem"},
                    ),
                    dbc.Button(
                        ["Use Groww ", html.I(className="fas fa-arrow-right ms-1")],
                        id="pick-groww-btn",
                        color="primary",
                        className="w-100",
                        n_clicks=0,
                    ),
                ]),
                style={"background": "#1e293b", "border": "1px solid #00D09C", "height": "100%"},
            )),
        ]),

        html.P(
            "You can switch brokers anytime from the settings. "
            "Your existing signals and exclusions are not affected.",
            className="text-muted small text-center mb-0",
        ),

    ]))


# ── Groww wizard step helpers ───────────────────────────────────────────────

def _step(n: int, text) -> html.Div:
    return html.Div(
        className="d-flex align-items-start mb-3",
        children=[
            html.Div(str(n), style={
                "minWidth": "26px", "height": "26px", "borderRadius": "50%",
                "background": "#083d2f", "border": "1px solid #00D09C", "color": "#00D09C",
                "display": "flex", "alignItems": "center", "justifyContent": "center",
                "fontSize": "0.78rem", "fontWeight": "700", "marginRight": "12px",
                "marginTop": "2px", "flexShrink": "0",
            }),
            html.Div(text, style={"color": "#cbd5e1", "fontSize": "0.875rem",
                                   "lineHeight": "1.6"}),
        ],
    )


def _groww_progress_bar(current_step: int) -> html.Div:
    steps = [
        (1, "fas fa-id-card",    "Get Credentials"),
        (2, "fas fa-key",        "API Keys"),
        (3, "fas fa-plug",       "Connect"),
        (4, "fas fa-sliders-h",  "Preferences"),
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

        items.append(html.Div([
            dbc.Badge(badge_content, color=badge_color, className="wizard-badge",
                      style={"width": "2rem", "height": "2rem", "display": "inline-flex",
                             "alignItems": "center", "justifyContent": "center",
                             "borderRadius": "50%", "fontSize": "0.85rem"}),
            html.Div(label, className=f"wizard-step-label small {text_class}",
                     style={"marginTop": "4px"}),
        ], className="wizard-step text-center", style={"flex": "1"}))

        if i < len(steps) - 1:
            connector_color = "#22c55e" if current_step > n else "#334155"
            items.append(html.Div(style={"flex": "1", "height": "2px",
                                         "background": connector_color,
                                         "marginTop": "1rem", "alignSelf": "flex-start"}))
    return html.Div(items, style={"display": "flex", "alignItems": "flex-start",
                                  "padding": "1rem 0", "marginBottom": "1.5rem"})


# ── Groww wizard step 1 — Get API credentials ───────────────────────────────

def groww_step1_card() -> html.Div:
    return dbc.Card(className="section-container", children=dbc.CardBody([

        html.H5([html.I(className="fas fa-id-card me-2", style={"color": "#00D09C"}),
                 "Subscribe to Groww Trade API"],
                className="mb-1 fw-semibold"),
        html.P("You need an active Groww trading account and a Trade API subscription.",
               className="text-muted small mb-4"),

        dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"),
             html.Strong("Prerequisite: "),
             "You must already have a Groww demat/trading account. "
             "If you don't have one, open an account at ",
             html.A("groww.in", href="https://groww.in", target="_blank",
                    className="alert-link"), " first."],
            color="info", className="mb-4", style={"fontSize": "0.85rem"},
        ),

        html.Hr(style={"borderColor": "#334155"}),
        html.P("Follow these steps to get your API credentials:",
               className="small fw-semibold mb-3"),

        _step(1, [
            "Open the Groww Trade API page: ",
            html.A("groww.in/trade-api", href="https://groww.in/trade-api",
                   target="_blank", style={"color": "#60a5fa"}),
            " and click ", html.Strong("Get Started"), " or ", html.Strong("Subscribe"),
            ".",
        ]),
        _step(2, [
            "Log in with your Groww account. Go to your profile → Settings → ",
            html.Strong("Trading APIs"), " in the side panel.",
        ]),
        _step(3, [
            "Click ", html.Strong("Generate API Keys"), " → choose ",
            html.Strong("API Key & Secret"), ".",
            " Copy both your ", html.Strong("App ID"), " (API Key) and ",
            html.Strong("App Secret"), ".",
        ]),
        _step(4, [
            html.Strong("Optional (highly recommended): "),
            "Enable TOTP setup to get your ",
            html.Strong("TOTP Secret"), " (a Base32 string like ",
            html.Em("JBSWY3DPEHPK3PXP"), "). This allows the dashboard to ",
            html.Span("automatically refresh your token every morning",
                      style={"color": "#00D09C", "fontWeight": "600"}),
            " — no daily reconnection required.",
        ]),

        dbc.Alert(
            [html.I(className="fas fa-star me-2", style={"color": "#00D09C"}),
             html.Strong("Groww advantage: "),
             "With TOTP auto-refresh, you ", html.Strong("never need to reconnect manually"),
             ". The system generates a fresh token at 6:15 AM IST every day automatically."],
            color="success", className="mt-3 mb-4", style={"fontSize": "0.85rem"},
        ),

        html.Hr(style={"borderColor": "#334155"}),
        html.Div(className="d-flex justify-content-between align-items-center mt-3", children=[
            html.A(
                [html.I(className="fas fa-external-link-alt me-1"), "Open Groww Trade API"],
                href="https://groww.in/trade-api",
                target="_blank",
                className="btn btn-outline-primary btn-sm",
            ),
            dbc.Button(
                ["I have my credentials ",
                 html.I(className="fas fa-arrow-right ms-1")],
                id="groww-wizard-step1-next",
                color="primary",
                n_clicks=0,
            ),
        ]),

        html.Div(className="mt-3 pt-2", style={"borderTop": "1px solid #1e3a5f"}, children=[
            dbc.Button(
                [html.I(className="fas fa-exchange-alt me-1"), "Switch to Zerodha instead"],
                id="groww-switch-to-zerodha-btn",
                color="secondary",
                outline=True,
                size="sm",
                n_clicks=0,
            ),
        ]),
    ]))


# ── Groww wizard step 2 — Enter credentials ─────────────────────────────────

def groww_step2_card(app_id_saved: bool = False) -> html.Div:
    app_id_placeholder = ("•••••••••••• already saved (enter new to update)"
                          if app_id_saved else "e.g. your-groww-app-id")
    return dbc.Card(className="section-container", children=dbc.CardBody([

        html.H5([html.I(className="fas fa-key me-2", style={"color": "#00D09C"}),
                 "Enter Your Groww API Credentials"],
                className="mb-1 fw-semibold"),
        html.P("Paste the credentials from your Groww developer settings.",
               className="text-muted small mb-4"),

        # Where to find them
        dbc.Card(dbc.CardBody([
            html.P([html.I(className="fas fa-map-marker-alt me-2 text-primary"),
                    html.Strong("Where to find these:")], className="mb-2 small"),
            html.Ol([
                html.Li(["Go to ", html.A("groww.in/trade-api/api-keys",
                                           href="https://groww.in/trade-api/api-keys",
                                           target="_blank", style={"color": "#60a5fa"})]),
                html.Li(["Your ", html.Strong("App ID"), " is your API Key"]),
                html.Li(["Click ", html.Strong("Show Secret"), " for your App Secret"]),
                html.Li(["For TOTP: scan the QR code or copy the ",
                          html.Strong("TOTP Secret"), " (Base32 string)"]),
            ], style={"color": "#94a3b8", "fontSize": "0.83rem",
                      "paddingLeft": "18px", "marginBottom": "0"}),
        ]), className="mb-4", style={"background": "#0f172a", "border": "1px solid #083d2f"}),

        dbc.Label([html.I(className="fas fa-key me-1", style={"color": "#00D09C"}),
                   " App ID (API Key)"],
                  className="small fw-semibold"),
        dbc.Input(id="groww-app-id-input", type="text",
                  placeholder=app_id_placeholder, className="mb-1"),
        html.P("Your Groww API Key (alphanumeric string)",
               className="text-muted mb-3", style={"fontSize": "0.78rem"}),

        dbc.Label([html.I(className="fas fa-lock me-1 text-warning"), " App Secret"],
                  className="small fw-semibold"),
        dbc.Input(id="groww-app-secret-input", type="password",
                  placeholder="Paste your App Secret", className="mb-1"),
        html.P("Your Groww API Secret (keep this private)",
               className="text-muted mb-3", style={"fontSize": "0.78rem"}),

        html.Hr(style={"borderColor": "#334155"}),

        # TOTP section
        html.Div(className="mb-4", children=[
            dbc.Card(dbc.CardBody([
                dbc.Switch(
                    id="groww-totp-auto-switch",
                    label=[
                        html.Span([html.I(className="fas fa-magic me-1",
                                          style={"color": "#00D09C"}),
                                   html.Strong(" Enable TOTP Auto-Refresh"),
                                   html.Span(" (Recommended)",
                                             style={"color": "#00D09C", "fontSize": "0.82rem"})],
                                  style={"color": "#f1f5f9"}),
                        html.Br(),
                        html.Span(
                            "Store your TOTP secret once — the dashboard generates a fresh "
                            "token automatically at 6:15 AM IST every morning. "
                            "No daily reconnection required.",
                            style={"color": "#94a3b8", "fontSize": "0.82rem"},
                        ),
                    ],
                    value=True,
                    className="mb-2",
                ),
                html.Div(id="groww-totp-input-section", children=[
                    dbc.Label([html.I(className="fas fa-shield-alt me-1 text-warning"),
                               " TOTP Secret"],
                              className="small fw-semibold mt-2"),
                    dbc.Input(id="groww-totp-secret-input", type="password",
                              placeholder="e.g. JBSWY3DPEHPK3PXP (Base32 string)",
                              className="mb-1"),
                    html.P(
                        "Scan the QR code in Groww's TOTP setup with an authenticator app "
                        "like Google Authenticator, then copy the secret key shown below the QR.",
                        className="text-muted mb-0", style={"fontSize": "0.78rem"},
                    ),
                ]),
            ]), style={"background": "#0d1f17", "border": "1px solid #00D09C"}),
        ]),

        dbc.Alert(
            [html.I(className="fas fa-shield-alt me-2"),
             "Credentials are ", html.Strong("AES-256 encrypted"),
             " before storage. They never leave the server in plain text."],
            color="info", className="mb-4", style={"fontSize": "0.83rem"},
        ),

        html.Div(id="groww-creds-status", className="mb-3"),

        html.Div(className="d-flex justify-content-between", children=[
            dbc.Button([html.I(className="fas fa-arrow-left me-1"), "Back"],
                       id="groww-wizard-step2-back", color="secondary", outline=True, n_clicks=0),
            dbc.Button([html.I(className="fas fa-save me-1"), "Save & Continue"],
                       id="save-groww-creds-btn", color="primary", n_clicks=0),
        ]),
    ]))


# ── Groww wizard step 3 — Connect / generate token ──────────────────────────

def groww_step3_card(settings: dict) -> html.Div:
    is_totp = settings.get("totp_auto_refresh", False) and settings.get("totp_secret_enc")
    token_set = bool(settings.get("access_token_enc"))

    from modules.groww.portfolio import is_token_valid
    token_valid = is_token_valid(settings.get("access_token_set_at")) if token_set else False

    status_badge = None
    if token_valid:
        status_badge = dbc.Badge(
            [html.I(className="fas fa-circle me-1"), "Connected"],
            color="success", className="fs-6 p-2",
        )
    elif token_set:
        status_badge = dbc.Badge(
            [html.I(className="fas fa-exclamation-triangle me-1"), "Token Expired"],
            color="warning", className="fs-6 p-2",
        )
    else:
        status_badge = dbc.Badge(
            [html.I(className="fas fa-times-circle me-1"), "Not Connected"],
            color="secondary", className="fs-6 p-2",
        )

    if is_totp:
        connect_content = html.Div([
            dbc.Alert(
                [html.I(className="fas fa-magic me-2", style={"color": "#00D09C"}),
                 html.Strong("TOTP Auto-Refresh is enabled. "),
                 "Click the button below — the dashboard generates your token automatically "
                 "using the TOTP secret you saved. No browser login needed."],
                color="success", className="mb-3", style={"fontSize": "0.85rem"},
            ),
            dbc.Button(
                [html.I(className="fas fa-bolt me-2"), "Generate & Test Token"],
                id="groww-generate-token-btn",
                color="success",
                size="lg",
                className="w-100 mb-3",
                n_clicks=0,
            ),
        ])
    else:
        connect_content = html.Div([
            dbc.Alert(
                [html.I(className="fas fa-info-circle me-2"),
                 html.Strong("Manual mode. "),
                 "Get your access token from the ",
                 html.A("Groww developer portal",
                        href="https://groww.in/trade-api/api-keys",
                        target="_blank", style={"color": "#93c5fd"}),
                 " and paste it below. You will need to do this once per day "
                 "(tokens reset at 6:00 AM IST)."],
                color="info", className="mb-3", style={"fontSize": "0.85rem"},
            ),
            dbc.Label("Access Token", className="small fw-semibold"),
            dbc.Input(id="groww-manual-token-input", type="password",
                      placeholder="Paste your Groww access token here", className="mb-3"),
            dbc.Button(
                [html.I(className="fas fa-save me-2"), "Save & Test Token"],
                id="groww-save-manual-token-btn",
                color="primary",
                size="lg",
                className="w-100 mb-3",
                n_clicks=0,
            ),
        ])

    # Dummy inputs for callbacks — only one set will be in DOM depending on mode
    if is_totp:
        hidden_manual = html.Div([
            dbc.Input(id="groww-manual-token-input", type="hidden", className="d-none"),
            html.Div(id="groww-save-manual-token-btn-wrapper",
                     children=dbc.Button("", id="groww-save-manual-token-btn",
                                         n_clicks=0, className="d-none")),
        ], className="d-none")
    else:
        hidden_manual = html.Div(
            dbc.Button("", id="groww-generate-token-btn", n_clicks=0, className="d-none"),
            className="d-none"
        )

    return dbc.Card(className="section-container", children=dbc.CardBody([

        html.H5([html.I(className="fas fa-plug me-2", style={"color": "#00D09C"}),
                 "Connect Your Groww Account"],
                className="mb-1 fw-semibold"),
        html.P("Authorise this dashboard to place Smart Orders on your behalf.",
               className="text-muted small mb-4"),

        html.Div(className="d-flex align-items-center mb-4", children=[
            html.Span("Status: ", className="text-muted me-2 small"),
            status_badge,
        ]),

        connect_content,
        hidden_manual,

        html.Div(id="groww-token-status", className="mb-3"),

        html.Div(className="d-flex justify-content-between", children=[
            dbc.Button([html.I(className="fas fa-arrow-left me-1"), "Back"],
                       id="groww-wizard-step3-back", color="secondary", outline=True, n_clicks=0),
            dbc.Button(["Continue ", html.I(className="fas fa-arrow-right ms-1")],
                       id="groww-wizard-step3-next", color="primary", n_clicks=0),
        ]),
    ]))


# ── Groww wizard step 4 — Preferences ───────────────────────────────────────

def groww_step4_card(settings: dict, exclusions: list) -> html.Div:
    proximity_val = settings.get("proximity_threshold_pct", 2.0)
    allocation_val = settings.get("max_allocation_pct", 3.0)
    gtt_enabled = settings.get("gtt_enabled", False)
    exclusion_tags = [
        dbc.Badge(
            [sym, html.Span(" ×", id={"type": "groww-del-exclusion", "symbol": sym},
                            style={"cursor": "pointer", "marginLeft": "4px"})],
            color="secondary", className="me-1 mb-1 p-2",
            style={"fontSize": "0.8rem"},
        )
        for sym in exclusions
    ]
    return dbc.Card(className="section-container", children=dbc.CardBody([
        html.H5([html.I(className="fas fa-sliders-h me-2", style={"color": "#00D09C"}),
                 "GTT Preferences"], className="mb-4"),
        dbc.Row([
            dbc.Col(md=6, children=[
                html.Label(id="groww-proximity-threshold-label",
                           children=f"Proximity Threshold: {proximity_val}%",
                           className="small fw-semibold"),
                html.P("How close to the buy target before creating a Smart Order",
                       className="text-muted small mb-2"),
                dcc.Slider(id="groww-proximity-threshold-slider", min=0.5, max=10.0, step=0.5,
                           value=proximity_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
            dbc.Col(md=6, children=[
                html.Label(id="groww-max-allocation-label",
                           children=f"Max Allocation per Stock: {allocation_val}%",
                           className="small fw-semibold"),
                html.P("Maximum % of portfolio per stock",
                       className="text-muted small mb-2"),
                dcc.Slider(id="groww-max-allocation-slider", min=0.5, max=10.0, step=0.5,
                           value=allocation_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
        ]),
        html.Hr(),
        html.Label("Excluded Stocks", className="small fw-semibold"),
        html.P("Smart Orders will never be created for these stocks.",
               className="text-muted small mb-2"),
        html.Div(exclusion_tags, id="groww-exclusion-tags", className="mb-2"),
        dbc.InputGroup([
            dbc.Input(id="groww-exclusion-input", placeholder="Add symbol e.g. HINDCOPPER",
                      maxLength=20),
            dbc.Button([html.I(className="fas fa-plus me-1"), "Add"],
                       id="groww-add-exclusion-btn", color="secondary", outline=True, n_clicks=0),
        ], className="mb-4"),
        html.Hr(),
        dbc.Card(dbc.CardBody([
            dbc.Switch(id="groww-gtt-enabled-switch",
                       label=[html.Strong("Enable Automatic Smart Order Creation",
                                          style={"color": "#f1f5f9"}), html.Br(),
                              html.Span("Runs at 8:30 AM IST, Mon–Fri.",
                                        style={"color": "#94a3b8", "fontSize": "0.82rem"})],
                       value=gtt_enabled, className="mb-0"),
        ]), className="mb-4", style={"background": "#0d1f17", "border": "1px solid #00D09C"}),
        html.Div(id="groww-prefs-status", className="mb-3"),
        html.Div(className="d-flex justify-content-between", children=[
            dbc.Button([html.I(className="fas fa-arrow-left me-1"), "Back"],
                       id="groww-wizard-step4-back", color="secondary", outline=True, n_clicks=0),
            dbc.Button([html.I(className="fas fa-check me-1"), "Save & Activate"],
                       id="save-groww-prefs-btn", color="success", n_clicks=0),
        ]),
    ]))


# ── Groww dashboard helpers ─────────────────────────────────────────────────

_GROWW_SIDEBAR_ITEMS = [
    ("connection", "fas fa-plug",      "Connection"),
    ("schedule",   "fas fa-clock",     "Schedule"),
    ("prefs",      "fas fa-sliders-h", "Preferences"),
    ("exclusions", "fas fa-ban",       "Exclusions"),
    ("activity",   "fas fa-history",   "Activity Log"),
]


def groww_sidebar(active_panel: str, settings: dict) -> html.Div:
    from modules.groww.portfolio import is_token_valid
    is_connected = is_token_valid(settings.get("access_token_set_at"))
    is_auto = settings.get("totp_auto_refresh", False)

    items = []
    for panel_id, icon, label in _GROWW_SIDEBAR_ITEMS:
        is_active = panel_id == active_panel
        badge = None
        if panel_id == "connection" and settings.get("access_token_enc") and not is_connected:
            dot_color = "#00D09C" if is_auto else "#f59e0b"
            badge = html.Span(style={
                "display": "inline-block", "width": "8px", "height": "8px",
                "borderRadius": "50%", "background": dot_color,
                "marginLeft": "6px", "verticalAlign": "middle",
            })
        items.append(
            html.Button(
                [html.I(className=f"{icon} me-2"), label, badge or ""],
                id={"type": "groww-nav-btn", "panel": panel_id},
                n_clicks=0,
                style={
                    "display": "block", "width": "100%", "textAlign": "left",
                    "padding": "10px 14px", "border": "none",
                    "background": "#083d2f" if is_active else "transparent",
                    "color": "#f1f5f9" if is_active else "#94a3b8",
                    "borderRadius": "6px", "cursor": "pointer",
                    "marginBottom": "4px", "fontSize": "0.88rem",
                    "fontWeight": "600" if is_active else "400",
                    "transition": "background 0.15s",
                    "borderLeft": "3px solid #00D09C" if is_active else "3px solid transparent",
                },
            )
        )
    return html.Div(items, style={"minWidth": "175px", "paddingRight": "12px"})


def groww_connection_section(settings: dict) -> html.Div:
    from modules.groww.portfolio import is_token_valid
    is_connected = is_token_valid(settings.get("access_token_set_at"))
    is_auto = settings.get("totp_auto_refresh", False) and settings.get("totp_secret_enc")

    if is_connected:
        status_badge = dbc.Badge(
            [html.I(className="fas fa-circle me-1"), "Connected"],
            color="success", className="fs-6 p-2",
        )
    elif settings.get("access_token_enc"):
        status_badge = dbc.Badge(
            [html.I(className="fas fa-exclamation-triangle me-1"), "Token Expired"],
            color="warning", className="fs-6 p-2",
        )
    else:
        status_badge = dbc.Badge(
            [html.I(className="fas fa-times-circle me-1"), "Not Connected"],
            color="secondary", className="fs-6 p-2",
        )

    last_set = settings.get("access_token_set_at", "")
    if last_set:
        try:
            from datetime import datetime, timezone, timedelta
            ts = datetime.fromisoformat(str(last_set))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ist = ts + timedelta(hours=5, minutes=30)
            last_set_str = ist.strftime("Last connected: %d %b %Y at %I:%M %p IST")
        except Exception:
            last_set_str = ""
    else:
        last_set_str = "Never connected"

    if is_auto:
        auto_badge = dbc.Badge(
            [html.I(className="fas fa-magic me-1"), "TOTP Auto-Refresh Active"],
            color="success", className="ms-2 p-2",
            style={"fontSize": "0.75rem"},
        )
        if is_connected:
            reconnect_section = html.Div([
                html.Div(className="d-flex align-items-center mb-2", children=[
                    auto_badge,
                ]),
                html.P(
                    "Your token refreshes automatically at 6:15 AM IST every day. "
                    "No manual action needed.",
                    className="text-muted small mb-3",
                ),
                dbc.Button(
                    [html.I(className="fas fa-bolt me-2"), "Refresh Token Now"],
                    id="groww-refresh-token-btn",
                    color="outline-success",
                    size="sm",
                    n_clicks=0,
                ),
                html.P("Force an early refresh if needed.",
                       className="text-muted small mt-2 mb-0"),
            ])
        else:
            reconnect_section = html.Div([
                html.Div(className="d-flex align-items-center mb-3", children=[
                    auto_badge,
                ]),
                dbc.Alert(
                    [html.I(className="fas fa-info-circle me-2"),
                     "Token expired (resets at 6 AM IST). Since you have TOTP enabled, "
                     "click the button below — no Groww login needed."],
                    color="info", style={"fontSize": "0.83rem"}, className="mb-3",
                ),
                dbc.Button(
                    [html.I(className="fas fa-bolt me-2"), "Auto-Refresh Token Now"],
                    id="groww-refresh-token-btn",
                    color="success",
                    size="lg",
                    className="w-100",
                    n_clicks=0,
                ),
            ])
    else:
        if is_connected:
            reconnect_section = html.Div([
                dbc.Alert(
                    [html.I(className="fas fa-clock me-2 text-warning"),
                     html.Strong("Manual mode. "),
                     "You need to paste a new token daily at ",
                     html.Strong("Groww developer portal"),
                     " (tokens reset at 6:00 AM IST). ",
                     html.Strong("Tip: "),
                     "switch to TOTP mode to eliminate this."],
                    color="warning", style={"fontSize": "0.83rem"}, className="mb-3",
                ),
                dbc.Button(
                    [html.I(className="fas fa-sync-alt me-2"), "Refresh Token"],
                    id="groww-refresh-token-btn",
                    color="outline-secondary",
                    size="sm",
                    n_clicks=0,
                ),
            ])
        else:
            reconnect_section = html.Div([
                dbc.Alert(
                    [html.I(className="fas fa-info-circle me-2"),
                     html.Strong("Manual mode — daily reconnection required. "),
                     "Paste your new access token from ",
                     html.A("groww.in/trade-api/api-keys",
                            href="https://groww.in/trade-api/api-keys",
                            target="_blank", style={"color": "#93c5fd"}),
                     "."],
                    color="warning", style={"fontSize": "0.83rem"}, className="mb-3",
                ),
                dbc.Label("New Access Token", className="small fw-semibold"),
                dbc.InputGroup([
                    dbc.Input(id="groww-manual-token-input",
                              type="password",
                              placeholder="Paste new access token"),
                    dbc.Button([html.I(className="fas fa-save me-1"), "Save"],
                               id="groww-save-manual-token-btn",
                               color="success",
                               n_clicks=0),
                ], className="mb-2"),
                # Hidden auto-refresh btn to avoid callback ID errors
                html.Div(
                    dbc.Button("", id="groww-refresh-token-btn", n_clicks=0, className="d-none"),
                    className="d-none",
                ),
            ])

    return html.Div([
        html.H6("Groww Connection", className="mb-3 fw-semibold"),
        html.Div(className="d-flex align-items-center mb-1", children=[
            html.Span("Status: ", className="text-muted me-2 small"),
            status_badge,
        ]),
        html.P(last_set_str, className="text-muted small mb-4"),
        reconnect_section,
        html.Div(id="groww-token-status", className="mt-3"),
    ])


def groww_schedule_section(settings: dict) -> html.Div:
    is_auto = settings.get("totp_auto_refresh", False)
    return html.Div([
        html.H6("Smart Order Job Schedule", className="mb-3 fw-semibold"),
        dbc.Card(dbc.CardBody([
            html.Div(className="d-flex align-items-center mb-3", children=[
                html.I(className="fas fa-clock fa-2x me-3", style={"color": "#00D09C"}),
                html.Div([
                    html.H5("8:30 AM IST — Fixed", className="mb-0 fw-bold",
                            style={"color": "#f1f5f9"}),
                    html.Small("Monday to Friday, every market day",
                               style={"color": "#94a3b8"}),
                ]),
            ]),
            html.Hr(style={"borderColor": "#334155"}),
            html.Div([
                html.Div(className="d-flex align-items-start mb-2", children=[
                    html.I(className="fas fa-magic me-2 mt-1",
                           style={"color": "#00D09C", "fontSize": "0.85rem"}),
                    html.Span(
                        [html.Strong("6:15 AM IST — Token auto-refreshed " if is_auto
                                     else "⚠ Manual reconnect required before 8:00 AM "),
                         ("via TOTP. No action needed." if is_auto
                          else "— paste new token from Groww portal.")],
                        style={"color": "#94a3b8", "fontSize": "0.85rem"},
                    ),
                ]),
                html.Div(className="d-flex align-items-start mb-2", children=[
                    html.I(className="fas fa-bell me-2 mt-1",
                           style={"color": "#f59e0b", "fontSize": "0.85rem"}),
                    html.Span(
                        [html.Strong("8:00 AM IST — Pre-flight check. "),
                         "Reminder email sent if token is expired."],
                        style={"color": "#94a3b8", "fontSize": "0.85rem"},
                    ),
                ]),
                html.Div(className="d-flex align-items-start mb-2", children=[
                    html.I(className="fas fa-robot me-2 mt-1",
                           style={"color": "#3b82f6", "fontSize": "0.85rem"}),
                    html.Span(
                        [html.Strong("8:30 AM IST — GTT job runs. "),
                         "STRONG BUY signals → Smart Orders placed."],
                        style={"color": "#94a3b8", "fontSize": "0.85rem"},
                    ),
                ]),
                html.Div(className="d-flex align-items-start", children=[
                    html.I(className="fas fa-store me-2 mt-1",
                           style={"color": "#10b981", "fontSize": "0.85rem"}),
                    html.Span([html.Strong("9:15 AM IST — Market opens. "),
                               "Smart Orders are already placed and waiting."],
                              style={"color": "#94a3b8", "fontSize": "0.85rem"}),
                ]),
            ]),
        ]), style={"background": "#0f172a", "border": "1px solid #083d2f"}),
    ])


def groww_prefs_section(settings: dict) -> html.Div:
    proximity_val = settings.get("proximity_threshold_pct", 2.0)
    allocation_val = settings.get("max_allocation_pct", 3.0)
    gtt_enabled = settings.get("gtt_enabled", False)
    return html.Div([
        html.H6("Smart Order Preferences", className="mb-4 fw-semibold"),
        dbc.Row([
            dbc.Col(md=6, children=[
                html.Label(id="groww-proximity-threshold-label",
                           children=f"Proximity Threshold: {proximity_val}%",
                           className="small fw-semibold"),
                html.P("How close to buy target before Smart Order is created",
                       className="text-muted small mb-2"),
                dcc.Slider(id="groww-proximity-threshold-slider", min=0.5, max=10.0, step=0.5,
                           value=proximity_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
            dbc.Col(md=6, children=[
                html.Label(id="groww-max-allocation-label",
                           children=f"Max Allocation per Stock: {allocation_val}%",
                           className="small fw-semibold"),
                html.P("Maximum % of portfolio per stock",
                       className="text-muted small mb-2"),
                dcc.Slider(id="groww-max-allocation-slider", min=0.5, max=10.0, step=0.5,
                           value=allocation_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
        ]),
        html.Hr(),
        dbc.Card(dbc.CardBody([
            dbc.Switch(id="groww-gtt-enabled-switch",
                       label=[html.Strong("Enable Automatic Smart Order Creation",
                                          style={"color": "#f1f5f9"}), html.Br(),
                              html.Span("Runs at 8:30 AM IST, Mon–Fri.",
                                        style={"color": "#94a3b8", "fontSize": "0.82rem"})],
                       value=gtt_enabled, className="mb-0"),
        ]), className="mb-4", style={"background": "#0d1f17", "border": "1px solid #00D09C"}),
        html.Div(id="groww-prefs-status", className="mb-3"),
        dbc.Button([html.I(className="fas fa-check me-1"), "Save Preferences"],
                   id="save-groww-prefs-btn", color="primary", n_clicks=0),
    ])


def groww_exclusions_section(exclusions: list) -> html.Div:
    tags = [
        dbc.Badge(
            [sym, html.Span(" ×", id={"type": "groww-del-exclusion", "symbol": sym},
                            style={"cursor": "pointer", "marginLeft": "4px"},
                            n_clicks=0)],
            color="secondary", className="me-1 mb-1 p-2",
            style={"fontSize": "0.8rem"},
        )
        for sym in exclusions
    ]
    return html.Div([
        html.H6("Excluded Stocks", className="mb-3 fw-semibold"),
        html.P("Smart Orders will never be created for symbols in this list.",
               className="text-muted small mb-4"),
        html.Div(tags, id="groww-exclusion-tags", className="mb-3"),
        dbc.InputGroup([
            dbc.Input(id="groww-exclusion-input", placeholder="Add symbol e.g. HINDCOPPER",
                      maxLength=20),
            dbc.Button([html.I(className="fas fa-plus me-1"), "Add"],
                       id="groww-add-exclusion-btn", color="secondary", outline=True, n_clicks=0),
        ], className="mb-2"),
        html.P("Symbols are saved immediately when added or removed.",
               className="text-muted small"),
    ])


def groww_activity_section(user_id: int) -> html.Div:
    return html.Div([
        html.H6("Activity Log", className="mb-3 fw-semibold"),
        html.Div(className="d-flex justify-content-between align-items-center mb-3", children=[
            html.P("Smart Order actions taken today. Refreshes every 30 seconds.",
                   className="text-muted small mb-0"),
            dbc.Button([html.I(className="fas fa-play me-2"), "Run GTT Job Now"],
                       id="run-gtt-job-btn", color="warning", size="sm", n_clicks=0),
        ]),
        html.Div(id="gtt-log-container"),
    ])
