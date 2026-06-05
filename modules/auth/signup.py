import re
import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta

import flask

from modules.auth import user_store

logger = logging.getLogger(__name__)

# Simple rate limiter: max 3 signup attempts per IP per hour
_signup_attempts: dict = defaultdict(list)
_lock = threading.Lock()


def _is_signup_rate_limited(ip: str) -> bool:
    with _lock:
        cutoff = datetime.utcnow() - timedelta(hours=1)
        _signup_attempts[ip] = [t for t in _signup_attempts[ip] if t > cutoff]
        return len(_signup_attempts[ip]) >= 3


def _record_signup_attempt(ip: str):
    with _lock:
        _signup_attempts[ip].append(datetime.utcnow())


_SIGNUP_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Request Access — Stock Signal Dashboard</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.0/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  <style>
    body { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
           min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .signup-card { background: #1e293b; border: none; border-radius: 16px;
                   max-width: 440px; width: 100%; }
    .signup-card .card-body { padding: 2rem 2.25rem; }
    .logo-icon { font-size: 2rem; color: #3b82f6; }
    h4 { color: #f1f5f9; font-weight: 700; }
    .subtitle { color: #94a3b8; font-size: 0.85rem; }
    hr { border-color: #334155; }
    .form-label { color: #cbd5e1; font-size: 0.88rem; }
    .form-control { background: #0f172a; border-color: #334155; color: #f1f5f9; }
    .form-control:focus { background: #0f172a; border-color: #3b82f6; color: #f1f5f9;
                          box-shadow: 0 0 0 0.2rem rgba(59,130,246,.25); }
    .form-control::placeholder { color: #475569; }
    .btn-primary { background: #3b82f6; border-color: #3b82f6; font-weight: 600; }
    .btn-primary:hover { background: #2563eb; border-color: #2563eb; }
    .alert-success-custom { background: #052e16; border: 1px solid #16a34a;
                            color: #4ade80; border-radius: 8px; padding: 1rem; }
    .alert-error-custom { background: #450a0a; border: 1px solid #dc2626;
                          color: #f87171; border-radius: 8px; padding: 1rem; }
    .login-link { color: #3b82f6; text-decoration: none; font-size: 0.85rem; }
    .login-link:hover { color: #93c5fd; }
  </style>
</head>
<body>
  <div class="signup-card card shadow-lg mx-3">
    <div class="card-body">
      <div class="text-center mb-3">
        <i class="fas fa-chart-line logo-icon"></i>
        <h4 class="mt-2 mb-1">Stock Signal Dashboard</h4>
        <p class="subtitle">Request access — admin will review and approve</p>
      </div>
      <hr>

      {message}

      {form}

      <div class="text-center mt-3">
        <a href="/" class="login-link">
          <i class="fas fa-arrow-left me-1"></i>Back to login
        </a>
      </div>
    </div>
  </div>
</body>
</html>
"""

_FORM_HTML = """
<form method="POST" action="/signup" novalidate>
  <div class="mb-3">
    <label class="form-label">Full Name</label>
    <input type="text" name="name" class="form-control" placeholder="Your full name"
           value="{name_val}" required maxlength="100">
  </div>
  <div class="mb-3">
    <label class="form-label">Email Address</label>
    <input type="email" name="email" class="form-control" placeholder="your@email.com"
           value="{email_val}" required>
  </div>
  <div class="mb-3">
    <label class="form-label">Password</label>
    <input type="password" name="password" class="form-control"
           placeholder="Minimum 8 characters" required minlength="8">
  </div>
  <button type="submit" class="btn btn-primary w-100 mt-2">
    <i class="fas fa-paper-plane me-2"></i>Request Access
  </button>
</form>
"""

_SUCCESS_HTML = """
<div class="alert-success-custom mb-3">
  <i class="fas fa-check-circle me-2"></i>
  <strong>Request submitted!</strong><br>
  <span style="font-size:0.88rem">Your account is pending admin approval.
  You will be able to log in once approved.</span>
</div>
"""


def _render_page(message: str = "", form: str = "") -> str:
    """Render the signup page — uses .replace() to avoid CSS braces clashing with str.format()."""
    return _SIGNUP_PAGE.replace("{message}", message).replace("{form}", form)


def register_signup_route(server):
    @server.route("/signup", methods=["GET", "POST"])
    def signup():
        ip = flask.request.remote_addr or "unknown"

        if flask.request.method == "GET":
            return _render_page(form=_FORM_HTML.format(name_val="", email_val=""))

        # POST — process signup form
        if _is_signup_rate_limited(ip):
            return _render_page(
                message='<div class="alert-error-custom mb-3">Too many requests. Try again later.</div>',
                form=_FORM_HTML.format(name_val="", email_val=""),
            ), 429

        name = flask.request.form.get("name", "").strip()
        email = flask.request.form.get("email", "").strip().lower()
        password = flask.request.form.get("password", "")

        # Validation
        errors = []
        if not name or len(name) < 2:
            errors.append("Full name must be at least 2 characters.")
        if not email or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")

        if errors:
            error_html = '<div class="alert-error-custom mb-3">' + "<br>".join(errors) + "</div>"
            return _render_page(
                message=error_html,
                form=_FORM_HTML.format(name_val=name, email_val=email),
            ), 400

        # Check duplicate email
        try:
            existing = user_store.get_user_by_email(email)
            if existing:
                error_html = '<div class="alert-error-custom mb-3">An account with this email already exists.</div>'
                return _render_page(
                    message=error_html,
                    form=_FORM_HTML.format(name_val=name, email_val=""),
                ), 400

            _record_signup_attempt(ip)
            user_store.create_pending_user(name, email, password)
            logger.info("New signup request from %s (IP: %s)", email, ip)

        except Exception:
            logger.exception("Signup failed for email %s", email)
            error_html = '<div class="alert-error-custom mb-3">Something went wrong. Please try again.</div>'
            return _render_page(
                message=error_html,
                form=_FORM_HTML.format(name_val=name, email_val=email),
            ), 500

        # Success — show message, no form
        return _render_page(message=_SUCCESS_HTML)
