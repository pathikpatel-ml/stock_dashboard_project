import logging
import re

import dash
import dash_bootstrap_components as dbc
import flask
import flask_login
from dash import ALL, Input, Output, State, html

from modules.auth import user_store
from modules.auth.crypto import decrypt, encrypt
from modules.kite import auth as kite_auth
from modules.kite import portfolio as kite_portfolio
from modules.kite.scheduler import run_premarket_gtt_job
from modules.kite.settings_layout import (
    _connection_badge_from_settings,
    _expired_banner,
    _intro_card,
    _progress_bar,
    _sidebar,
    _step1_card,
    _step2_card,
    _step3_card,
    _step4_card,
    _token_status,
    _connection_section,
    _schedule_section,
    _prefs_section,
    _exclusions_section,
    _activity_section,
)

logger = logging.getLogger(__name__)


def _current_user_id():
    if flask_login.current_user.is_authenticated:
        return flask_login.current_user.id
    return None


def _connection_status(settings: dict) -> tuple:
    """Returns (badge_component, is_connected_today)."""
    if settings.get("access_token_enc"):
        token_age = settings.get("access_token_set_at")
        valid = kite_portfolio.is_token_valid(token_age)
        if valid:
            badge = dbc.Badge(
                [html.I(className="fas fa-circle me-1"), "Connected"],
                color="success", className="fs-6 p-2",
            )
            return badge, True
        else:
            badge = dbc.Badge(
                [html.I(className="fas fa-exclamation-triangle me-1"),
                 "Token Expired — Reconnect"],
                color="warning", className="fs-6 p-2",
            )
            return badge, False
    badge = dbc.Badge(
        [html.I(className="fas fa-times-circle me-1"), "Not Connected"],
        color="secondary", className="fs-6 p-2",
    )
    return badge, False


def _determine_wizard_step(settings: dict) -> int:
    """Return the step the user should land on based on their current state.

    Step 0 = intro landing page (brand new user, no API key saved yet).
    Steps 1–4 = wizard steps.
    """
    if not settings.get("api_key_enc"):
        return 0   # Show intro landing page for new users
    _, connected = _connection_status(settings)
    if not connected:
        return 3
    if not settings.get("gtt_enabled"):
        return 4
    return 4


