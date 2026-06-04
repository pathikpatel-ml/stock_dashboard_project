"""
Zerodha GTT Settings — three-mode layout:
  • Intro / landing : brand new users (api_key_enc IS NULL, step == 0)
  • Wizard mode     : first-time setup steps 1–4 (api_key_enc IS NULL, step >= 1)
  • Dashboard mode  : returning users (api_key_enc IS NOT NULL) — sidebar + content panel
"""
import dash_bootstrap_components as dbc
from dash import dcc, html


# ── Shared helpers ──────────────────────────────────────────────────────────

def _connection_badge_from_settings(settings: dict):
    if not settings.get("access_token_enc"):
        return dbc.Badge(
            [html.I(className="fas fa-times-circle me-1"), "Not Connected"],
            color="secondary", className="fs-6 p-2",
        )
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


# ── Intro / landing card ────────────────────────────────────────────────────

def _intro_card() -> html.Div:
    """Landing page shown to first-time users before they enter the wizard."""
    return dbc.Card(className="section-container", children=dbc.CardBody([

        # Hero
        html.Div(className="text-center mb-4", children=[
            html.Div(style={"fontSize": "3rem", "marginBottom": "0.75rem"},
                     children=html.I(className="fas fa-robot text-primary")),
            html.H4("Automate Your GTT Buy Orders", className="fw-bold mb-2"),
            html.P(
                "Place Zerodha GTT orders automatically at 8:30 AM IST — before the market "
                "opens — based on your V20 STRONG BUY signals.",
                className="text-muted",
                style={"maxWidth": "500px", "margin": "0 auto", "fontSize": "0.95rem"},
            ),
        ]),

        html.Hr(style={"borderColor": "#334155", "margin": "1.5rem 0"}),

        # Two-column: what you get vs what you need
        dbc.Row(className="mb-4", children=[
            dbc.Col(md=6, className="mb-3 mb-md-0", children=[
                html.H6([html.I(className="fas fa-check-circle text-success me-2"),
                         "What you get"], className="mb-3 fw-semibold"),
                html.Ul([
                    html.Li("GTT orders placed automatically Mon–Fri at 8:30 AM IST"),
                    html.Li("Only STRONG BUY signals with MACD confirmation are acted on"),
                    html.Li("Email alert if you need to reconnect before the job runs"),
                    html.Li("Full control — enable, disable, or adjust thresholds anytime"),
                ], className="text-muted small",
                   style={"paddingLeft": "18px", "lineHeight": "1.9"}),
            ]),
            dbc.Col(md=6, children=[
                html.H6([html.I(className="fas fa-clipboard-list text-warning me-2"),
                         "What you need"], className="mb-3 fw-semibold"),
                html.Ul([
                    html.Li([
                        html.Strong("Active Zerodha trading account "),
                        html.Span("(user ID like ZY1234)", className="text-muted"),
                    ]),
                    html.Li([
                        "Free API key from ",
                        html.A("developers.kite.trade", href="https://developers.kite.trade",
                               target="_blank", style={"color": "#60a5fa"}),
                    ]),
                    html.Li("About 5 minutes for first-time setup"),
                ], className="text-muted small",
                   style={"paddingLeft": "18px", "lineHeight": "1.9"}),
            ]),
        ]),

        # Daily reconnect notice
        dbc.Alert([
            html.I(className="fas fa-clock me-2"),
            html.Strong("Daily reconnection required. "),
            "Zerodha resets all tokens at 6 AM IST every day. You'll receive an email "
            "reminder each morning so you can reconnect before the 8:30 AM job runs.",
        ], color="info", style={"fontSize": "0.85rem"}, className="mb-4"),

        # CTA
        html.Div(className="d-flex flex-column align-items-center gap-2", children=[
            dbc.Button(
                [html.I(className="fas fa-rocket me-2"),
                 "Get Started — Takes About 5 Minutes ",
                 html.I(className="fas fa-arrow-right")],
                id="wizard-intro-start-btn",
                color="primary",
                size="lg",
                n_clicks=0,
                className="px-5",
            ),
            html.P("Step-by-step guide — no technical knowledge required.",
                   className="text-muted small mb-0"),
        ]),

    ]))


