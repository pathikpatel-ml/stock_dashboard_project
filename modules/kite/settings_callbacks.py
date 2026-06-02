import logging

import dash
import dash_bootstrap_components as dbc
import flask
import flask_login
from dash import Input, Output, State, html

from modules.auth import user_store
from modules.auth.crypto import decrypt, encrypt
from modules.kite import auth as kite_auth
from modules.kite import portfolio as kite_portfolio
from modules.kite.scheduler import run_premarket_gtt_job

logger = logging.getLogger(__name__)


def _current_user_id():
    if flask_login.current_user.is_authenticated:
        return flask_login.current_user.id
    return None


def _connection_badge(settings):
    """Return a Bootstrap badge showing Kite connection status."""
    if settings.get("access_token_enc"):
        token_age = settings.get("access_token_set_at")
        valid = kite_portfolio.is_token_valid(token_age)
        if valid:
            return dbc.Badge("Connected", color="success", className="fs-6")
        else:
            return dbc.Badge("Token Expired — Reconnect", color="warning", className="fs-6")
    return dbc.Badge("Not Connected", color="secondary", className="fs-6")


def register_kite_settings_callbacks(app):

    # ── Load saved settings when the tab becomes visible ──────────────────
    @app.callback(
        Output("kite-api-key-input", "placeholder"),
        Output("proximity-threshold-slider", "value"),
        Output("max-allocation-slider", "value"),
        Output("gtt-enabled-switch", "value"),
        Output("kite-connection-status", "children"),
        Output("kite-settings-loaded", "data"),
        Input("kite-status-interval", "n_intervals"),
        Input("strategy-tabs", "value"),
    )
    def load_kite_settings(n_intervals, active_tab):
        user_id = _current_user_id()
        if not user_id or active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate

        settings = user_store.get_kite_settings(user_id)
        api_key_hint = (
            "•••• saved ••••" if settings.get("api_key_enc") else "Paste your Kite API Key"
        )
        return (
            api_key_hint,
            settings.get("proximity_threshold_pct", 2.0),
            settings.get("max_allocation_pct", 3.0),
            settings.get("gtt_enabled", False),
            _connection_badge(settings),
            True,
        )

    # ── Save API credentials ───────────────────────────────────────────────
    @app.callback(
        Output("kite-creds-status", "children"),
        Input("save-kite-creds-btn", "n_clicks"),
        State("kite-api-key-input", "value"),
        State("kite-api-secret-input", "value"),
        prevent_initial_call=True,
    )
    def save_credentials(n_clicks, api_key, api_secret):
        user_id = _current_user_id()
        if not user_id:
            return "Not logged in."
        if not api_key or not api_secret:
            return "Both API Key and API Secret are required."
        try:
            user_store.upsert_kite_settings(
                user_id,
                api_key_enc=encrypt(api_key.strip()),
                api_secret_enc=encrypt(api_secret.strip()),
            )
            return dbc.Alert("Credentials saved securely.", color="success",
                             dismissable=True, duration=4000)
        except Exception:
            logger.exception("Failed to save Kite credentials for user %s", user_id)
            return dbc.Alert("Failed to save credentials. Please try again.",
                             color="danger", dismissable=True)

    # ── Update slider labels ───────────────────────────────────────────────
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

    # ── Save preferences ──────────────────────────────────────────────────
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
                f"Preferences saved. GTT auto-creation is {status}.",
                color="success", dismissable=True, duration=4000
            )
        except Exception:
            logger.exception("Failed to save Kite preferences for user %s", user_id)
            return dbc.Alert("Failed to save preferences. Please try again.",
                             color="danger", dismissable=True)

    # ── Connect Zerodha — redirect to Kite login URL ──────────────────────
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
                "Save your API Key first, then click Connect.", color="warning"
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
                color="danger"
            )

    # ── Auto-exchange token when redirected back from Kite ─────────────────
    @app.callback(
        Output("kite-token-status", "children", allow_duplicate=True),
        Output("kite-connection-status", "children", allow_duplicate=True),
        Input("kite-settings-loaded", "data"),
        prevent_initial_call=True,
    )
    def auto_exchange_token(loaded):
        """Exchange request_token stored in Flask session after Kite OAuth redirect."""
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
            return dbc.Alert("Save API credentials before connecting.", color="warning"), dash.no_update

        try:
            from datetime import datetime, timezone
            api_key = decrypt(settings["api_key_enc"])
            api_secret = decrypt(settings["api_secret_enc"])
            access_token = kite_auth.exchange_request_token(api_key, request_token, api_secret)
            user_store.upsert_kite_settings(
                user_id,
                access_token_enc=encrypt(access_token),
                access_token_set_at=datetime.now(timezone.utc),
            )
            return (
                dbc.Alert("Zerodha connected successfully!", color="success", duration=5000),
                dbc.Badge("Connected", color="success", className="fs-6"),
            )
        except Exception:
            logger.exception("Kite token exchange failed for user %s", user_id)
            return (
                dbc.Alert("Connection failed. Check your API Key and Secret and try again.",
                          color="danger"),
                dash.no_update,
            )

    # ── GTT log table ──────────────────────────────────────────────────────
    @app.callback(
        Output("gtt-log-container", "children"),
        Input("run-gtt-job-btn", "n_clicks"),
        Input("kite-status-interval", "n_intervals"),
        Input("strategy-tabs", "value"),
        prevent_initial_call=False,
    )
    def refresh_gtt_log(n_clicks, n_intervals, active_tab):
        user_id = _current_user_id()
        if not user_id or active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate

        ctx = dash.callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

        job_log_section = None
        if "run-gtt-job-btn" in triggered and n_clicks:
            try:
                result = run_premarket_gtt_job()
                job_logs = result.get("logs", [])
                token_expired = result.get("token_expired", False)
                alert_color = "warning" if token_expired else "secondary"
                if token_expired:
                    job_logs.append("ACTION REQUIRED: Reconnect Zerodha (Connect Zerodha button above).")
                job_log_section = dbc.Card(
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
                                "maxHeight": "300px",
                                "overflowY": "auto",
                            },
                        ),
                    ]),
                    className="mb-3",
                )
            except Exception as exc:
                import traceback
                job_log_section = dbc.Alert(
                    [html.Strong("Job error: "), html.Pre(traceback.format_exc(),
                     style={"fontSize": "0.75rem", "marginBottom": 0})],
                    color="danger",
                    className="mb-3",
                )

        rows = user_store.get_gtt_log_today(user_id)
        if not rows:
            empty = html.P("No GTT actions today yet.", className="text-muted small")
            return html.Div([job_log_section, empty]) if job_log_section else empty

        status_colors = {
            "created": "success",
            "buy_at_market": "danger",       # needs immediate action
            "skipped_exists": "info",
            "skipped_low_qty": "warning",
            "skipped_proximity": "secondary",
            "failed": "danger",
        }

        table_rows = []
        for r in rows:
            badge = dbc.Badge(
                r["status"],
                color=status_colors.get(r["status"], "secondary"),
                className="me-1",
            )
            table_rows.append(
                html.Tr([
                    html.Td(r["symbol"]),
                    html.Td(r["strategy"].upper()),
                    html.Td(badge),
                    html.Td(str(r["gtt_id"] or "—")),
                    html.Td(r["error_msg"] or "—", className="small text-muted"),
                ])
            )

        table = dbc.Table(
            [
                html.Thead(html.Tr([
                    html.Th("Symbol"), html.Th("Strategy"),
                    html.Th("Status"), html.Th("GTT ID"), html.Th("Note"),
                ])),
                html.Tbody(table_rows),
            ],
            bordered=True, hover=True, size="sm", responsive=True,
            className="small",
        )
        return html.Div([job_log_section, table]) if job_log_section else table
