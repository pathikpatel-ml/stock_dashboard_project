import logging
import os
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

_DASHBOARD_URL = "https://stock-dashboard-project.onrender.com"


def _send(to_email: str, subject: str, html_body: str):
    sender = os.environ.get("NOTIFY_EMAIL", "")
    password = os.environ.get("NOTIFY_EMAIL_PASSWORD", "")
    if not sender or not password:
        logger.warning(
            "NOTIFY_EMAIL / NOTIFY_EMAIL_PASSWORD not set — skipping email to %s (%s)",
            to_email, subject,
        )
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        # Force IPv4 — Render free-tier containers have no IPv6 routing.
        # smtplib tries IPv6 first (ENETUNREACH) and doesn't fall back to IPv4.
        smtp_ip = socket.getaddrinfo("smtp.gmail.com", 587, socket.AF_INET)[0][4][0]
        with smtplib.SMTP(smtp_ip, 587, timeout=15) as srv:
            srv.ehlo("smtp.gmail.com")
            srv.starttls()
            srv.login(sender, password)
            srv.sendmail(sender, to_email, msg.as_string())
        logger.warning("EMAIL SENT to %s: %s", to_email, subject)
    except Exception as exc:
        logger.error("Failed to send notification to %s: %s", to_email, exc)


def notify_admin_new_signup(admin_email: str, name: str, user_email: str,
                             join_reason: str = ""):
    reason_html = (
        f"<p><strong>Reason for joining:</strong><br>"
        f"<em>{join_reason}</em></p>"
    ) if join_reason else ""
    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#1e293b;padding:20px;">
      <h2 style="color:#3b82f6;">&#128276; New Access Request</h2>
      <p><strong>{name}</strong> (<a href="mailto:{user_email}">{user_email}</a>)
         has requested access to the Stock Signal Dashboard.</p>
      {reason_html}
      <p style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}" style="background:#3b82f6;color:white;
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
      <h2 style="color:#16a34a;">&#10003; Access Approved!</h2>
      <p>Hi {name},</p>
      <p>Your request to access the <strong>Stock Signal Dashboard</strong>
         has been <strong>approved</strong>. You can now log in.</p>
      <p style="margin-top:20px;">
        <a href="{_DASHBOARD_URL}" style="background:#16a34a;color:white;
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