# ── Wizard step helpers (unchanged) ────────────────────────────────────────

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
                dbc.Badge(badge_content, color=badge_color, className="wizard-badge",
                          style={"width": "2rem", "height": "2rem",
                                 "display": "inline-flex", "alignItems": "center",
                                 "justifyContent": "center", "borderRadius": "50%",
                                 "fontSize": "0.85rem"}),
                html.Div(label, className=f"wizard-step-label small {text_class}",
                         style={"marginTop": "4px"}),
            ], className="wizard-step text-center", style={"flex": "1"})
        )
        if i < len(steps) - 1:
            connector_color = "#22c55e" if current_step > n else "#334155"
            items.append(html.Div(style={"flex": "1", "height": "2px",
                                         "background": connector_color,
                                         "marginTop": "1rem", "alignSelf": "flex-start"}))
    return html.Div(items, style={"display": "flex", "alignItems": "flex-start",
                                  "padding": "1rem 0", "marginBottom": "1.5rem"})


def _step(n: int, text) -> html.Div:
    """Render a single numbered instruction step."""
    return html.Div(
        className="d-flex align-items-start mb-3",
        children=[
            html.Div(
                str(n),
                style={
                    "minWidth": "26px", "height": "26px",
                    "borderRadius": "50%", "background": "#1e3a5f",
                    "border": "1px solid #3b82f6", "color": "#60a5fa",
                    "display": "flex", "alignItems": "center",
                    "justifyContent": "center", "fontSize": "0.78rem",
                    "fontWeight": "700", "marginRight": "12px",
                    "marginTop": "2px", "flexShrink": "0",
                },
            ),
            html.Div(text, style={"color": "#cbd5e1", "fontSize": "0.875rem",
                                   "lineHeight": "1.6"}),
        ],
    )


