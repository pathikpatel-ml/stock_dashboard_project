import base64
import logging
import os
import smtplib
import socket
import ssl
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)

_DASHBOARD_URL = "https://stock-dashboard-project.onrender.com"


# ---------------------------------------------------------------------------
# Backend: Gmail API (OAuth2 refresh token) — HTTPS port 443, never blocked
# ---------------------------------------------------------------------------

def _send_via_gmail_api(to_email: str, subject: str, html_body: str,
                         sender_email: str, client_id: str,
                         client_secret: str, refresh_token: str):
    # Step 1 — exchange refresh token for a short-lived access token
    token_resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    token_resp.raise_for_status()
    access_token = token_resp.json()["access_token"]

    # Step 2 — build MIME message and base64-encode it
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    # Step 3 — POST to Gmail send endpoint
    send_resp = requests.post(
        "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        headers={"Authorization": f"Bearer {access_token}",
                 "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=10,
    )
    send_resp.raise_for_status()
    logger.info("EMAIL SENT via Gmail API to %s: %s", to_email, subject)


# ---------------------------------------------------------------------------
# Backend: SendGrid — HTTPS port 443, never blocked
# ---------------------------------------------------------------------------

def _send_via_sendgrid(to_email: str, subject: str, html_body: str,
                        api_key: str, from_email: str):
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": from_email},
            "subject": subject,
            "content": [{"type": "text/html", "value": html_body}],
        },
        timeout=10,
    )
    if resp.status_code not in (200, 202):
        raise RuntimeError(f"SendGrid {resp.status_code}: {resp.text[:200]}")
    logger.info("EMAIL SENT via SendGrid to %s: %s", to_email, subject)


# ---------------------------------------------------------------------------
# Backend: Gmail SMTP — works locally, blocked on Render free tier
# ---------------------------------------------------------------------------

def _send_via_smtp(to_email: str, subject: str, html_body: str,
                   sender: str, password: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    # Force IPv4 — Render containers have no IPv6 routing.
    smtp_ip = socket.getaddrinfo("smtp.gmail.com", 465, socket.AF_INET)[0][4][0]
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_ip, 465, context=ctx, timeout=20) as srv:
        srv.ehlo()
        srv.login(sender, password)
        srv.sendmail(sender, to_email, msg.as_string())
    logger.info("EMAIL SENT via SMTP to %s: %s", to_email, subject)


# ---------------------------------------------------------------------------
# Public entry point — fire-and-forget, never blocks the caller
# ---------------------------------------------------------------------------

def _send(to_email: str, subject: str, html_body: str):
    """
    Dispatch email in a background daemon thread.
    Returns in < 5ms regardless of delivery outcome.

    Priority (first matching config wins):
      1. Gmail API  — GMAIL_CLIENT_ID + GMAIL_CLIENT_SECRET + GMAIL_REFRESH_TOKEN
      2. SendGrid   — SENDGRID_API_KEY
      3. SMTP       — NOTIFY_EMAIL + NOTIFY_EMAIL_PASSWORD (local dev only on Render)
    """
    gmail_client_id     = os.environ.get("GMAIL_CLIENT_ID", "")
    gmail_client_secret = os.environ.get("GMAIL_CLIENT_SECRET", "")
    gmail_refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN", "")
    sendgrid_key        = os.environ.get("SENDGRID_API_KEY", "")
    smtp_sender         = os.environ.get("NOTIFY_EMAIL", "")
    smtp_password       = os.environ.get("NOTIFY_EMAIL_PASSWORD", "")

    has_gmail_api = all([gmail_client_id, gmail_client_secret, gmail_refresh_token, smtp_sender])
    has_sendgrid  = bool(sendgrid_key and smtp_sender)
    has_smtp      = bool(smtp_sender and smtp_password)

    if not (has_gmail_api or has_sendgrid or has_smtp):
        logger.warning(
            "No email backend configured — skipping email to %s (%s). "
            "Set GMAIL_CLIENT_ID+GMAIL_CLIENT_SECRET+GMAIL_REFRESH_TOKEN (recommended) "
            "or SENDGRID_API_KEY, or NOTIFY_EMAIL+NOTIFY_EMAIL_PASSWORD for local SMTP.",
            to_email, subject,
        )
        return

    def _worker():
        try:
            if has_gmail_api:
                _send_via_gmail_api(to_email, subject, html_body, smtp_sender,
                                    gmail_client_id, gmail_client_secret, gmail_refresh_token)
            elif has_sendgrid:
                _send_via_sendgrid(to_email, subject, html_body, sendgrid_key, smtp_sender)
            else:
                _send_via_smtp(to_email, subject, html_body, smtp_sender, smtp_password)
        except Exception as exc:
            logger.error("Failed to send email to %s (%s): %s", to_email, subject, exc)

    threading.Thread(target=_worker, daemon=True, name=f"email-{to_email[:20]}").start()