def register_kite_settings_callbacks(app):

    # ── Intro landing page CTA ────────────────────────────────────────────────
    @app.callback(
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("wizard-intro-start-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def start_wizard_from_intro(n_clicks):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        return 1   # Advance from intro (step 0) to first wizard step

    # ── Master render: single callback, one set of elements in DOM ───────────
    # Replaces the old render_kite_mode + render_dashboard + render_wizard_step.
    # Only wizard OR dashboard elements are in the DOM at any time — no duplicate IDs.
    @app.callback(
        Output("kite-settings-root", "children"),
        Input("strategy-tabs", "value"),
        Input("kite-status-interval", "n_intervals"),
        Input("kite-wizard-step", "data"),
        Input("kite-panel", "data"),
        Input("kite-oauth-result", "data"),
    )
    def render_kite_root(active_tab, _, wizard_step, panel, oauth_result):
        if active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        settings = user_store.get_kite_settings(user_id)
        badge, connected = _connection_status(settings)
        api_key_saved = bool(settings.get("api_key_enc"))

        # ── OAuth result toast (shown once after redirect) ─────────────────
        oauth_toast = None
        if oauth_result == "connected":
            oauth_toast = dbc.Alert(
                [html.I(className="fas fa-check-circle me-2"),
                 html.Strong("Zerodha connected successfully! "),
                 "GTT orders will be placed automatically at your scheduled time."],
                color="success", dismissable=True, duration=10000, className="mb-3",
            )
        elif oauth_result and oauth_result.startswith("error:"):
            err_code = oauth_result.split(":", 1)[1]
            msg = {
                "cancelled": "OAuth was cancelled. Click 'Reconnect' to try again.",
                "missing_creds": "API credentials not found. Please re-enter your API Key and Secret.",
                "exchange_failed": "Token exchange failed — your API Key or Secret may be wrong. "
                                   "Check them in Step 2 and try again.",
            }.get(err_code, f"Connection failed ({err_code}). Please try again.")
            oauth_toast = dbc.Alert(
                [html.I(className="fas fa-exclamation-circle me-2"), msg],
                color="danger", dismissable=True, className="mb-3",
            )

        # ── Wizard mode: first-time setup ─────────────────────────────────
        if not api_key_saved:
            step = wizard_step if wizard_step is not None else _determine_wizard_step(settings)

            # Step 0: intro / landing page — shown to brand new users
            if step == 0:
                prefix = [oauth_toast] if oauth_toast else []
                return prefix + [_intro_card()]

            # Steps 1–4: guided wizard with progress bar
            exclusions = user_store.get_exclusions(user_id) if step == 4 else []
            if step == 1:   step_content = _step1_card()
            elif step == 2: step_content = _step2_card(False)
            elif step == 3: step_content = _step3_card(badge)
            else:           step_content = _step4_card(settings, exclusions)

            parts = ([oauth_toast] if oauth_toast else []) + [_progress_bar(step), step_content]
            if connected:
                parts.append(dbc.Card(dbc.CardBody([
                    html.H6([html.I(className="fas fa-vial me-2"), "Test GTT Job"],
                            className="mb-3"),
                    dbc.Button([html.I(className="fas fa-play me-2"), "Run GTT Job Now"],
                               id="run-gtt-job-btn", color="warning", size="sm",
                               className="mb-3", n_clicks=0),
                    html.Div(id="gtt-log-container"),
                ]), className="mt-4 section-container"))
            return parts

        # ── Dashboard mode: returning users ───────────────────────────────
        exclusions = user_store.get_exclusions(user_id)
        _, is_connected = _token_status(settings)

        active_panel = panel or "connection"
        if active_panel == "connection":   sec = _connection_section(settings)
        elif active_panel == "schedule":   sec = _schedule_section(settings)
        elif active_panel == "prefs":      sec = _prefs_section(settings)
        elif active_panel == "exclusions": sec = _exclusions_section(exclusions)
        elif active_panel == "activity":   sec = _activity_section(user_id)
        else:                              sec = _connection_section(settings)

        parts = [oauth_toast] if oauth_toast else []
        if settings.get("access_token_enc") and not is_connected:
            parts.append(_expired_banner())
        parts.append(html.Div(
            style={"display": "flex", "gap": "0", "alignItems": "flex-start"},
            children=[
                html.Div(_sidebar(active_panel, settings),
                         style={"minWidth": "185px", "paddingRight": "16px",
                                "borderRight": "1px solid #1e3a5f"}),
                html.Div(sec, style={"flex": "1", "paddingLeft": "24px", "minWidth": "0"}),
            ],
        ))
        return parts

    # ── Sidebar navigation (updates kite-panel → triggers render_kite_root) ─
    @app.callback(
        Output("kite-panel", "data"),
        Input({"type": "kite-nav-btn", "panel": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def sidebar_nav(n_clicks_list):
        ctx = dash.callback_context
        if not ctx.triggered or not any(n for n in n_clicks_list if n):
            raise dash.exceptions.PreventUpdate
        import json
        id_dict = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
        return id_dict["panel"]

    # ── Banner "Reconnect Now" — triggers OAuth directly ─────────────────
    @app.callback(
        Output("kite-login-redirect", "href", allow_duplicate=True),
        Output("kite-panel", "data", allow_duplicate=True),
        Input("banner-goto-connection", "n_clicks"),
        prevent_initial_call=True,
    )
    def banner_reconnect_now(n):
        if not n:
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        settings = user_store.get_kite_settings(user_id)
        if not settings.get("api_key_enc"):
            # No credentials saved — just navigate to Connection panel
            return dash.no_update, "connection"
        try:
            api_key = decrypt(settings["api_key_enc"])
            login_url = kite_auth.generate_login_url(api_key)
            return login_url, "connection"
        except Exception:
            logger.exception("Banner reconnect: could not generate login URL for user %s", user_id)
            return dash.no_update, "connection"

    # ── initialise_wizard: sets step store + signals settings are loaded ──
    # (kite-settings-loaded triggers auto_exchange_token after OAuth redirect)
    @app.callback(
        Output("kite-wizard-step", "data"),
        Output("kite-settings-loaded", "data"),
        Input("strategy-tabs", "value"),
    )
    def initialise_wizard(active_tab):
        if active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        settings = user_store.get_kite_settings(user_id)
        step = _determine_wizard_step(settings)
        return step, True

    # ── Save schedule preference ──────────────────────────────────────────
    @app.callback(
        Output("schedule-save-status", "children"),
        Input("save-schedule-btn", "n_clicks"),
        State("schedule-time-radio", "value"),
        prevent_initial_call=True,
    )
    def save_schedule(n_clicks, schedule_time):
        user_id = _current_user_id()
        if not user_id:
            return "Not logged in."
        try:
            user_store.upsert_kite_settings(user_id, schedule_time=schedule_time)
        except Exception as exc:
            err = str(exc).lower()
            logger.exception("Failed to save schedule for user %s", user_id)
            if "schedule_time" in err or "42703" in err or "column" in err:
                return dbc.Alert([
                    html.Strong("Database migration required. "),
                    "Please run this SQL in the ",
                    html.A("Supabase SQL editor",
                           href="https://supabase.com/dashboard/project/_/sql/new",
                           target="_blank", className="alert-link"),
                    ":", html.Br(),
                    html.Code(
                        "ALTER TABLE kite_settings ADD COLUMN IF NOT EXISTS schedule_time TEXT NOT NULL DEFAULT '08:30';",
                        style={"fontSize": "0.8rem", "wordBreak": "break-all"},
                    ),
                ], color="warning", dismissable=True)
            return dbc.Alert("Failed to save schedule — check server logs.", color="danger", dismissable=True)

        # Reschedule APScheduler job for this user
        try:
            from app import _scheduler
            from modules.kite.scheduler import reschedule_user
            reschedule_user(_scheduler, user_id, schedule_time)
        except Exception as e:
            logger.warning("Could not reschedule APScheduler job: %s", e)

        return dbc.Alert(
            [html.I(className="fas fa-check me-2"),
             f"Schedule saved — GTT job will run at {schedule_time} IST on weekdays."],
            color="success", dismissable=True, duration=4000,
        )

    # ── Step navigation ───────────────────────────────────────────────────
    for btn_id, direction in [
        ("wizard-step1-next", +1),
        ("wizard-step2-back", -1),
        ("wizard-step3-back", -1),
        ("wizard-step3-next", +1),
        ("wizard-step4-back", -1),
    ]:
        _register_nav(app, btn_id, direction)

    # ── Save API credentials (step 2) ─────────────────────────────────────
    @app.callback(
        Output("kite-creds-status", "children"),
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("save-kite-creds-btn", "n_clicks"),
        State("kite-api-key-input", "value"),
        State("kite-api-secret-input", "value"),
        State("kite-wizard-step", "data"),
        prevent_initial_call=True,
    )
    def save_credentials(n_clicks, api_key, api_secret, current_step):
        user_id = _current_user_id()
        if not user_id:
            return "Not logged in.", dash.no_update
        if not api_key or not api_secret:
            return dbc.Alert("Both API Key and API Secret are required.",
                             color="warning", dismissable=True), dash.no_update
        try:
            user_store.upsert_kite_settings(
                user_id,
                api_key_enc=encrypt(api_key.strip()),
                api_secret_enc=encrypt(api_secret.strip()),
            )
            return (
                dbc.Alert("Credentials saved.", color="success",
                          dismissable=True, duration=3000),
                3,  # advance to step 3
            )
        except Exception:
            logger.exception("Failed to save Kite credentials for user %s", user_id)
            return (dbc.Alert("Failed to save credentials. Please try again.",
                              color="danger", dismissable=True),
                    dash.no_update)

    # ── Slider labels ─────────────────────────────────────────────────────
    @app.callback(
        Output("proximity-threshold-label", "children"),
        Input("proximity-threshold-slider", "value"),
    )
    def update_proximity_label(val):
        return f"Proximity Threshold: {val}%"

    @app.callback(
        Output("max-allocation-label", "children"),
        Input("max-allocation-slider", "value"),
    )
    def update_allocation_label(val):
        return f"Max Allocation per Stock: {val}%"

    # ── Save preferences (step 4) ─────────────────────────────────────────
    @app.callback(
        Output("kite-prefs-status", "children"),
        Input("save-kite-prefs-btn", "n_clicks"),
        State("proximity-threshold-slider", "value"),
        State("max-allocation-slider", "value"),
        State("gtt-enabled-switch", "value"),
        prevent_initial_call=True,
    )
    def save_preferences(n_clicks, proximity_pct, allocation_pct, gtt_enabled):
        user_id = _current_user_id()
        if not user_id:
            return "Not logged in."
        try:
            old_settings = user_store.get_kite_settings(user_id)
            was_disabled = not old_settings.get("gtt_enabled", False)
            user_store.upsert_kite_settings(
                user_id,
                proximity_threshold_pct=proximity_pct,
                max_allocation_pct=allocation_pct,
                gtt_enabled=bool(gtt_enabled),
            )
            status = "enabled" if gtt_enabled else "disabled"
            return dbc.Alert(
                [html.I(className="fas fa-check me-2"),
                 f"Saved. GTT auto-creation is {status}."],
                color="success", dismissable=True, duration=6000,
            )
        except Exception:
            logger.exception("Failed to save Kite preferences for user %s", user_id)
            return dbc.Alert("Failed to save. Please try again.",
                             color="danger", dismissable=True)

    # ── Connect Zerodha (step 3) ──────────────────────────────────────────
    @app.callback(
        Output("kite-login-redirect", "href"),
        Output("kite-token-status", "children"),
        Input("connect-kite-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def connect_zerodha(n_clicks):
        if not n_clicks:          # prevent_initial_call doesn't guard dynamic mounts
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            return dash.no_update, "Not logged in."
        settings = user_store.get_kite_settings(user_id)
        if not settings.get("api_key_enc"):
            return dash.no_update, dbc.Alert(
                "Save your API credentials first (Step 2).", color="warning"
            )
        try:
            api_key = decrypt(settings["api_key_enc"])
            login_url = kite_auth.generate_login_url(api_key)
            return login_url, dbc.Alert(
                "Redirecting to Zerodha login...", color="info", duration=3000
            )
        except Exception:
            logger.exception("Failed to generate Kite login URL for user %s", user_id)
            return dash.no_update, dbc.Alert(
                "Could not generate login URL. Check your API Key is saved correctly.",
                color="danger",
            )

    # ── Auto-exchange token after Kite OAuth redirect ─────────────────────
    @app.callback(
        Output("kite-token-status", "children", allow_duplicate=True),
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("kite-settings-loaded", "data"),
        prevent_initial_call=True,
    )
    def auto_exchange_token(loaded):
        if not loaded:
            raise dash.exceptions.PreventUpdate
        request_token = flask.session.pop("kite_request_token", None)
        if not request_token:
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        settings = user_store.get_kite_settings(user_id)
        if not settings.get("api_key_enc") or not settings.get("api_secret_enc"):
            return (dbc.Alert("Save API credentials before connecting.", color="warning"),
                    dash.no_update)
        try:
            from datetime import datetime, timezone
            api_key = decrypt(settings["api_key_enc"])
            api_secret = decrypt(settings["api_secret_enc"])
            access_token = kite_auth.exchange_request_token(
                api_key, request_token, api_secret
            )
            user_store.upsert_kite_settings(
                user_id,
                access_token_enc=encrypt(access_token),
                access_token_set_at=datetime.now(timezone.utc),
            )
            return (
                dbc.Alert(
                    [html.I(className="fas fa-check-circle me-2"),
                     "Zerodha connected successfully!"],
                    color="success", duration=8000,
                ),
                4,  # advance to preferences step
            )
        except Exception:
            logger.exception("Kite token exchange failed for user %s", user_id)
            return (
                dbc.Alert("Connection failed. Check your API Key and Secret.",
                          color="danger"),
                dash.no_update,
            )

    # ── Exclusions: add ───────────────────────────────────────────────────
    @app.callback(
        Output("exclusion-tags", "children"),
        Output("exclusion-input", "value"),
        Input("add-exclusion-btn", "n_clicks"),
        Input({"type": "del-exclusion", "symbol": ALL}, "n_clicks"),
        State("exclusion-input", "value"),
        prevent_initial_call=True,
    )
    def manage_exclusions(add_clicks, del_clicks, new_symbol):
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        ctx = dash.callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

        if "add-exclusion-btn" in triggered and new_symbol:
            symbol = new_symbol.strip().upper()
            if re.match(r"^[A-Z0-9]{2,20}$", symbol):
                user_store.add_exclusion(user_id, symbol)
        elif "del-exclusion" in triggered and any(del_clicks):
            import json
            id_dict = json.loads(triggered.split(".")[0])
            user_store.remove_exclusion(user_id, id_dict["symbol"])

        exclusions = user_store.get_exclusions(user_id)
        tags = [
            dbc.Badge(
                [sym, html.Span(" ×",
                                id={"type": "del-exclusion", "symbol": sym},
                                style={"cursor": "pointer", "marginLeft": "4px"},
                                n_clicks=0)],
                color="secondary",
                className="me-1 mb-1 p-2",
                style={"fontSize": "0.8rem"},
            )
            for sym in exclusions
        ]
        return tags, ""

    # ── GTT log / test run ────────────────────────────────────────────────
    @app.callback(
        Output("gtt-log-container", "children"),
        Input("run-gtt-job-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def run_and_show_log(n_clicks):
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        try:
            result = run_premarket_gtt_job()
            job_logs = result.get("logs", [])
            token_expired = result.get("token_expired", False)
            if token_expired:
                job_logs.append("ACTION REQUIRED: Token expired — reconnect Zerodha (Step 3).")
            return [
                dbc.Card(
                    dbc.CardBody([
                        html.H6("Job Output", className="mb-2"),
                        html.Pre(
                            "\n".join(job_logs),
                            style={
                                "fontSize": "0.75rem",
                                "background": "#0f172a",
                                "color": "#94a3b8",
                                "padding": "0.75rem",
                                "borderRadius": "6px",
                                "maxHeight": "280px",
                                "overflowY": "auto",
                            },
                        ),
                    ]),
                    className="mb-3",
                ),
                _build_gtt_log_table(user_id),
            ]
        except Exception as exc:
            return dbc.Alert(f"Job error — check server logs.", color="danger")

    # Refresh log on tab open
    @app.callback(
        Output("gtt-log-container", "children", allow_duplicate=True),
        Input("kite-status-interval", "n_intervals"),
        Input("strategy-tabs", "value"),
        prevent_initial_call=True,
    )
    def refresh_log_on_tab(n, active_tab):
        if active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        return _build_gtt_log_table(user_id)


def _build_gtt_log_table(user_id: int):
    rows = user_store.get_gtt_log_today(user_id)
    if not rows:
        return html.P("No GTT actions today yet.", className="text-muted small")

    status_colors = {
        "created": "success",
        "buy_at_market": "danger",
        "skipped_exists": "info",
        "skipped_low_qty": "warning",
        "skipped_proximity": "secondary",
        "failed": "danger",
    }
    table_rows = []
    for r in rows:
        table_rows.append(html.Tr([
            html.Td(r["symbol"]),
            html.Td(r["strategy"].upper()),
            html.Td(dbc.Badge(r["status"],
                              color=status_colors.get(r["status"], "secondary"))),
            html.Td(str(r["gtt_id"] or "—")),
            html.Td(r["error_msg"] or "—", className="small text-muted"),
        ]))
    return dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Symbol"), html.Th("Strategy"),
                html.Th("Status"), html.Th("GTT ID"), html.Th("Note"),
            ])),
            html.Tbody(table_rows),
        ],
        bordered=True, hover=True, size="sm", responsive=True, className="small",
    )


def _register_nav(app, btn_id: str, direction: int):
    """Register a simple Back/Next navigation callback."""
    @app.callback(
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input(btn_id, "n_clicks"),
        State("kite-wizard-step", "data"),
        prevent_initial_call=True,
    )
    def _nav(n_clicks, current_step):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        new_step = max(1, min(4, (current_step or 1) + direction))
        return new_step