def _step1_card() -> html.Div:
    redirect_url = "https://stock-dashboard-project.onrender.com/kite/callback"

    return dbc.Card(className="section-container", children=dbc.CardBody([

        # Header
        html.H5([html.I(className="fas fa-id-card me-2 text-primary"),
                 "Get Your Zerodha Kite API Key"],
                className="mb-1 fw-semibold"),
        html.P(
            "This is a one-time setup. You need an active Zerodha trading account to begin.",
            className="text-muted small mb-4",
        ),

        # Prerequisite banner
        dbc.Alert(
            [html.I(className="fas fa-info-circle me-2"),
             html.Strong("Prerequisite: "),
             "You must already have a Zerodha demat/trading account (user ID like ZY1234). "
             "If you don't have one, open an account at ",
             html.A("zerodha.com", href="https://zerodha.com", target="_blank",
                    className="alert-link"), " first."],
            color="info", className="mb-4", style={"fontSize": "0.85rem"},
        ),

        html.Hr(style={"borderColor": "#334155"}),
        html.P("Follow these steps to get your API Key:", className="small fw-semibold mb-3"),

        _step(1, [
            "Open the Kite Connect developer portal: ",
            html.A("developers.kite.trade", href="https://developers.kite.trade",
                   target="_blank", style={"color": "#60a5fa"}),
        ]),
        _step(2, [
            "Click ", html.Strong("Login"), " in the top-right corner. ",
            "Sign in with your ", html.Strong("Zerodha User ID and password"),
            " (same credentials you use to log in to Kite/Zerodha). ",
            "Do NOT create a new account — use your existing Zerodha login.",
        ]),
        _step(3, [
            "After logging in, click ",
            html.Strong("Create new app"),
            " (or go to ",
            html.A("developers.kite.trade/apps/new",
                   href="https://developers.kite.trade/apps/new",
                   target="_blank", style={"color": "#60a5fa"}),
            ").",
        ]),
        _step(4, [
            "Fill in the form:",
            html.Ul([
                html.Li([html.Strong("App name: "), "Any name, e.g. ", html.Em("My GTT Bot")]),
                html.Li([html.Strong("App type: "), "Select ", html.Strong("Personal"),
                         " (free, no approval needed)"]),
                html.Li([html.Strong("Redirect URL: "), "Copy exactly:",
                         html.Br(),
                         html.Div(
                             redirect_url,
                             style={"background": "#0f172a", "border": "1px solid #334155",
                                    "borderRadius": "6px", "padding": "6px 10px",
                                    "fontFamily": "monospace", "fontSize": "0.8rem",
                                    "color": "#93c5fd", "marginTop": "4px",
                                    "wordBreak": "break-all"},
                         )]),
                html.Li([html.Strong("Description: "), "Optional — write anything"]),
            ], style={"marginTop": "6px", "paddingLeft": "18px",
                      "color": "#94a3b8", "fontSize": "0.85rem"}),
        ]),
        _step(5, [
            "Click ", html.Strong("Create"), ". Your app is now created. ",
            "You will see your ", html.Strong("API Key"),
            " on the app's detail page — click ",
            html.Strong("Show API Secret"), " to reveal your ",
            html.Strong("API Secret"), " too.",
        ]),

        dbc.Alert(
            [html.I(className="fas fa-exclamation-triangle me-2 text-warning"),
             html.Strong("Important: "), "Copy and save your ",
             html.Strong("API Secret"), " now. It is shown only once. "
             "If you lose it, you will need to regenerate it in the portal."],
            color="warning", className="mt-3 mb-4", style={"fontSize": "0.85rem"},
        ),

        html.Hr(style={"borderColor": "#334155"}),

        html.Div(className="d-flex justify-content-between align-items-center mt-3", children=[
            html.A(
                [html.I(className="fas fa-external-link-alt me-1"),
                 "Open Developer Portal"],
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
        ]),
    ]))


def _step2_card(api_key_saved: bool = False) -> html.Div:
    key_placeholder = "•••••••••••• already saved (enter new key to update)" if api_key_saved else "e.g. abcdef1234567890"
    return dbc.Card(className="section-container", children=dbc.CardBody([

        html.H5([html.I(className="fas fa-key me-2 text-primary"),
                 "Enter Your API Key & Secret"],
                className="mb-1 fw-semibold"),
        html.P(
            "Paste the credentials from your Kite Connect app's detail page.",
            className="text-muted small mb-4",
        ),

        # Where to find them
        dbc.Card(
            dbc.CardBody([
                html.P([html.I(className="fas fa-map-marker-alt me-2 text-primary"),
                        html.Strong("Where to find these:")],
                       className="mb-2 small"),
                html.Ol([
                    html.Li(["Go to ",
                             html.A("developers.kite.trade/apps",
                                    href="https://developers.kite.trade/apps",
                                    target="_blank", style={"color": "#60a5fa"})]),
                    html.Li(["Click on the app you created (e.g. ", html.Em("My GTT Bot"), ")"]),
                    html.Li(["Your ", html.Strong("API Key"), " is shown at the top of the page"]),
                    html.Li(["Click ", html.Strong("Show API Secret"),
                             " to reveal your ", html.Strong("API Secret")]),
                ], style={"color": "#94a3b8", "fontSize": "0.83rem",
                          "paddingLeft": "18px", "marginBottom": "0"}),
            ]),
            className="mb-4",
            style={"background": "#0f172a", "border": "1px solid #1e3a5f"},
        ),

        dbc.Label([html.I(className="fas fa-key me-1 text-primary"), " API Key"],
                  className="small fw-semibold"),
        dbc.Input(
            id="kite-api-key-input",
            type="text",
            placeholder=key_placeholder,
            className="mb-1",
        ),
        html.P("Looks like: a8kc3fg7h2mj5p1q (16 alphanumeric characters)",
               className="text-muted mb-3", style={"fontSize": "0.78rem"}),

        dbc.Label([html.I(className="fas fa-lock me-1 text-warning"), " API Secret"],
                  className="small fw-semibold"),
        dbc.Input(
            id="kite-api-secret-input",
            type="password",
            placeholder="Paste your API Secret",
            className="mb-1",
        ),
        html.P("Looks like: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx (32 characters)",
               className="text-muted mb-3", style={"fontSize": "0.78rem"}),

        dbc.Alert(
            [html.I(className="fas fa-shield-alt me-2"),
             "Your credentials are ", html.Strong("encrypted"),
             " before being stored. They never leave the server in plain text."],
            color="info", className="mb-4", style={"fontSize": "0.83rem"},
        ),

        html.Div(id="kite-creds-status", className="mb-3"),

        html.Div(className="d-flex justify-content-between", children=[
            dbc.Button([html.I(className="fas fa-arrow-left me-1"), "Back"],
                       id="wizard-step2-back", color="secondary", outline=True, n_clicks=0),
            dbc.Button([html.I(className="fas fa-save me-1"), "Save & Continue"],
                       id="save-kite-creds-btn", color="primary", n_clicks=0),
        ]),
    ]))


def _step3_card(connection_badge) -> html.Div:
    return dbc.Card(className="section-container", children=dbc.CardBody([

        html.H5([html.I(className="fas fa-plug me-2 text-primary"),
                 "Connect Your Zerodha Trading Account"],
                className="mb-1 fw-semibold"),
        html.P("Authorise this dashboard to place GTT orders on your behalf.",
               className="text-muted small mb-4"),

        html.Div(className="d-flex align-items-center mb-4", children=[
            html.Span("Status: ", className="text-muted me-2 small"),
            connection_badge,
        ]),

        # How it works
        dbc.Card(
            dbc.CardBody([
                html.P([html.I(className="fas fa-question-circle me-2 text-primary"),
                        html.Strong("How this works:")],
                       className="mb-2 small"),
                html.Ul([
                    html.Li("Click the button below — you'll be taken to Zerodha's login page"),
                    html.Li(["Enter your ", html.Strong("Zerodha User ID"),
                             " (e.g. ZY1234) and your ", html.Strong("Zerodha password")]),
                    html.Li("Complete the 2FA (TOTP or SMS OTP)"),
                    html.Li("You'll be redirected back here automatically"),
                    html.Li("Your access token is saved — GTT automation is ready"),
                ], style={"color": "#94a3b8", "fontSize": "0.83rem",
                          "paddingLeft": "18px", "marginBottom": "0"}),
            ]),
            className="mb-4",
            style={"background": "#0f172a", "border": "1px solid #1e3a5f"},
        ),

        dbc.Alert(
            [html.I(className="fas fa-clock me-2 text-warning"),
             html.Strong("Daily reconnection required. "),
             "Zerodha resets all access tokens at ", html.Strong("6:00 AM IST"),
             " every day. You'll receive an email each morning if reconnection is needed "
             "before your scheduled GTT run."],
            color="warning", className="mb-4", style={"fontSize": "0.85rem"},
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

        html.Div(className="d-flex justify-content-between", children=[
            dbc.Button([html.I(className="fas fa-arrow-left me-1"), "Back"],
                       id="wizard-step3-back", color="secondary", outline=True, n_clicks=0),
            dbc.Button(["Continue ", html.I(className="fas fa-arrow-right ms-1")],
                       id="wizard-step3-next", color="primary", n_clicks=0),
        ]),

    ]))


def _step4_card(settings: dict, exclusions: list) -> html.Div:
    proximity_val = settings.get("proximity_threshold_pct", 2.0)
    allocation_val = settings.get("max_allocation_pct", 3.0)
    gtt_enabled = settings.get("gtt_enabled", False)
    exclusion_tags = [
        dbc.Badge([sym, html.Span(" ×", id={"type": "del-exclusion", "symbol": sym},
                                  style={"cursor": "pointer", "marginLeft": "4px"})],
                  color="secondary", className="me-1 mb-1 p-2",
                  style={"fontSize": "0.8rem"})
        for sym in exclusions
    ]
    return dbc.Card(className="section-container", children=dbc.CardBody([
        html.H5([html.I(className="fas fa-sliders-h me-2 text-primary"),
                 "GTT Preferences"], className="mb-4"),
        dbc.Row([
            dbc.Col(md=6, children=[
                html.Label(id="proximity-threshold-label",
                           children=f"Proximity Threshold: {proximity_val}%",
                           className="small fw-semibold"),
                html.P("How close to the buy target before creating a GTT",
                       className="text-muted small mb-2"),
                dcc.Slider(id="proximity-threshold-slider", min=0.5, max=10.0, step=0.5,
                           value=proximity_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
            dbc.Col(md=6, children=[
                html.Label(id="max-allocation-label",
                           children=f"Max Allocation per Stock: {allocation_val}%",
                           className="small fw-semibold"),
                html.P("Maximum % of portfolio per stock",
                       className="text-muted small mb-2"),
                dcc.Slider(id="max-allocation-slider", min=0.5, max=10.0, step=0.5,
                           value=allocation_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
        ]),
        html.Hr(),
        html.Label("Excluded Stocks", className="small fw-semibold"),
        html.P("GTT orders will never be created for these stocks.",
               className="text-muted small mb-2"),
        html.Div(exclusion_tags, id="exclusion-tags", className="mb-2"),
        dbc.InputGroup([
            dbc.Input(id="exclusion-input", placeholder="Add symbol e.g. HINDCOPPER",
                      maxLength=20),
            dbc.Button([html.I(className="fas fa-plus me-1"), "Add"],
                       id="add-exclusion-btn", color="secondary", outline=True, n_clicks=0),
        ], className="mb-4"),
        html.Hr(),
        dbc.Card(dbc.CardBody([
            dbc.Switch(id="gtt-enabled-switch",
                       label=[html.Strong("Enable Automatic GTT Creation"), html.Br(),
                              html.Span("Runs at your scheduled time, Mon–Fri.",
                                        className="text-muted small")],
                       value=gtt_enabled, className="mb-0"),
        ]), className="mb-4", style={"background": "#1e293b", "border": "1px solid #334155", "color": "#f1f5f9"}),
        html.Div(id="kite-prefs-status", className="mb-3"),
        html.Div(className="d-flex justify-content-between", children=[
            dbc.Button([html.I(className="fas fa-arrow-left me-1"), "Back"],
                       id="wizard-step4-back", color="secondary", outline=True, n_clicks=0),
            dbc.Button([html.I(className="fas fa-check me-1"), "Save & Activate"],
                       id="save-kite-prefs-btn", color="success", n_clicks=0),
        ]),
    ]))


# ── Dashboard mode: sidebar helpers ────────────────────────────────────────

_SIDEBAR_ITEMS = [
    ("connection", "fas fa-plug",      "Connection"),
    ("schedule",   "fas fa-clock",     "Schedule"),
    ("prefs",      "fas fa-sliders-h", "Preferences"),
    ("exclusions", "fas fa-ban",       "Exclusions"),
    ("activity",   "fas fa-history",   "Activity Log"),
]


def _sidebar(active_panel: str, settings: dict) -> html.Div:
    """Render sidebar nav with active highlight and connection status badge."""
    _, connected = _token_status(settings)
    items = []
    for panel_id, icon, label in _SIDEBAR_ITEMS:
        is_active = panel_id == active_panel
        # Add a small orange dot next to Connection when token is expired
        badge = None
        if panel_id == "connection" and settings.get("access_token_enc") and not connected:
            badge = html.Span(style={
                "display": "inline-block", "width": "8px", "height": "8px",
                "borderRadius": "50%", "background": "#f59e0b",
                "marginLeft": "6px", "verticalAlign": "middle",
            })
        items.append(
            html.Button(
                [html.I(className=f"{icon} me-2"),
                 label,
                 badge or ""],
                id={"type": "kite-nav-btn", "panel": panel_id},
                n_clicks=0,
                className="kite-nav-btn" + (" active" if is_active else ""),
                style={
                    "display": "block", "width": "100%", "textAlign": "left",
                    "padding": "10px 14px", "border": "none",
                    "background": "#1e3a5f" if is_active else "transparent",
                    "color": "#f1f5f9" if is_active else "#94a3b8",
                    "borderRadius": "6px", "cursor": "pointer",
                    "marginBottom": "4px", "fontSize": "0.88rem",
                    "fontWeight": "600" if is_active else "400",
                    "transition": "background 0.15s",
                },
            )
        )
    return html.Div(items, style={"minWidth": "175px", "paddingRight": "12px"})


def _token_status(settings: dict) -> tuple:
    """(badge, is_connected_bool)"""
    if not settings.get("access_token_enc"):
        return None, False
    try:
        from modules.kite import portfolio as kite_portfolio
        valid = kite_portfolio.is_token_valid(settings.get("access_token_set_at"))
    except Exception:
        valid = False
    return settings.get("access_token_enc"), valid


def _expired_banner() -> html.Div:
    return dbc.Alert(
        className="mb-3 d-flex align-items-center justify-content-between flex-wrap gap-2",
        color="warning",
        style={"fontSize": "0.88rem"},
        children=[
            html.Div([
                html.I(className="fas fa-exclamation-triangle me-2"),
                html.Strong("Daily token expired. "),
                "Zerodha resets all tokens at 6 AM IST. Click Reconnect to re-authorize.",
            ]),
            dbc.Button(
                [html.I(className="fas fa-plug me-1"), "Reconnect Now"],
                id="banner-goto-connection",
                color="warning",
                size="sm",
                n_clicks=0,
            ),
        ],
    )


# ── Dashboard section content builders ─────────────────────────────────────

def _connection_section(settings: dict) -> html.Div:
    badge = _connection_badge_from_settings(settings)
    _, connected = _token_status(settings)
    last_set = settings.get("access_token_set_at", "")
    if last_set:
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(str(last_set))
            if ts.tzinfo is None:
                from datetime import timezone
                ts = ts.replace(tzinfo=timezone.utc)
            from datetime import timedelta
            ist = ts + timedelta(hours=5, minutes=30)
            last_set_str = ist.strftime("Last connected: %d %b %Y at %I:%M %p IST")
        except Exception:
            last_set_str = ""
    else:
        last_set_str = "Never connected"

    if connected:
        # ── Connected state ──
        reconnect_section = html.Div([
            dbc.Button(
                [html.I(className="fas fa-sync-alt me-2"), "Refresh Token"],
                id="connect-kite-btn",
                color="outline-secondary",
                size="sm",
                n_clicks=0,
            ),
            html.P("Your token is valid for today. You can refresh it early if needed.",
                   className="text-muted small mt-2 mb-0"),
        ])
    else:
        # ── Expired / not connected state — make reconnect impossible to miss ──
        reconnect_section = html.Div([
            dbc.Alert(
                [html.I(className="fas fa-info-circle me-2"),
                 html.Strong("Why does this happen? "),
                 "Zerodha resets all API tokens at 6 AM IST every day as a security measure. "
                 "This is not a bug — you must reconnect each morning before your GTT job runs."],
                color="info", style={"fontSize": "0.83rem"}, className="mb-3",
            ),
            html.P("Steps:", className="small fw-semibold mb-2"),
            html.Ol([
                html.Li("Click the button below"),
                html.Li("Log in with your Zerodha User ID and password"),
                html.Li("Complete 2FA (TOTP or SMS)"),
                html.Li("You'll be redirected back automatically — done!"),
            ], className="text-muted small mb-4",
               style={"paddingLeft": "18px", "lineHeight": "1.8"}),
            dbc.Button(
                [html.I(className="fas fa-plug me-2"), "Reconnect Zerodha Account"],
                id="connect-kite-btn",
                color="success",
                size="lg",
                className="w-100",
                n_clicks=0,
            ),
        ])

    return html.Div([
        html.H6("Zerodha Connection", className="mb-3 fw-semibold"),
        html.Div(className="d-flex align-items-center mb-1", children=[
            html.Span("Status: ", className="text-muted me-2 small"),
            badge,
        ]),
        html.P(last_set_str, className="text-muted small mb-4"),
        reconnect_section,
        html.Div(id="kite-token-status", className="mt-3"),
    ])


def _schedule_section(settings: dict) -> html.Div:
    schedule_time = settings.get("schedule_time", "08:30")
    options = [
        {"value": "08:30",
         "label": "8:30 AM IST  —  45 min before open (Recommended)"},
        {"value": "08:45", "label": "8:45 AM IST  —  30 min before open"},
        {"value": "09:00", "label": "9:00 AM IST  —  15 min before open"},
        {"value": "09:10", "label": "9:10 AM IST  —  5 min before open (Latest)"},
    ]
    return html.Div([
        html.H6("GTT Job Schedule", className="mb-3 fw-semibold"),
        html.P("When should the GTT job run each weekday morning? "
               "Pick a time that gives you enough chance to reconnect if the token "
               "expires overnight.",
               className="text-muted small mb-4"),
        dbc.RadioItems(id="schedule-time-radio", options=options,
                       value=schedule_time, className="mb-4"),
        dbc.Button([html.I(className="fas fa-save me-1"), "Save Schedule"],
                   id="save-schedule-btn", color="primary", n_clicks=0),
        html.Div(id="schedule-save-status", className="mt-3"),
    ])


def _prefs_section(settings: dict) -> html.Div:
    proximity_val = settings.get("proximity_threshold_pct", 2.0)
    allocation_val = settings.get("max_allocation_pct", 3.0)
    gtt_enabled = settings.get("gtt_enabled", False)
    return html.Div([
        html.H6("GTT Preferences", className="mb-4 fw-semibold"),
        dbc.Row([
            dbc.Col(md=6, children=[
                html.Label(id="proximity-threshold-label",
                           children=f"Proximity Threshold: {proximity_val}%",
                           className="small fw-semibold"),
                html.P("How close to buy target before GTT is created",
                       className="text-muted small mb-2"),
                dcc.Slider(id="proximity-threshold-slider", min=0.5, max=10.0, step=0.5,
                           value=proximity_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
            dbc.Col(md=6, children=[
                html.Label(id="max-allocation-label",
                           children=f"Max Allocation per Stock: {allocation_val}%",
                           className="small fw-semibold"),
                html.P("Maximum % of portfolio per stock",
                       className="text-muted small mb-2"),
                dcc.Slider(id="max-allocation-slider", min=0.5, max=10.0, step=0.5,
                           value=allocation_val, marks={i: f"{i}%" for i in range(1, 11)},
                           className="mb-4"),
            ]),
        ]),
        html.Hr(),
        dbc.Card(dbc.CardBody([
            dbc.Switch(id="gtt-enabled-switch",
                       label=[html.Strong("Enable Automatic GTT Creation"), html.Br(),
                              html.Span("Runs at your scheduled time, Mon–Fri. "
                                        "Only BUY/STRONG BUY signals with MACD confirmation.",
                                        className="text-muted small")],
                       value=gtt_enabled, className="mb-0"),
        ]), className="mb-4", style={"background": "#1e293b", "border": "1px solid #334155", "color": "#f1f5f9"}),
        html.Div(id="kite-prefs-status", className="mb-3"),
        dbc.Button([html.I(className="fas fa-check me-1"), "Save Preferences"],
                   id="save-kite-prefs-btn", color="primary", n_clicks=0),
    ])


def _exclusions_section(exclusions: list) -> html.Div:
    tags = [
        dbc.Badge([sym, html.Span(" ×", id={"type": "del-exclusion", "symbol": sym},
                                  style={"cursor": "pointer", "marginLeft": "4px"})],
                  color="secondary", className="me-1 mb-1 p-2",
                  style={"fontSize": "0.8rem"})
        for sym in exclusions
    ]
    return html.Div([
        html.H6("Excluded Stocks", className="mb-3 fw-semibold"),
        html.P("GTT orders will never be created for symbols in this list — "
               "useful for stocks you're already holding or want to avoid.",
               className="text-muted small mb-4"),
        html.Div(tags, id="exclusion-tags", className="mb-3"),
        dbc.InputGroup([
            dbc.Input(id="exclusion-input", placeholder="Add symbol e.g. HINDCOPPER",
                      maxLength=20),
            dbc.Button([html.I(className="fas fa-plus me-1"), "Add"],
                       id="add-exclusion-btn", color="secondary", outline=True, n_clicks=0),
        ], className="mb-2"),
        html.P("Symbols are saved immediately when added or removed.",
               className="text-muted small"),
    ])


def _activity_section(user_id: int) -> html.Div:
    return html.Div([
        html.H6("Activity Log", className="mb-3 fw-semibold"),
        html.Div(className="d-flex justify-content-between align-items-center mb-3", children=[
            html.P("GTT actions taken today. Refreshes every 30 seconds.",
                   className="text-muted small mb-0"),
            dbc.Button([html.I(className="fas fa-play me-2"), "Run GTT Job Now"],
                       id="run-gtt-job-btn", color="warning", size="sm", n_clicks=0),
        ]),
        html.Div(id="gtt-log-container"),
    ])


# ── Main layout shell ───────────────────────────────────────────────────────

def create_kite_settings_layout():
    """
    Minimal shell — all content is rendered into kite-settings-root by a
    single master callback (render_kite_root). This prevents duplicate IDs
    from wizard + dashboard elements being in the DOM simultaneously.

    dcc.Location is kept at top level (outside the rendered content) so
    the Kite OAuth redirect works regardless of which mode is active.
    """
    return dbc.Container(fluid=True, className="p-4", style={"maxWidth": "900px"}, children=[
        html.H4([html.I(className="fas fa-chart-line me-2"), "Zerodha GTT Automation"],
                className="mb-1"),
        html.P("Set up automatic GTT buy orders before market open.",
               className="text-muted mb-4"),

        # All mode-specific content rendered here (wizard OR dashboard, never both)
        html.Div(id="kite-settings-root"),

        # dcc.Location must be always in DOM for OAuth redirect to work
        dcc.Location(id="kite-login-redirect", refresh=True),

        # Shared stores and interval
        dcc.Store(id="kite-wizard-step", data=None),
        dcc.Store(id="kite-settings-loaded"),
        dcc.Store(id="kite-panel", data="connection"),
        dcc.Store(id="kite-oauth-result"),    # populated by app.py after OAuth redirect
        dcc.Store(id="kite-oauth-url"),       # clientside callback opens this in a new tab
        dcc.Interval(id="kite-status-interval", interval=30_000, n_intervals=0),
    ])
