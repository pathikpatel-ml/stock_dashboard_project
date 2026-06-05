# app.py
import atexit
import logging
import os
from datetime import datetime, timezone

import dash
import dash_bootstrap_components as dbc
import flask
import flask_login
from dash import Input, Output, dcc, html
from flask_talisman import Talisman

import data_manager
from modules import v20_callbacks, v20_layout
from modules.admin import callbacks as admin_callbacks
from modules.admin import layout as admin_layout
from modules.auth import callbacks as auth_callbacks
from modules.auth import layout as auth_layout
from modules.auth import user_store
from modules.auth.session_store import SupabaseSessionInterface, clear_all_sessions
from modules.auth.signup import register_signup_route
from modules.breakout import callbacks as breakout_callbacks
from modules.breakout import layout as breakout_layout
from modules.kite import settings_callbacks as kite_settings_callbacks
from modules.kite import settings_layout as kite_settings_layout

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dash + Flask app setup
# ---------------------------------------------------------------------------

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    assets_folder="assets",
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)
server = app.server
app.title = "Stock Signal Dashboard"

# Render (and most PaaS) sit behind a reverse proxy — without ProxyFix,
# request.remote_addr is always 127.0.0.1, breaking per-IP rate limiting.
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402
server.wsgi_app = ProxyFix(server.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ---------------------------------------------------------------------------
# Security — secret key (fail hard if not set in production)
# ---------------------------------------------------------------------------

_secret_key = os.environ.get("FLASK_SECRET_KEY", "")
if not _secret_key:
    if os.environ.get("RENDER"):
        raise RuntimeError("FLASK_SECRET_KEY environment variable must be set in production.")
    # Local dev fallback — NOT safe for production
    _secret_key = "dev-only-insecure-key-set-FLASK_SECRET_KEY-in-env"
    logger.warning("FLASK_SECRET_KEY not set — using insecure dev default. Set it in .env")

server.secret_key = _secret_key
server.config["SESSION_COOKIE_HTTPONLY"] = True
server.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("RENDER"):
    server.config["SESSION_COOKIE_SECURE"] = True

# Server-side sessions backed by Supabase (survive restarts/redeploys).
server.session_interface = SupabaseSessionInterface()

# ---------------------------------------------------------------------------
# Security headers via Flask-Talisman
# ---------------------------------------------------------------------------
# CSP disabled because Dash requires inline JS/CSS — all other headers applied.
Talisman(
    server,
    force_https=bool(os.environ.get("RENDER")),
    strict_transport_security=bool(os.environ.get("RENDER")),
    strict_transport_security_max_age=31536000,
    content_security_policy=False,   # Dash needs inline scripts
    x_content_type_options=True,     # No MIME-type sniffing
    x_xss_protection=True,           # XSS browser filter
    referrer_policy="strict-origin-when-cross-origin",
    frame_options="SAMEORIGIN",      # Clickjack protection
)

# ---------------------------------------------------------------------------
# Flask-Login configuration
# ---------------------------------------------------------------------------

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "pathikc129@gmail.com")
server.config["ADMIN_EMAIL"] = ADMIN_EMAIL


def _is_admin(user) -> bool:
    return (user.is_authenticated
            and hasattr(user, "email")
            and user.email == ADMIN_EMAIL)


login_manager = flask_login.LoginManager()
login_manager.init_app(server)
login_manager.login_view = "/"


@login_manager.user_loader
def load_user(user_id):
    try:
        return user_store.get_user_by_id(int(user_id))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@server.route("/logout")
def logout():
    flask_login.logout_user()
    flask.session.clear()
    return flask.redirect("/")


@server.route("/api/run-gtt", methods=["POST"])
def api_run_gtt():
    """GitHub Actions calls this endpoint to trigger the pre-market GTT job."""
    token = flask.request.headers.get("X-Trigger-Token", "")
    expected = os.environ.get("GTT_TRIGGER_TOKEN", "")
    if not expected or token != expected:
        return flask.jsonify({"error": "unauthorized"}), 401
    try:
        from modules.kite.scheduler import run_premarket_gtt_job
        result = run_premarket_gtt_job()
        if result.get("token_expired"):
            return flask.jsonify({"status": "token_expired", "logs": result["logs"]}), 400
        return flask.jsonify({"status": "ok", "logs": result["logs"]})
    except Exception:
        logger.exception("GTT job error in /api/run-gtt")
        return flask.jsonify({"status": "error",
                              "error": "Internal server error — check Render logs"}), 500


@server.route("/api/health")
def api_health():
    """Wake-up ping for GitHub Actions. Returns signal count only with valid token."""
    token = flask.request.headers.get("X-Trigger-Token", "")
    expected = os.environ.get("GTT_TRIGGER_TOKEN", "")
    # Always return 200 (keeps Render awake), but only expose data with valid token
    if expected and token == expected:
        v20_count = 0 if data_manager.v20_signals_df is None else len(data_manager.v20_signals_df)
        return flask.jsonify({"status": "ok", "v20_signals": v20_count})
    return flask.jsonify({"status": "ok"})


