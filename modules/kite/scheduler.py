import logging
import os
import smtplib
import traceback
from datetime import date, datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apscheduler.schedulers.background import BackgroundScheduler

from modules.auth import user_store
from modules.auth.crypto import decrypt
from modules.kite import auth as kite_auth
from modules.kite import gtt_manager, portfolio

logger = logging.getLogger(__name__)


def _send_reauth_email(to_email: str):
    """
    Send a Kite token-expired alert via Gmail SMTP.

    Required env vars:
        NOTIFY_EMAIL          — Gmail address that sends the alert (e.g. yourname@gmail.com)
        NOTIFY_EMAIL_PASSWORD — Gmail App Password (16-char, not your regular password)
                                Generate at: myaccount.google.com → Security → App Passwords
    """
    sender = os.environ.get("NOTIFY_EMAIL", "")
    password = os.environ.get("NOTIFY_EMAIL_PASSWORD", "")

    if not sender or not password:
        logger.warning(
            "NOTIFY_EMAIL or NOTIFY_EMAIL_PASSWORD not set — skipping email to %s.", to_email
        )
        return

    subject = "Action Required: Reconnect Zerodha before market open"
    html_body = f"""
    <html><body style="font-family: Arial, sans-serif; color: #1e293b;">
      <h2 style="color:#ef4444;">Kite Access Token Expired</h2>
      <p>Your Zerodha Kite access token has expired (tokens reset every day at 6 AM IST).</p>
      <p>The pre-market GTT job could <strong>not create orders</strong> today because
         no valid token was found.</p>
      <h3>What to do:</h3>
      <ol>
        <li>Open your <a href="https://stock-dashboard-project.onrender.com">Stock Dashboard</a></li>
        <li>Go to the <strong>Zerodha Settings</strong> tab</li>
        <li>Click <strong>Connect Zerodha</strong> and log in with your Kite User ID</li>
        <li>You will be redirected back automatically — token is saved</li>
      </ol>
      <p style="color:#64748b; font-size:0.85em;">
        Please reconnect <strong>before 8:00 AM IST</strong> so tomorrow's GTT job runs successfully.
      </p>
    </body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())

        logger.info("Reauth email sent to %s.", to_email)
    except Exception as exc:
        logger.error("Failed to send reauth email to %s: %s", to_email, exc)


def run_premarket_gtt_job() -> dict:
    """
    Runs daily before market open (03:00 UTC = 08:30 IST, Mon-Fri).
    Returns {"logs": [...], "success": bool, "token_expired": bool}
    success=False when a token is expired — causes the GitHub Action to fail
    and send an automatic email notification.
    """
    import data_manager  # avoid circular import at module load

    logs = []
    token_expired = False

    def log(msg: str, level: str = "info"):
        logger.info(msg) if level == "info" else logger.error(msg)
        logs.append(msg)

    log(f"GTT job started at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # ── 1. Load users ────────────────────────────────────────────────────────
    try:
        users = user_store.get_all_gtt_enabled_users()
    except Exception as exc:
        log(f"ERROR fetching users from DB: {exc}", "error")
        log(traceback.format_exc(), "error")
        return {"logs": logs, "success": False, "token_expired": False}

    if not users:
        log("No users with GTT enabled and a connected Kite account.")
        return {"logs": logs, "success": True, "token_expired": False}
    log(f"Found {len(users)} user(s) with GTT enabled.")

    # ── 2. Load today's signals ──────────────────────────────────────────────
    v20_df = data_manager.v20_processed_df
    breakout_df = data_manager.breakout_signals_df
    v20_count = 0 if v20_df is None or v20_df.empty else len(v20_df)
    brk_count = 0 if breakout_df is None or breakout_df.empty else len(breakout_df)
    log(f"Signals loaded — V20: {v20_count} rows, Breakout: {brk_count} rows.")

    today = date.today()

    for user in users:
        user_id = user["id"]
        email = user["email"]
        # Email stays in server log only, not in browser-visible output
        logger.info("Processing GTT for user %s (id=%s)", email, user_id)
        log(f"--- Processing user (id={user_id}) ---")

        # ── 3. Token check ───────────────────────────────────────────────────
        token_set_at = user.get("access_token_set_at")
        if not portfolio.is_token_valid(token_set_at):
            log(f"  TOKEN_EXPIRED: Kite token not connected today — please reconnect before 8:30 AM IST.", "error")
            token_expired = True
            _send_reauth_email(email)
            continue
        log("  Token valid [OK]")

        # ── 4. Build Kite client ─────────────────────────────────────────────
        try:
            kite = kite_auth.build_authenticated_client(
                user["api_key_enc"], user["access_token_enc"]
            )
            log("  Kite client built [OK]")
        except Exception as exc:
            log(f"  ERROR building Kite client: {exc}", "error")
            _send_reauth_email(email)
            continue

        # ── 5. Portfolio value ───────────────────────────────────────────────
        try:
            portfolio_value = portfolio.get_portfolio_value(kite)
            # Portfolio value is financial data — keep it in server log only
            logger.info("Portfolio value for user %s: Rs.%.0f", email, portfolio_value)
            log("  Portfolio loaded [OK]")
        except Exception as exc:
            log(f"  ERROR fetching portfolio: {exc}", "error")
            _send_reauth_email(email)
            continue

        if portfolio_value <= 0:
            log("  WARN: Portfolio value is zero — skipping GTT creation.")
            continue

        # ── 6. GTT candidates ────────────────────────────────────────────────
        settings = user_store.get_kite_settings(user_id)
        proximity_pct = settings.get("proximity_threshold_pct", 2.0)
        allocation_pct = settings.get("max_allocation_pct", 3.0)
        log(f"  Proximity threshold: {proximity_pct}% | Max allocation: {allocation_pct}%")

        exclusions = set(user_store.get_exclusions(user_id))
        if exclusions:
            log(f"  Excluded symbols: {', '.join(sorted(exclusions))}")

        try:
            candidates = gtt_manager.build_candidates(v20_df, breakout_df, proximity_pct,
                                                       excluded_symbols=exclusions)
        except Exception as exc:
            log(f"  ERROR building candidates: {exc}", "error")
            continue

        log(f"  Candidates within threshold (bullish signals only): {len(candidates)}")
        for c in candidates:
            log(f"    -> {c['symbol']} ({c['strategy']}) signal={c.get('signal_strength','?')} buy@Rs.{c['buy_price']}")
        if not candidates:
            log("  No signals close enough to buy target — nothing to do.")
            continue

        # ── 7. Existing GTTs ─────────────────────────────────────────────────
        try:
            existing_symbols = gtt_manager.get_existing_gtt_symbols(kite)
            log(f"  Existing GTT symbols: {existing_symbols or 'none'}")
        except Exception as exc:
            log(f"  ERROR fetching existing GTTs: {exc}", "error")
            existing_symbols = set()

        # ── 8. Place GTTs ────────────────────────────────────────────────────
        for c in candidates:
            symbol = c["symbol"]

            if symbol in existing_symbols:
                user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                          None, "skipped_exists", None)
                log(f"  [{symbol}] skipped — GTT already exists.")
                continue

            qty = gtt_manager.calculate_quantity(portfolio_value, allocation_pct, c["buy_price"])
            if qty < 1:
                note = f"Rs.{portfolio_value:.0f} x {allocation_pct}% / Rs.{c['buy_price']} < 1 share"
                user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                          None, "skipped_low_qty", note)
                log(f"  [{symbol}] skipped — qty < 1 ({note}).")
                continue

            try:
                gtt_id = gtt_manager.place_buy_gtt(kite, symbol, c["buy_price"],
                                                    qty, c["current_ltp"])
                user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                          gtt_id, "created", None)
                log(f"  [{symbol}] GTT CREATED [OK] id={gtt_id} qty={qty} @Rs.{c['buy_price']}")
                existing_symbols.add(symbol)
            except Exception as exc:
                user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                          None, "failed", str(exc))
                log(f"  [{symbol}] ERROR: {exc}", "error")

    log("GTT job finished.")
    return {"logs": logs, "success": not token_expired, "token_expired": token_expired}


def create_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    # 08:30 IST = 03:00 UTC, Mon–Fri only
    sched.add_job(
        run_premarket_gtt_job,
        trigger="cron",
        hour=3,
        minute=0,
        day_of_week="mon-fri",
        id="premarket_gtt",
        replace_existing=True,
    )
    return sched
