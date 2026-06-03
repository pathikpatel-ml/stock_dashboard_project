"""
Shared async email notification helpers.
All sends are fire-and-forget daemon threads — callers are never blocked.
Requires env vars: NOTIFY_EMAIL, NOTIFY_EMAIL_PASSWORD, ADMIN_EMAIL, APP_URL
"""
import logging
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_APP_URL_DEFAULT = "https://stock-dashboard-project.onrender.com"


def _app_url() -> str:
    return os.environ.get("APP_URL", _APP_URL_DEFAULT).rstrip("/")


def _smtp_send(to_email: str, subject: str, html_body: str):
    sender = os.environ.get("NOTIFY_EMAIL", "")
    password = os.environ.get("NOTIFY_EMAIL_PASSWORD", "")
    if not sender or not password:
        logger.warning("NOTIFY_EMAIL/NOTIFY_EMAIL_PASSWORD not set — skipping email to %s", to_email)
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(sender, password)
            srv.sendmail(sender, to_email, msg.as_string())
        logger.info("Email sent to %s — %s", to_email, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)


def send_email_async(to_email: str, subject: str, html_body: str):
    """Send email in a background daemon thread. Never blocks the caller."""
    threading.Thread(
        target=_smtp_send, args=(to_email, subject, html_body), daemon=True
    ).start()


# ---------------------------------------------------------------------------
# Specific notification templates
# ---------------------------------------------------------------------------

def notify_admin_new_signup(name: str, email: str):
    """Email ADMIN_EMAIL when a new user submits a signup request."""
    admin_email = os.environ.get("ADMIN_EMAIL", "pathikc129@gmail.com")
    url = _app_url()
    subject = f"New access request: {name} ({email})"
    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;max-width:520px;">
      <h2 style="color:#3b82f6;">New Signup Request</h2>
      <table style="border-collapse:collapse;width:100%;margin-bottom:1.5rem;">
        <tr><td style="padding:6px 0;color:#64748b;width:100px">Name</td>
            <td style="padding:6px 0;font-weight:600">{name}</td></tr>
        <tr><td style="padding:6px 0;color:#64748b">Email</td>
            <td style="padding:6px 0">{email}</td></tr>
      </table>
      <a href="{url}/?tab=admin"
         style="background:#3b82f6;color:white;padding:10px 22px;text-decoration:none;
                border-radius:6px;font-weight:600;display:inline-block;">
        Review in Admin Panel →
      </a>
      <p style="color:#94a3b8;font-size:0.82em;margin-top:1.5rem;">
        Log in to your dashboard, open the Admin tab, then approve or reject this request.
      </p>
    </body></html>
    """
    send_email_async(admin_email, subject, body)


def notify_token_expired(user_email: str):
    """Email a user whose Kite access token has expired before the GTT job ran."""
    url = _app_url()
    subject = "Action Required: Reconnect Zerodha before 9:15 AM IST"
    body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;max-width:520px;">
      <h2 style="color:#ef4444;">Kite Access Token Expired</h2>
      <p>Your Zerodha Kite access token has expired.<br>
         Tokens are reset every day at 6 AM IST — this is a Zerodha limitation.</p>
      <p>The pre-market GTT job <strong>could not create orders today</strong>.</p>

      <div style="background:#fef9c3;border-left:4px solid #f59e0b;padding:12px 16px;
                  border-radius:0 6px 6px 0;margin:1.2rem 0;">
        <strong>Reconnect before 9:15 AM IST</strong> and your GTT orders will be placed
        automatically — no further action needed.
      </div>

      <h3 style="margin-top:1.5rem;">How to reconnect:</h3>
      <ol style="line-height:1.8">
        <li>Open your <a href="{url}" style="color:#3b82f6">Stock Dashboard</a></li>
        <li>Go to the <strong>Zerodha Settings</strong> tab</li>
        <li>Click <strong>Connect Zerodha</strong> and log in with your Kite User ID</li>
        <li>You'll be redirected back automatically — token is saved</li>
      </ol>

      <p style="color:#64748b;font-size:0.85em;margin-top:1.5rem;">
        After 9:15 AM IST, the market has opened and automatic GTT placement is no longer
        possible for today. You can still place orders manually in Zerodha Kite.
      </p>
    </body></html>
    """
    send_email_async(user_email, subject, body)
