import json
import logging
import re
from datetime import datetime, timezone

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
from modules.groww.settings_layout import (
    broker_picker_card,
    groww_step1_card,
    groww_step2_card,
    groww_step3_card,
    groww_step4_card,
    groww_sidebar,
    groww_connection_section,
    groww_schedule_section,
    groww_prefs_section,
    groww_exclusions_section,
    groww_activity_section,
    _groww_progress_bar,
)

logger = logging.getLogger(__name__)


def _current_user_id():
    if flask_login.current_user.is_authenticated:
        return flask_login.current_user.id
    return None


# ── Broker resolution helpers ───────────────────────────────────────────────

def _resolve_broker(user_id: int, broker_store: str) -> tuple:
    """
    Returns (broker, kite_settings, groww_settings).
    broker is 'zerodha', 'groww', or None (brand new user).
    """
    kite_settings = user_store.get_kite_settings(user_id)
    groww_settings = user_store.get_groww_settings(user_id)

    broker_choice = kite_settings.get("broker_choice")

    if broker_choice == "groww" or groww_settings.get("app_id_enc"):
        return "groww", kite_settings, groww_settings
    if kite_settings.get("api_key_enc") or broker_choice == "zerodha":
        return "zerodha", kite_settings, groww_settings
    if broker_store in ("zerodha", "groww"):
        return broker_store, kite_settings, groww_settings
    return None, kite_settings, groww_settings  # truly new user


def _connection_status(settings: dict) -> tuple:
    """(badge, is_connected_today) for Zerodha."""
    if settings.get("access_token_enc"):
        valid = kite_portfolio.is_token_valid(settings.get("access_token_set_at"))
        if valid:
            return dbc.Badge(
                [html.I(className="fas fa-circle me-1"), "Connected"],
                color="success", className="fs-6 p-2",
            ), True
        return dbc.Badge(
            [html.I(className="fas fa-exclamation-triangle me-1"), "Token Expired — Reconnect"],
            color="warning", className="fs-6 p-2",
        ), False
    return dbc.Badge(
        [html.I(className="fas fa-times-circle me-1"), "Not Connected"],
        color="secondary", className="fs-6 p-2",
    ), False


def _determine_wizard_step(settings: dict) -> int:
    if not settings.get("api_key_enc"):
        return 0
    _, connected = _connection_status(settings)
    if not connected:
        return 3
    return 4


def _determine_wizard_step_groww(settings: dict) -> int:
    if not settings.get("app_id_enc"):
        return 1
    from modules.groww import portfolio as gp
    valid = gp.is_token_valid(settings.get("access_token_set_at"))
    if not settings.get("access_token_enc") or not valid:
        return 3
    return 4


# ── Register all callbacks ──────────────────────────────────────────────────

