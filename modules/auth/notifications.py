import logging
import os
import smtplib
import socket
import ssl
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_DASHBOARD_URL = "https://stock-dashboard-project.onrender.com"


def _send_via_sendgrid(to_email: str, subject: str, html_body: str, api_key: str, from_email: str):
    """HTTP-based send via SendGrid — uses port 443, works on Render free tier."""
    import requests
    resp = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
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


def _send_via_smtp(to_email: str, subject: str, html_body: str, sender: str, password: str):
    """SMTP send (port 465 SSL). Works locally; may be blocked on Render free tier."""
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


def _send(to_email: str, subject: str, html_body: str):
    """
    Fire-and-forget email. Always runs in a background daemon thread so it
    never blocks a Dash callback and never triggers gunicorn's worker timeout.

    Priority:
      1. SendGrid (SENDGRID_API_KEY set) — HTTP, works on Render free tier
      2. Gmail SMTP (NOTIFY_EMAIL + NOTIFY_EMAIL_PASSWORD set) — works locally
    """
    sendgrid_key = os.environ.get("SENDGRID_API_KEY", "")
    smtp_sender   = os.environ.get("NOTIFY_EMAIL", "")
    smtp_password  = os.environ.get("NOTIFY_EMAIL_PASSWORD", "")

    if not sendgrid_key and not (smtp_sender and smtp_password):
        logger.warning(
            "No email credentials configured — skipping email to %s (%s). "
            "Set SENDGRID_API_KEY (recommended on Render) or "
            "NOTIFY_EMAIL + NOTIFY_EMAIL_PASSWORD.",
            to_email, subject,
        )
        return

    def _worker():
        try:
            if sendgrid_key and smtp_sender:
                _send_via_sendgrid(to_email, subject, html_body, sendgrid_key, smtp_sender)
            elif sendgrid_key:
                # SendGrid requires a verified sender — use a placeholder if NOTIFY_EMAIL not set
                _send_via_sendgrid(to_email, subject, html_body, sendgrid_key,
                                   "noreply@stock-dashboard-project.onrender.com")
            else:
                _send_via_smtp(to_email, subject, html_body, smtp_sender, smtp_password)
        except Exception as exc:
            logger.error("Failed to send email to %s (%s): %s", to_email, subject, exc)

    # Daemon thread — if the process exits the thread is abandoned (acceptable).
    threading.Thread(target=_worker, daemon=True, name=f"email-{to_email[:20]}").start()


def notify_admin_new_signup(admin_email: str, name: str, user_email: str,
                             join_reason: str = ""):
    reason_html = (
        f"<p><strong>Reason for joining:</strong><br>"
        f"<em>{join_reason}</em></p>"
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
    """Pre-flight reminder sent at 8:00 AM IST — 30 min before the 8:30 AM GTT job."""
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
    """Pre-flight reminder for Groww manual-mode users (no TOTP auto-refresh)."""
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
      <p style="color:#64748b;font-size:0.82em;margin-top:16px;">
        <strong>Tip:</strong> Enable TOTP auto-refresh in your Broker Automation Setup
        to never need to reconnect manually again.
      </p>
    </body></html>
    """
    _send(user_email, "Action required: Reconnect Groww before 8:30 AM IST — GTT job in 30 min", html)


def notify_user_rejected(user_email: str, name: str, reason: str = ""):
    reason_html = (
        f"<p><strong>Reason:</strong> {reason}</p>"
    ) if reason else ""
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
