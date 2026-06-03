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
    _progress_bar,
    _step1_card,
    _step2_card,
    _step3_card,
    _step4_card,
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
    """Return the step the user should land on based on their current state."""
    if not settings.get("api_key_enc"):
        return 1
    _, connected = _connection_status(settings)
    if not connected:
        return 3
    if not settings.get("gtt_enabled"):
        return 4
    return 4


def register_kite_settings_callbacks(app):

    # ── Load wizard on tab open ────────────────────────────────────────────
    @app.callback(
        Output("kite-wizard-step", "data"),
        Output("kite-settings-loaded", "data"),
        Input("strategy-tabs", "value"),
        Input("kite-status-interval", "n_intervals"),
    )
    def initialise_wizard(active_tab, n_intervals):
        if active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        settings = user_store.get_kite_settings(user_id)
        step = _determine_wizard_step(settings)
        return step, True

    # ── Render wizard step content + progress bar ─────────────────────────
    @app.callback(
        Output("wizard-progress", "children"),
        Output("wizard-step-content", "children"),
        Output("wizard-test-run-section", "children"),
        Input("kite-wizard-step", "data"),
    )
    def render_wizard_step(step):
        if step is None:
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        settings = user_store.get_kite_settings(user_id)
        exclusions = user_store.get_exclusions(user_id)
        badge, connected = _connection_status(settings)
        api_key_saved = bool(settings.get("api_key_enc"))

        progress = _progress_bar(step)

        if step == 1:
            content = _step1_card()
        elif step == 2:
            content = _step2_card(api_key_saved)
        elif step == 3:
            content = _step3_card(badge)
        else:
            content = _step4_card(settings, exclusions)

        # Show test-run card once connected
        test_section = dash.no_update
        if connected:
            test_section = dbc.Card(
                dbc.CardBody([
                    html.H6([html.I(className="fas fa-vial me-2"),
                             "Test GTT Job"], className="mb-3"),
                    dbc.Button(
                        [html.I(className="fas fa-play me-2"), "Run GTT Job Now"],
                        id="run-gtt-job-btn",
                        color="warning",
                        size="sm",
                        className="mb-3",
                        n_clicks=0,
                    ),
                    html.Div(id="gtt-log-container"),
                ]),
                className="mt-4 section-container",
            )
        return progress, content, test_section

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
                color="success", dismissable=True, duration=4000,
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
                    color="success", duration=5000,
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