def register_kite_settings_callbacks(app):

    # ── Initialise wizard + broker (fires on tab open) ────────────────────
    @app.callback(
        Output("kite-wizard-step", "data"),
        Output("kite-settings-loaded", "data"),
        Output("active-broker-store", "data"),
        Input("strategy-tabs", "value"),
    )
    def initialise_wizard(active_tab):
        if active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        broker, kite_settings, groww_settings = _resolve_broker(user_id, None)

        if broker == "groww":
            step = _determine_wizard_step_groww(groww_settings)
        elif broker == "zerodha":
            step = _determine_wizard_step(kite_settings)
        else:
            step = 0  # brand new user → broker picker

        return step, True, broker

    # ── Intro landing page CTA (Zerodha only fallback) ────────────────────
    @app.callback(
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("wizard-intro-start-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def start_wizard_from_intro(n_clicks):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        return 1

    # ── Broker picker — user chooses Zerodha or Groww ─────────────────────
    @app.callback(
        Output("active-broker-store", "data", allow_duplicate=True),
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("pick-zerodha-btn", "n_clicks"),
        Input("pick-groww-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def pick_broker(zerodha_clicks, groww_clicks):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise dash.exceptions.PreventUpdate
        triggered = ctx.triggered[0]["prop_id"].split(".")[0]
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        if triggered == "pick-zerodha-btn" and zerodha_clicks:
            user_store.upsert_kite_settings(user_id, broker_choice="zerodha")
            return "zerodha", 1
        if triggered == "pick-groww-btn" and groww_clicks:
            user_store.upsert_kite_settings(user_id, broker_choice="groww")
            return "groww", 1
        raise dash.exceptions.PreventUpdate

    # ── Groww — switch back to Zerodha from step 1 ────────────────────────
    @app.callback(
        Output("active-broker-store", "data", allow_duplicate=True),
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("groww-switch-to-zerodha-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def switch_to_zerodha(n_clicks):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        user_store.upsert_kite_settings(user_id, broker_choice="zerodha")
        return "zerodha", 0

    # ── Master render: single callback, one set of elements in DOM ───────
    @app.callback(
        Output("kite-settings-root", "children"),
        Input("strategy-tabs", "value"),
        Input("kite-status-interval", "n_intervals"),
        Input("kite-wizard-step", "data"),
        Input("kite-panel", "data"),
        Input("kite-oauth-result", "data"),
        Input("active-broker-store", "data"),
    )
    def render_kite_root(active_tab, _, wizard_step, panel, oauth_result, broker_store):
        if active_tab != "tab-kite-settings":
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        broker, kite_settings, groww_settings = _resolve_broker(user_id, broker_store)

        # ── OAuth toast (Zerodha only) ─────────────────────────────────────
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
                "exchange_failed": "Token exchange failed — your API Key or Secret may be wrong.",
            }.get(err_code, f"Connection failed ({err_code}). Please try again.")
            oauth_toast = dbc.Alert(
                [html.I(className="fas fa-exclamation-circle me-2"), msg],
                color="danger", dismissable=True, className="mb-3",
            )

        # ── Brand new user — broker picker ────────────────────────────────
        if broker is None:
            return [oauth_toast] if oauth_toast else [broker_picker_card()]

        # ═══════════════════════════════════════════════════════════════════
        # ZERODHA FLOW (unchanged)
        # ═══════════════════════════════════════════════════════════════════
        if broker == "zerodha":
            badge, connected = _connection_status(kite_settings)
            api_key_saved = bool(kite_settings.get("api_key_enc"))

            if not api_key_saved:
                step = wizard_step if wizard_step is not None else _determine_wizard_step(kite_settings)
                if step == 0:
                    # Check if user explicitly picked Zerodha → show intro card
                    # (if broker_choice='zerodha' was set, skip broker picker)
                    prefix = [oauth_toast] if oauth_toast else []
                    return prefix + [_intro_card()]
                exclusions = user_store.get_exclusions(user_id) if step == 4 else []
                if step == 1:   step_content = _step1_card()
                elif step == 2: step_content = _step2_card(False)
                elif step == 3: step_content = _step3_card(badge)
                else:           step_content = _step4_card(kite_settings, exclusions)
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

            # Zerodha dashboard
            exclusions = user_store.get_exclusions(user_id)
            _, is_connected = _token_status(kite_settings)
            active_panel = panel or "connection"
            if active_panel == "connection":   sec = _connection_section(kite_settings)
            elif active_panel == "schedule":   sec = _schedule_section(kite_settings)
            elif active_panel == "prefs":      sec = _prefs_section(kite_settings)
            elif active_panel == "exclusions": sec = _exclusions_section(exclusions)
            elif active_panel == "activity":   sec = _activity_section(user_id)
            else:                              sec = _connection_section(kite_settings)

            parts = [oauth_toast] if oauth_toast else []
            if kite_settings.get("access_token_enc") and not is_connected:
                banner_url = ""
                if kite_settings.get("api_key_enc"):
                    try:
                        banner_url = kite_auth.generate_login_url(decrypt(kite_settings["api_key_enc"]))
                    except Exception:
                        pass
                parts.append(_expired_banner(banner_url))
            parts.append(html.Div(
                style={"display": "flex", "gap": "0", "alignItems": "flex-start"},
                children=[
                    html.Div(_sidebar(active_panel, kite_settings),
                             style={"minWidth": "185px", "paddingRight": "16px",
                                    "borderRight": "1px solid #1e3a5f"}),
                    html.Div(sec, style={"flex": "1", "paddingLeft": "24px", "minWidth": "0"}),
                ],
            ))
            return parts

        # ═══════════════════════════════════════════════════════════════════
        # GROWW FLOW
        # ═══════════════════════════════════════════════════════════════════
        from modules.groww import portfolio as gp
        app_id_saved = bool(groww_settings.get("app_id_enc"))

        if not app_id_saved:
            step = wizard_step if wizard_step is not None else 1
            step = max(1, step)  # Groww wizard starts at 1
            exclusions = user_store.get_groww_exclusions(user_id) if step == 4 else []
            if step == 1:   step_content = groww_step1_card()
            elif step == 2: step_content = groww_step2_card(False)
            elif step == 3: step_content = groww_step3_card(groww_settings)
            else:           step_content = groww_step4_card(groww_settings, exclusions)
            parts = [_groww_progress_bar(step), step_content]
            is_connected = gp.is_token_valid(groww_settings.get("access_token_set_at"))
            if is_connected:
                parts.append(dbc.Card(dbc.CardBody([
                    html.H6([html.I(className="fas fa-vial me-2"), "Test GTT Job"],
                            className="mb-3"),
                    dbc.Button([html.I(className="fas fa-play me-2"), "Run GTT Job Now"],
                               id="run-gtt-job-btn", color="warning", size="sm",
                               className="mb-3", n_clicks=0),
                    html.Div(id="gtt-log-container"),
                ]), className="mt-4 section-container"))
            return parts

        # Groww dashboard
        is_connected = gp.is_token_valid(groww_settings.get("access_token_set_at"))
        is_auto = groww_settings.get("totp_auto_refresh", False)
        exclusions = user_store.get_groww_exclusions(user_id)

        active_panel = panel or "connection"
        if active_panel == "connection":   sec = groww_connection_section(groww_settings)
        elif active_panel == "schedule":   sec = groww_schedule_section(groww_settings)
        elif active_panel == "prefs":      sec = groww_prefs_section(groww_settings)
        elif active_panel == "exclusions": sec = groww_exclusions_section(exclusions)
        elif active_panel == "activity":   sec = groww_activity_section(user_id)
        else:                              sec = groww_connection_section(groww_settings)

        parts = []
        if groww_settings.get("access_token_enc") and not is_connected and not is_auto:
            parts.append(dbc.Alert(
                className="mb-3 d-flex align-items-center justify-content-between flex-wrap gap-2",
                color="warning",
                style={"fontSize": "0.88rem"},
                children=[
                    html.Div([html.I(className="fas fa-exclamation-triangle me-2"),
                              html.Strong("Daily token expired. "),
                              "Go to Connection to paste your new Groww token."]),
                ],
            ))
        elif groww_settings.get("access_token_enc") and not is_connected and is_auto:
            parts.append(dbc.Alert(
                className="mb-3 d-flex align-items-center justify-content-between flex-wrap gap-2",
                color="info",
                style={"fontSize": "0.88rem"},
                children=[
                    html.Div([html.I(className="fas fa-magic me-2"),
                              html.Strong("Token expired — TOTP auto-refresh available. "),
                              "Go to Connection and click Auto-Refresh."]),
                ],
            ))

        # Groww header badge
        parts.append(html.Div(className="d-flex align-items-center mb-3 gap-2", children=[
            html.Div("G", style={
                "width": "28px", "height": "28px", "borderRadius": "6px",
                "background": "#00D09C", "color": "white", "fontWeight": "700",
                "fontSize": "0.9rem", "display": "inline-flex", "alignItems": "center",
                "justifyContent": "center",
            }),
            html.Span("Groww Trade API", className="fw-semibold",
                      style={"color": "#00D09C"}),
            (dbc.Badge([html.I(className="fas fa-magic me-1"), "Auto-refresh"],
                       color="success", className="py-1",
                       style={"fontSize": "0.72rem"})
             if is_auto else
             dbc.Badge("Manual mode", color="secondary", className="py-1",
                       style={"fontSize": "0.72rem"})),
        ]))

        parts.append(html.Div(
            style={"display": "flex", "gap": "0", "alignItems": "flex-start"},
            children=[
                html.Div(groww_sidebar(active_panel, groww_settings),
                         style={"minWidth": "185px", "paddingRight": "16px",
                                "borderRight": "1px solid #083d2f"}),
                html.Div(sec, style={"flex": "1", "paddingLeft": "24px", "minWidth": "0"}),
            ],
        ))
        return parts

    # ── Sidebar navigation (Zerodha nav buttons) ──────────────────────────
    @app.callback(
        Output("kite-panel", "data"),
        Input({"type": "kite-nav-btn", "panel": ALL}, "n_clicks"),
        Input({"type": "groww-nav-btn", "panel": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )
    def sidebar_nav(kite_clicks, groww_clicks):
        ctx = dash.callback_context
        all_clicks = (kite_clicks or []) + (groww_clicks or [])
        if not ctx.triggered or not any((n or 0) for n in all_clicks):
            raise dash.exceptions.PreventUpdate
        id_dict = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
        return id_dict["panel"]

    # ── Banner "Reconnect Now" (Zerodha) ──────────────────────────────────
    @app.callback(
        Output("kite-oauth-url", "data", allow_duplicate=True),
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
            return dash.no_update, "connection"
        try:
            login_url = kite_auth.generate_login_url(decrypt(settings["api_key_enc"]))
            return login_url, "connection"
        except Exception:
            logger.exception("Banner reconnect: could not generate login URL for user %s", user_id)
            return dash.no_update, "connection"

    # ── initialise_wizard: already defined above ──────────────────────────

    # ── Step navigation (Zerodha) ─────────────────────────────────────────
    for btn_id, direction in [
        ("wizard-step1-next", +1),
        ("wizard-step2-back", -1),
        ("wizard-step3-back", -1),
        ("wizard-step3-next", +1),
        ("wizard-step4-back", -1),
    ]:
        _register_nav(app, btn_id, direction, min_step=1, max_step=4)

    # ── Step navigation (Groww) ───────────────────────────────────────────
    for btn_id, direction in [
        ("groww-wizard-step1-next", +1),
        ("groww-wizard-step2-back", -1),
        ("groww-wizard-step3-back", -1),
        ("groww-wizard-step3-next", +1),
        ("groww-wizard-step4-back", -1),
    ]:
        _register_nav(app, btn_id, direction, min_step=1, max_step=4)

    # ── Save Zerodha API credentials (step 2) ─────────────────────────────
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
            return (dbc.Alert("Credentials saved.", color="success",
                              dismissable=True, duration=3000), 3)
        except Exception:
            logger.exception("Failed to save Kite credentials for user %s", user_id)
            return (dbc.Alert("Failed to save credentials. Please try again.",
                              color="danger", dismissable=True), dash.no_update)

    # ── Save Groww credentials (step 2) ───────────────────────────────────
    @app.callback(
        Output("groww-creds-status", "children"),
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("save-groww-creds-btn", "n_clicks"),
        State("groww-app-id-input", "value"),
        State("groww-app-secret-input", "value"),
        State("groww-totp-secret-input", "value"),
        State("groww-totp-auto-switch", "value"),
        prevent_initial_call=True,
    )
    def save_groww_credentials(n_clicks, app_id, app_secret, totp_secret, totp_auto):
        user_id = _current_user_id()
        if not user_id:
            return "Not logged in.", dash.no_update
        if not app_id or not app_secret:
            return dbc.Alert("App ID and App Secret are required.",
                             color="warning", dismissable=True), dash.no_update
        totp_enabled = bool(totp_auto) and bool(totp_secret and totp_secret.strip())
        try:
            kwargs = dict(
                app_id_enc=encrypt(app_id.strip()),
                app_secret_enc=encrypt(app_secret.strip()),
                totp_auto_refresh=totp_enabled,
            )
            if totp_enabled:
                kwargs["totp_secret_enc"] = encrypt(totp_secret.strip())
            user_store.upsert_groww_settings(user_id, **kwargs)
            msg = ("Credentials saved with TOTP auto-refresh enabled."
                   if totp_enabled else "Credentials saved (manual mode).")
            return (dbc.Alert(msg, color="success", dismissable=True, duration=4000), 3)
        except Exception:
            logger.exception("Failed to save Groww credentials for user %s", user_id)
            return (dbc.Alert("Failed to save. Please try again.",
                              color="danger", dismissable=True), dash.no_update)

    # ── Groww TOTP — generate & save token ────────────────────────────────
    @app.callback(
        Output("groww-token-status", "children"),
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("groww-generate-token-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def groww_generate_token(n_clicks):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        settings = user_store.get_groww_settings(user_id)
        if not settings.get("totp_secret_enc") or not settings.get("app_id_enc"):
            return dbc.Alert("TOTP secret or App ID not saved. Go back to step 2.",
                             color="warning"), dash.no_update
        try:
            from modules.groww.auth import auto_refresh_token
            new_token = auto_refresh_token(settings["app_id_enc"], settings["totp_secret_enc"])
            user_store.upsert_groww_settings(
                user_id,
                access_token_enc=encrypt(new_token),
                access_token_set_at=datetime.now(timezone.utc),
            )
            return (dbc.Alert(
                [html.I(className="fas fa-check-circle me-2"),
                 "Token generated and saved! Groww is connected."],
                color="success", duration=8000,
            ), 4)
        except Exception as exc:
            logger.exception("Groww token generation failed for user %s", user_id)
            return (dbc.Alert(f"Token generation failed: {exc}",
                              color="danger", dismissable=True), dash.no_update)

    # ── Groww manual — save pasted token ──────────────────────────────────
    @app.callback(
        Output("groww-token-status", "children", allow_duplicate=True),
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input("groww-save-manual-token-btn", "n_clicks"),
        State("groww-manual-token-input", "value"),
        prevent_initial_call=True,
    )
    def groww_save_manual_token(n_clicks, token):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        if not token or not token.strip():
            return dbc.Alert("Please enter an access token.", color="warning"), dash.no_update
        try:
            user_store.upsert_groww_settings(
                user_id,
                access_token_enc=encrypt(token.strip()),
                access_token_set_at=datetime.now(timezone.utc),
            )
            return (dbc.Alert(
                [html.I(className="fas fa-check-circle me-2"), "Token saved! Groww is connected."],
                color="success", duration=8000,
            ), 4)
        except Exception as exc:
            logger.exception("Groww manual token save failed for user %s", user_id)
            return (dbc.Alert(f"Failed to save: {exc}", color="danger", dismissable=True),
                    dash.no_update)

    # ── Groww dashboard — auto-refresh token button ───────────────────────
    @app.callback(
        Output("groww-token-status", "children", allow_duplicate=True),
        Input("groww-refresh-token-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def groww_refresh_token_dashboard(n_clicks):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        settings = user_store.get_groww_settings(user_id)
        if settings.get("totp_secret_enc") and settings.get("app_id_enc"):
            try:
                from modules.groww.auth import auto_refresh_token
                new_token = auto_refresh_token(settings["app_id_enc"], settings["totp_secret_enc"])
                user_store.upsert_groww_settings(
                    user_id,
                    access_token_enc=encrypt(new_token),
                    access_token_set_at=datetime.now(timezone.utc),
                )
                return dbc.Alert(
                    [html.I(className="fas fa-check-circle me-2"), "Token refreshed!"],
                    color="success", duration=5000,
                )
            except Exception as exc:
                return dbc.Alert(f"Refresh failed: {exc}", color="danger", dismissable=True)
        return dbc.Alert("No TOTP secret configured — use manual token paste.",
                         color="warning", dismissable=True)

    # ── TOTP input section toggle (show/hide TOTP field) ──────────────────
    @app.callback(
        Output("groww-totp-input-section", "style"),
        Input("groww-totp-auto-switch", "value"),
        prevent_initial_call=False,
    )
    def toggle_totp_section(enabled):
        return {} if enabled else {"display": "none"}

    # ── Zerodha slider labels ─────────────────────────────────────────────
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

    # ── Groww slider labels ───────────────────────────────────────────────
    @app.callback(
        Output("groww-proximity-threshold-label", "children"),
        Input("groww-proximity-threshold-slider", "value"),
    )
    def update_groww_proximity_label(val):
        return f"Proximity Threshold: {val}%"

    @app.callback(
        Output("groww-max-allocation-label", "children"),
        Input("groww-max-allocation-slider", "value"),
    )
    def update_groww_allocation_label(val):
        return f"Max Allocation per Stock: {val}%"

    # ── Save Zerodha preferences ──────────────────────────────────────────
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
                [html.I(className="fas fa-check me-2"), f"Saved. GTT auto-creation is {status}."],
                color="success", dismissable=True, duration=6000,
            )
        except Exception:
            logger.exception("Failed to save Kite preferences for user %s", user_id)
            return dbc.Alert("Failed to save.", color="danger", dismissable=True)

    # ── Save Groww preferences ────────────────────────────────────────────
    @app.callback(
        Output("groww-prefs-status", "children"),
        Input("save-groww-prefs-btn", "n_clicks"),
        State("groww-proximity-threshold-slider", "value"),
        State("groww-max-allocation-slider", "value"),
        State("groww-gtt-enabled-switch", "value"),
        prevent_initial_call=True,
    )
    def save_groww_preferences(n_clicks, proximity_pct, allocation_pct, gtt_enabled):
        user_id = _current_user_id()
        if not user_id:
            return "Not logged in."
        try:
            user_store.upsert_groww_settings(
                user_id,
                proximity_threshold_pct=proximity_pct,
                max_allocation_pct=allocation_pct,
                gtt_enabled=bool(gtt_enabled),
            )
            status = "enabled" if gtt_enabled else "disabled"
            return dbc.Alert(
                [html.I(className="fas fa-check me-2"),
                 f"Saved. Smart Order auto-creation is {status}."],
                color="success", dismissable=True, duration=6000,
            )
        except Exception:
            logger.exception("Failed to save Groww preferences for user %s", user_id)
            return dbc.Alert("Failed to save.", color="danger", dismissable=True)

    # ── Connect Zerodha (OAuth) ───────────────────────────────────────────
    @app.callback(
        Output("kite-oauth-url", "data"),
        Output("kite-token-status", "children"),
        Input("connect-kite-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def connect_zerodha(n_clicks):
        if not n_clicks:
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
            login_url = kite_auth.generate_login_url(decrypt(settings["api_key_enc"]))
            return login_url, dbc.Alert(
                [html.I(className="fas fa-external-link-alt me-2"),
                 "Zerodha login opened in a new tab. Complete authorization there — "
                 "this page will update automatically within 30 seconds."],
                color="info", duration=60000,
            )
        except Exception:
            logger.exception("Failed to generate Kite login URL for user %s", user_id)
            return dash.no_update, dbc.Alert(
                "Could not generate login URL. Check your API Key.", color="danger"
            )

    # ── Auto-exchange Zerodha token after OAuth redirect ──────────────────
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
            api_key = decrypt(settings["api_key_enc"])
            api_secret = decrypt(settings["api_secret_enc"])
            access_token = kite_auth.exchange_request_token(api_key, request_token, api_secret)
            user_store.upsert_kite_settings(
                user_id,
                access_token_enc=encrypt(access_token),
                access_token_set_at=datetime.now(timezone.utc),
            )
            return (dbc.Alert(
                [html.I(className="fas fa-check-circle me-2"),
                 "Zerodha connected successfully!"],
                color="success", duration=8000,
            ), 4)
        except Exception:
            logger.exception("Kite token exchange failed for user %s", user_id)
            return (dbc.Alert("Connection failed. Check API Key and Secret.", color="danger"),
                    dash.no_update)

    # ── Zerodha exclusions ────────────────────────────────────────────────
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
            id_dict = json.loads(triggered.split(".")[0])
            user_store.remove_exclusion(user_id, id_dict["symbol"])
        exclusions = user_store.get_exclusions(user_id)
        tags = [
            dbc.Badge(
                [sym, html.Span(" ×", id={"type": "del-exclusion", "symbol": sym},
                                style={"cursor": "pointer", "marginLeft": "4px"},
                                n_clicks=0)],
                color="secondary", className="me-1 mb-1 p-2", style={"fontSize": "0.8rem"},
            )
            for sym in exclusions
        ]
        return tags, ""

    # ── Groww exclusions ──────────────────────────────────────────────────
    @app.callback(
        Output("groww-exclusion-tags", "children"),
        Output("groww-exclusion-input", "value"),
        Input("groww-add-exclusion-btn", "n_clicks"),
        Input({"type": "groww-del-exclusion", "symbol": ALL}, "n_clicks"),
        State("groww-exclusion-input", "value"),
        prevent_initial_call=True,
    )
    def manage_groww_exclusions(add_clicks, del_clicks, new_symbol):
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate
        ctx = dash.callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
        if "groww-add-exclusion-btn" in triggered and new_symbol:
            symbol = new_symbol.strip().upper()
            if re.match(r"^[A-Z0-9]{2,20}$", symbol):
                user_store.add_groww_exclusion(user_id, symbol)
        elif "groww-del-exclusion" in triggered and any(del_clicks):
            id_dict = json.loads(triggered.split(".")[0])
            user_store.remove_groww_exclusion(user_id, id_dict["symbol"])
        exclusions = user_store.get_groww_exclusions(user_id)
        tags = [
            dbc.Badge(
                [sym, html.Span(" ×", id={"type": "groww-del-exclusion", "symbol": sym},
                                style={"cursor": "pointer", "marginLeft": "4px"},
                                n_clicks=0)],
                color="secondary", className="me-1 mb-1 p-2", style={"fontSize": "0.8rem"},
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
            if result.get("token_expired"):
                job_logs.append("ACTION REQUIRED: Token expired — reconnect your broker.")
            return [
                dbc.Card(dbc.CardBody([
                    html.H6("Job Output", className="mb-2"),
                    html.Pre("\n".join(job_logs), style={
                        "fontSize": "0.75rem", "background": "#0f172a",
                        "color": "#94a3b8", "padding": "0.75rem",
                        "borderRadius": "6px", "maxHeight": "280px", "overflowY": "auto",
                    }),
                ]), className="mb-3"),
                _build_gtt_log_table(user_id),
            ]
        except Exception as exc:
            return dbc.Alert("Job error — check server logs.", color="danger")

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
        "created": "success", "buy_at_market": "danger",
        "skipped_exists": "info", "skipped_low_qty": "warning",
        "skipped_proximity": "secondary", "failed": "danger",
    }
    table_rows = []
    for r in rows:
        broker_badge = dbc.Badge(
            r.get("broker", "zerodha").upper(),
            color="primary" if r.get("broker", "zerodha") == "zerodha" else "success",
            className="me-1",
            style={"fontSize": "0.65rem"},
        )
        table_rows.append(html.Tr([
            html.Td([broker_badge, r["symbol"]]),
            html.Td(r["strategy"].upper()),
            html.Td(dbc.Badge(r["status"], color=status_colors.get(r["status"], "secondary"))),
            html.Td(str(r["gtt_id"] or "—")),
            html.Td(r["error_msg"] or "—", className="small text-muted"),
        ]))
    return dbc.Table(
        [html.Thead(html.Tr([
            html.Th("Symbol"), html.Th("Strategy"),
            html.Th("Status"), html.Th("Order ID"), html.Th("Note"),
        ])),
         html.Tbody(table_rows)],
        bordered=True, hover=True, size="sm", responsive=True, className="small",
    )


def _register_nav(app, btn_id: str, direction: int, min_step: int = 1, max_step: int = 4):
    @app.callback(
        Output("kite-wizard-step", "data", allow_duplicate=True),
        Input(btn_id, "n_clicks"),
        State("kite-wizard-step", "data"),
        prevent_initial_call=True,
    )
    def _nav(n_clicks, current_step):
        if not n_clicks:
            raise dash.exceptions.PreventUpdate
        new_step = max(min_step, min(max_step, (current_step or min_step) + direction))
        return new_step
