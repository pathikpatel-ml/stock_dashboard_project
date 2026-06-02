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
from modules.auth import callbacks as auth_callbacks
from modules.auth import layout as auth_layout
from modules.auth import user_store
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

login_manager = flask_login.LoginManager()
login_manager.init_app(server)
login_manager.login_view = "/"

SESSION_TIMEOUT_MINUTES = 30


@login_manager.user_loader
def load_user(user_id):
    try:
        return user_store.get_user_by_id(int(user_id))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Session inactivity timeout (30 minutes)
# ---------------------------------------------------------------------------

@server.before_request
def enforce_session_timeout():
    """Log out users who have been idle for SESSION_TIMEOUT_MINUTES."""
    # Skip Dash internals, static files, API endpoints
    path = flask.request.path
    if (path.startswith("/_dash") or path.startswith("/assets")
            or path.startswith("/api/") or path in ("/logout", "/kite/callback")):
        return
    if not flask_login.current_user.is_authenticated:
        return
    last_active = flask.session.get("last_active")
    now = datetime.now(timezone.utc).timestamp()
    if last_active and (now - last_active) > (SESSION_TIMEOUT_MINUTES * 60):
        logger.info("Session timed out for user %s", flask_login.current_user.id)
        flask_login.logout_user()
        flask.session.clear()
        return flask.redirect("/")
    flask.session["last_active"] = now
    flask.session.modified = True


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
    """Zerodha OAuth redirect endpoint — captures request_token and stores in session."""
    if not flask_login.current_user.is_authenticated:
        return flask.redirect("/")
    request_token = flask.request.args.get("request_token")
    status = flask.request.args.get("status")
    if status != "success" or not request_token:
        return flask.redirect("/?kite_error=1#tab-kite-settings")
    flask.session["kite_request_token"] = request_token
    return flask.redirect("/?tab=kite-settings&token_ready=1")


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
    user_email = flask_login.current_user.email if flask_login.current_user.is_authenticated else ""
    return html.Div(
        className="app-container",
        children=[
            html.Div(
                className="d-flex justify-content-between align-items-center px-3 pt-2",
                children=[
                    html.H1("Stock Signal Dashboard", className="main-title mb-0"),
                    html.Div([
                        html.Span(f"{user_email} ", className="text-muted small me-2"),
                        html.A(
                            [html.I(className="fas fa-sign-out-alt me-1"), "Logout"],
                            href="/logout",
                            className="btn btn-sm btn-outline-secondary",
                        ),
                    ]),
                ],
            ),
            dcc.Tabs(
                id="strategy-tabs",
                value="tab-v20",
                children=[
                    dcc.Tab(label="V20 Strategy", value="tab-v20",
                            children=[v20_layout.create_v20_layout()]),
                    dcc.Tab(label="Multi-Year Breakout", value="tab-breakout",
                            children=[breakout_layout.create_breakout_layout()]),
                    dcc.Tab(label="Zerodha Settings", value="tab-kite-settings",
                            children=[kite_settings_layout.create_kite_settings_layout()]),
                ],
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


# ---------------------------------------------------------------------------
# Status callback
# ---------------------------------------------------------------------------

@app.callback(Output("app-subtitle", "children"), [Input("v20-signals-table-container", "children")])
def update_status_display(_):
    loaded_date = data_manager.LOADED_V20_FILE_DATE or datetime.now().strftime("%Y%m%d")
    if data_manager.v20_signals_df.empty:
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
