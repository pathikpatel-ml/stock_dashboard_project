import logging
import re
import threading
from collections import defaultdict
from datetime import datetime, timedelta

import dash
import flask
import flask_login
from dash import Input, Output, State

from modules.auth import user_store

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory login rate limiter (thread-safe)
# Max 5 failed attempts per IP per 15 minutes.
# ---------------------------------------------------------------------------

_failed_attempts: dict = defaultdict(list)
_lock = threading.Lock()
_MAX_ATTEMPTS = 5
_WINDOW_MINUTES = 15


def _is_rate_limited(ip: str) -> bool:
    with _lock:
        cutoff = datetime.utcnow() - timedelta(minutes=_WINDOW_MINUTES)
        _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]
        return len(_failed_attempts[ip]) >= _MAX_ATTEMPTS


def _record_failed(ip: str):
    with _lock:
        _failed_attempts[ip].append(datetime.utcnow())


def _clear_attempts(ip: str):
    with _lock:
        _failed_attempts.pop(ip, None)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def register_auth_callbacks(app):
    @app.callback(
        Output("login-error-msg", "children"),
        Output("login-redirect", "href"),
        Input("login-submit-btn", "n_clicks"),
        State("login-email", "value"),
        State("login-password", "value"),
        prevent_initial_call=True,
    )
    def handle_login(n_clicks, email, password):
        ip = flask.request.remote_addr or "unknown"

        # ── Rate limit check ──────────────────────────────────────────────
        if _is_rate_limited(ip):
            logger.warning("Rate limit hit on login from IP %s", ip)
            return (
                f"Too many failed attempts. Try again in {_WINDOW_MINUTES} minutes.",
                dash.no_update,
            )

        # ── Input validation ──────────────────────────────────────────────
        if not email or not password:
            return "Please enter your email and password.", dash.no_update

        email = email.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return "Invalid email format.", dash.no_update

        if len(password) < 6:
            return "Password must be at least 6 characters.", dash.no_update

        # ── Authentication ────────────────────────────────────────────────
        user = user_store.verify_password(email, password)
        if user is None:
            _record_failed(ip)
            remaining = _MAX_ATTEMPTS - len(_failed_attempts[ip])
            logger.warning(
                "Failed login attempt for %s from IP %s (%d attempts remaining)",
                email, ip, max(0, remaining),
            )
            return "Invalid email or password.", dash.no_update

        # ── Success ───────────────────────────────────────────────────────
        _clear_attempts(ip)
        flask_login.login_user(user, remember=True)
        logger.info("Successful login for %s from IP %s", email, ip)
        return "", "/"

    @app.callback(
        Output("login-submit-btn", "disabled"),
        Input("login-email", "value"),
        Input("login-password", "value"),
    )
    def toggle_submit_btn(email, password):
        return not (email and password)