@server.route("/kite/callback")
def kite_callback():
    """Zerodha OAuth redirect — exchange request_token server-side and save access_token."""
    if not flask_login.current_user.is_authenticated:
        return flask.redirect("/")
    request_token = flask.request.args.get("request_token")
    status = flask.request.args.get("status")
    if status != "success" or not request_token:
        return flask.redirect("/?tab=kite-settings&kite_error=cancelled")

    user_id = flask_login.current_user.id
    try:
        from modules.kite import auth as kite_auth
        from modules.auth.crypto import decrypt, encrypt
        from datetime import datetime, timezone

        settings = user_store.get_kite_settings(user_id)
        if not settings.get("api_key_enc") or not settings.get("api_secret_enc"):
            return flask.redirect("/?tab=kite-settings&kite_error=missing_creds")

        api_key    = decrypt(settings["api_key_enc"])
        api_secret = decrypt(settings["api_secret_enc"])
        access_token = kite_auth.exchange_request_token(api_key, request_token, api_secret)
        user_store.upsert_kite_settings(
            user_id,
            access_token_enc=encrypt(access_token),
            access_token_set_at=datetime.now(timezone.utc),
        )
        logger.info("Kite token exchanged successfully for user %s", user_id)
        return flask.redirect("/kite/connected")
    except Exception:
        logger.exception("Kite token exchange failed in /kite/callback for user %s", user_id)
        return flask.redirect("/kite/connected?error=exchange_failed")


