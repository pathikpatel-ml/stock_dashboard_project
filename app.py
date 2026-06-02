# app.py
import atexit
import os
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import flask
import flask_login
from dash import Input, Output, dcc, html

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
# Flask-Login configuration
# ---------------------------------------------------------------------------

server.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-me-in-production-set-env-var")
server.config["SESSION_COOKIE_HTTPONLY"] = True
server.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Enable Secure flag when deployed (Render uses HTTPS)
if os.environ.get("RENDER"):
    server.config["SESSION_COOKIE_SECURE"] = True

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
            # HTTP 400 → GitHub Action fails → GitHub sends automatic failure email
            return flask.jsonify({"status": "token_expired",
                                  "logs": result["logs"]}), 400
        return flask.jsonify({"status": "ok", "logs": result["logs"]})
    except Exception as exc:
        import traceback
        return flask.jsonify({"status": "error", "error": str(exc),
                              "traceback": traceback.format_exc()}), 500


@server.route("/api/health")
def api_health():
    """Wake-up ping used by GitHub Actions before triggering GTT."""
    import data_manager
    v20_count = 0 if data_manager.v20_signals_df is None else len(data_manager.v20_signals_df)
    return flask.jsonify({"status": "ok", "v20_signals": v20_count})


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
    user = flask_login.current_user
    user_email = user.email if flask_login.current_user.is_authenticated else ""
    return html.Div(
        className="app-container",
        children=[
            # Header with logout link
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
                    dcc.Tab(label="⚙️ Zerodha Settings", value="tab-kite-settings",
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


app.layout = serve_layout  # pass callable, not serve_layout()


# ---------------------------------------------------------------------------
# Register callbacks
# ---------------------------------------------------------------------------

auth_callbacks.register_auth_callbacks(app)
v20_callbacks.register_v20_callbacks(app)
breakout_callbacks.register_breakout_callbacks(app)
kite_settings_callbacks.register_kite_settings_callbacks(app)


# ---------------------------------------------------------------------------
# Status callback (only relevant when authenticated)
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
    import logging
    logging.getLogger(__name__).warning(
        "Database init failed (check DATABASE_URL env var): %s", _db_err
    )

try:
    from modules.kite.scheduler import create_scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    atexit.register(lambda: _scheduler.shutdown(wait=False))
except Exception as _sched_err:
    import logging
    logging.getLogger(__name__).warning("Scheduler failed to start: %s", _sched_err)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host="0.0.0.0", port=8050)