# ---------------------------------------------------------------------------
# Notification templates
# ---------------------------------------------------------------------------

def notify_admin_new_signup(admin_email: str, name: str, user_email: str,
                             join_reason: str = ""):
    reason_html = (
        f"<p><strong>Reason for joining:</strong><br><em>{join_reason}</em></p>"
    ) if join_reason else ""
    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;padding:20px;">
      <h2 style="color:#e8a000;">&#128276; New Access Request</h2>
      <p><strong>{name}</strong> (<a href="mailto:{user_email}">{user_email}</a>)
         has requested access to the Stock Signal Dashboard.</p>
      {reason_html}
      <p style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}" style="background:#e8a000;color:#000;
           padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold;">
          Review in Admin Panel
        </a>
      </p>
    </body></html>
    """
    _send(admin_email, f"New access request from {name}", html)


def notify_user_approved(user_email: str, name: str):
    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;padding:20px;">
      <h2 style="color:#10d9aa;">&#10003; Access Approved!</h2>
      <p>Hi {name},</p>
      <p>Your request to access the <strong>Stock Signal Dashboard</strong>
         has been <strong>approved</strong>. You can now log in.</p>
      <p style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}" style="background:#10d9aa;color:#000;
           padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold;">
          Log In Now
        </a>
      </p>
    </body></html>
    """
    _send(user_email, "Your Stock Dashboard access has been approved", html)


def notify_user_gtt_reminder(user_email: str):
    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;padding:20px;">
      <h2 style="color:#f59e0b;">&#9203; Reconnect Zerodha — GTT job in 30 minutes</h2>
      <p>Your Zerodha access token has expired (Zerodha resets tokens at 6:00 AM IST daily).</p>
      <p>The <strong>GTT automation job runs at 8:30 AM IST</strong>. If you reconnect now,
         your orders will be placed automatically before market open (9:15 AM IST).</p>
      <p style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}/?tab=kite-settings"
           style="background:#f59e0b;color:#1e293b;padding:10px 20px;border-radius:6px;
                  text-decoration:none;font-weight:bold;">
          Reconnect Zerodha Now
        </a>
      </p>
      <p style="color:#64748b;font-size:0.82em;margin-top:16px;">
        If you reconnect after 8:30 AM, use the <strong>"Run GTT Job Now"</strong> button
        in the Zerodha Settings → Connection panel to trigger the job manually.
      </p>
    </body></html>
    """
    _send(user_email, "Action required: Reconnect Zerodha before 8:30 AM IST — GTT job in 30 min", html)


def notify_user_gtt_reminder_groww(user_email: str):
    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;padding:20px;">
      <h2 style="color:#f59e0b;">&#9203; Reconnect Groww — GTT job in 30 minutes</h2>
      <p>Your Groww access token has expired (Groww resets tokens at 6:00 AM IST daily).</p>
      <p>The <strong>GTT automation job runs at 8:30 AM IST</strong>. If you reconnect now,
         your Smart Orders will be placed automatically before market open (9:15 AM IST).</p>
      <p style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}/?tab=kite-settings"
           style="background:#00D09C;color:#0f172a;padding:10px 20px;border-radius:6px;
                  text-decoration:none;font-weight:bold;">
          Reconnect Groww Now
        </a>
      </p>
    </body></html>
    """
    _send(user_email, "Action required: Reconnect Groww before 8:30 AM IST — GTT job in 30 min", html)


def notify_user_deactivated(user_email: str, name: str):
    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;padding:20px;">
      <h2 style="color:#f59e0b;">Your account has been deactivated</h2>
      <p>Hi {name},</p>
      <p>Your access to the <strong>Stock Signal Dashboard</strong> has been
         <strong>deactivated</strong> by the administrator.</p>
      <p>If you believe this is a mistake, or you would like to request access again,
         you can re-submit a request using the signup page below.</p>
      <p style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}/signup" style="background:#f59e0b;color:#1e293b;
           padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold;">
          Request Access Again
        </a>
      </p>
    </body></html>
    """
    _send(user_email, "Your Stock Dashboard access has been deactivated", html)


def notify_user_rejected(user_email: str, name: str, reason: str = ""):
    reason_html = (f"<p><strong>Reason:</strong> {reason}</p>") if reason else ""
    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;padding:20px;">
      <h2 style="color:#dc2626;">Access Request Not Approved</h2>
      <p>Hi {name},</p>
      <p>Your request to access the <strong>Stock Signal Dashboard</strong>
         was not approved at this time.</p>
      {reason_html}
      <p style="color:#64748b;font-size:0.85em;margin-top:16px;">
        If you believe this is a mistake, please contact the administrator.
      </p>
    </body></html>
    """
    _send(user_email, "Regarding your Stock Dashboard access request", html)