@server.route("/kite/connected")
def kite_connected_page():
    """Minimal close-tab page shown after OAuth in a popup window completes."""
    error = flask.request.args.get("error")
    if error:
        icon, heading, body, color = (
            "❌", "Connection Failed",
            "Token exchange failed — please check your API Key and Secret, then try again.",
            "#f87171",
        )
    else:
        icon, heading, body, color = (
            "✅", "Zerodha Connected!",
            "Your account is authorized. This tab will close automatically.",
            "#4ade80",
        )
    return f"""<!DOCTYPE html><html><head><title>Kite {heading}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  body{{font-family:Inter,system-ui,sans-serif;margin:0;display:flex;
       justify-content:center;align-items:center;min-height:100vh;
       background:#0f172a;color:#f1f5f9;text-align:center;padding:2rem;}}
  h2{{color:{color};margin:.5rem 0;}}
  p{{color:#94a3b8;font-size:.9rem;margin:.5rem 0;}}
  .icon{{font-size:4rem;margin-bottom:1rem;}}
  button{{margin-top:1.5rem;padding:.6rem 1.5rem;border:none;border-radius:8px;
          background:#334155;color:#f1f5f9;cursor:pointer;font-size:.9rem;}}
</style>
</head><body>
<div>
  <div class="icon">{icon}</div>
  <h2>{heading}</h2>
  <p>{body}</p>
  <button onclick="window.close()">Close this tab</button>
</div>
<script>
  // Try to auto-close; if blocked by browser, user clicks the button
  try {{ setTimeout(function(){{ window.close(); }}, 2500); }} catch(e) {{}}
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# Custom HTML template
# ---------------------------------------------------------------------------

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <link rel="stylesheet" href="/assets/enhanced_styles.css?v=4.0">
        <link rel="stylesheet" href="/assets/dashboard.css?v=4.0">
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""


# ---------------------------------------------------------------------------
# Dashboard layout (shown only when authenticated)
# ---------------------------------------------------------------------------

def _main_dashboard_layout():
    user = flask_login.current_user
    user_email = user.email if user.is_authenticated else ""
    is_admin = _is_admin(user)

    # Pending badge for admin
    pending_count = 0
    if is_admin:
        try:
            pending_count = user_store.get_pending_users_count()
        except Exception:
            pass

    header_right = [
        html.Span(f"{user_email} ", className="text-muted small me-2"),
    ]
    if is_admin and pending_count > 0:
        header_right.append(
            dbc.Button(
                [dbc.Badge(str(pending_count), color="light", text_color="danger",
                           className="me-1"),
                 "pending approvals"],
                id="pending-badge-btn",
                color="danger",
                outline=True,
                size="sm",
                className="me-2",
                n_clicks=0,
            )
        )
    header_right.append(
        html.A(
            [html.I(className="fas fa-sign-out-alt me-1"), "Logout"],
            href="/logout",
            className="btn btn-sm btn-outline-secondary",
        )
    )

    tabs = [
        dcc.Tab(label="V20 Strategy", value="tab-v20",
                children=[v20_layout.create_v20_layout()]),
        dcc.Tab(label="Multi-Year Breakout", value="tab-breakout",
                children=[breakout_layout.create_breakout_layout()]),
        dcc.Tab(label="Zerodha Settings", value="tab-kite-settings",
                children=[kite_settings_layout.create_kite_settings_layout()]),
    ]
    if is_admin:
        tabs.append(
            dcc.Tab(label="Admin", value="tab-admin",
                    children=[admin_layout.create_admin_layout()])
        )

    return html.Div(
        className="app-container",
        children=[
            # Reads current URL — used to auto-switch tabs after Kite OAuth redirect
            dcc.Location(id="app-url", refresh=False),
            # Heartbeat: fires every 60 s; redirects to login when session expires
            dcc.Location(id="session-expired-redirect", refresh=True),
            dcc.Interval(id="session-heartbeat", interval=60_000, n_intervals=0),

            html.Div(
                className="d-flex justify-content-between align-items-center px-3 pt-2",
                children=[
                    html.H1("Stock Signal Dashboard", className="main-title mb-0"),
                    html.Div(header_right, className="d-flex align-items-center"),
                ],
            ),
            dcc.Tabs(
                id="strategy-tabs",
                value="tab-v20",
                children=tabs,
            ),
            html.Div(id="app-subtitle"),
            html.Footer(
                f"Stock Signal Dashboard © {datetime.now().year}",
                className="footer",
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Callable app.layout — Dash calls this per request, so current_user is valid
# ---------------------------------------------------------------------------

def serve_layout():
    if flask_login.current_user.is_authenticated:
        return _main_dashboard_layout()
    return auth_layout.create_login_layout()


app.layout = serve_layout


# ---------------------------------------------------------------------------
# Register callbacks
# ---------------------------------------------------------------------------

auth_callbacks.register_auth_callbacks(app)
v20_callbacks.register_v20_callbacks(app)
breakout_callbacks.register_breakout_callbacks(app)
kite_settings_callbacks.register_kite_settings_callbacks(app)
admin_callbacks.register_admin_callbacks(app)
register_signup_route(server)

# Open Kite OAuth URL in a new tab without reloading the current page.
# When connect_zerodha writes a URL to kite-oauth-url store, this JS opens
# it in a popup, then resets the store to null so it fires again next time.
app.clientside_callback(
    """
    function(url) {
        if (url) {
            window.open(url, '_blank', 'noopener,noreferrer');
            return null;
        }
        return window.dash_clientside.no_update;
    }
    """,
    dash.Output("kite-oauth-url", "data"),
    dash.Input("kite-oauth-url", "data"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Status callback
# ---------------------------------------------------------------------------

@app.callback(
    Output("strategy-tabs", "value"),
    Input("pending-badge-btn", "n_clicks"),
    prevent_initial_call=True,
)
def go_to_admin_tab(n_clicks):
    return "tab-admin"


@app.callback(
    Output("strategy-tabs", "value", allow_duplicate=True),
    Input("app-url", "search"),
    prevent_initial_call=True,
)
def auto_switch_tab_from_url(search):
    """Switch to Zerodha Settings tab automatically after OAuth redirect."""
    if search and "tab=kite-settings" in search:
        return "tab-kite-settings"
    raise dash.exceptions.PreventUpdate


@app.callback(
    Output("kite-oauth-result", "data"),
    Input("app-url", "search"),
    prevent_initial_call=True,
)
def capture_oauth_result(search):
    """Store the OAuth result (success/error) so render_kite_root can display it."""
    if not search:
        raise dash.exceptions.PreventUpdate
    if "kite_connected=1" in search:
        return "connected"
    if "kite_error=" in search:
        import urllib.parse
        params = dict(urllib.parse.parse_qsl(search.lstrip("?")))
        return f"error:{params.get('kite_error', 'unknown')}"
    raise dash.exceptions.PreventUpdate


@app.callback(
    Output("session-expired-redirect", "href"),
    Input("session-heartbeat", "n_intervals"),
    prevent_initial_call=True,
)
def check_session_alive(_):
    """Redirect to login within 60 s of session expiring (30-min idle TTL)."""
    if not flask_login.current_user.is_authenticated:
        return "/"
    return dash.no_update


@app.callback(
    Output("app-subtitle", "children"),
    Input("v20-signals-table-container", "children"),
    Input("strategy-tabs", "value"),
)
def update_status_display(_, active_tab):
    # Only emit the CI health-check tag on the V20 tab; blank on all others
    # so it doesn't bleed through as visible text on e.g. the Zerodha page.
    if active_tab != "tab-v20":
        return ""
    loaded_date = data_manager.LOADED_V20_FILE_DATE or datetime.now().strftime("%Y%m%d")
    if data_manager.v20_signals_df is None or (
        hasattr(data_manager.v20_signals_df, "empty") and data_manager.v20_signals_df.empty
    ):
        return html.Span("V20DataLoadedNotFound", className="status-error")
    return html.Span(f"V20DataLoaded{loaded_date}", className="status-loaded")


# ---------------------------------------------------------------------------
# Data load + scheduler startup
# ---------------------------------------------------------------------------

data_manager.load_and_process_data_on_startup()

try:
    user_store.init_db()
except Exception as _db_err:
    logger.warning("Database init failed (check SUPABASE env vars): %s", _db_err)

# Force all users to re-login on every redeploy.
# Sessions are stored in Supabase and survive restarts by default;
# clearing them here makes redeploys behave like a clean restart.
clear_all_sessions()

try:
    from modules.kite.scheduler import create_scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
except Exception as _sched_err:
    logger.warning("Scheduler failed to start: %s", _sched_err)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("DASH APP: Application ready. Starting server...")
    _debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run_server(debug=_debug, host="0.0.0.0", port=8050)
