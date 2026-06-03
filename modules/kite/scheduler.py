import logging
import traceback
from datetime import date, datetime, timezone, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from modules.auth import user_store
from modules.auth.crypto import decrypt
from modules.kite import auth as kite_auth
from modules.kite import gtt_manager, portfolio
from modules.notifications import notify_token_expired

logger = logging.getLogger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_MARKET_OPEN_MINUTES = 9 * 60 + 15  # 9:15 AM IST in minutes from midnight


def _is_premarket_ist() -> bool:
    """True if current IST time is before 9:15 AM on a weekday."""
    now_ist = datetime.now(_IST)
    if now_ist.weekday() >= 5:  # Sat/Sun
        return False
    return (now_ist.hour * 60 + now_ist.minute) < _MARKET_OPEN_MINUTES


def _maybe_trigger_gtt_for_user(user_id: int) -> str | None:
    """
    Trigger GTT job for a single user in a background thread if:
    - gtt_enabled = True
    - Current IST time is before 9:15 AM (pre-market)
    - No GTT log entries exist for today
    Returns a status message if triggered, None otherwise.
    """
    import threading
    if not _is_premarket_ist():
        return None
    settings = user_store.get_kite_settings(user_id)
    if not settings.get("gtt_enabled"):
        return None
    if not settings.get("access_token_enc"):
        return None
    # Don't re-run if job already ran for this user today
    if user_store.get_gtt_log_today(user_id):
        return None
    logger.info("Auto-triggering GTT job for user_id=%s after token reconnect", user_id)
    threading.Thread(
        target=run_premarket_gtt_job,
        kwargs={"user_ids": [user_id]},
        daemon=True,
    ).start()
    return "GTT orders are being placed for today's signals. Check Activity Log in ~30s."


def run_premarket_gtt_job(user_ids: list | None = None) -> dict:
    """
    Runs daily before market open.
    user_ids: if provided, only process those user IDs (for targeted re-runs).
    Returns {"logs": [...], "success": bool, "token_expired": bool}
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

    if user_ids is not None:
        users = [u for u in users if u["id"] in set(user_ids)]
        log(f"Filtered to {len(users)} user(s) by user_ids={user_ids}.")

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
            log(f"  TOKEN_EXPIRED: Kite token not connected today — please reconnect before 8 AM IST.", "error")
            token_expired = True
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
            notify_token_expired(email)
            continue

        # ── 5. Portfolio value ───────────────────────────────────────────────
        try:
            portfolio_value = portfolio.get_portfolio_value(kite)
            # Portfolio value is financial data — keep it in server log only
            logger.info("Portfolio value for user %s: Rs.%.0f", email, portfolio_value)
            log("  Portfolio loaded [OK]")
        except Exception as exc:
            log(f"  ERROR fetching portfolio: {exc}", "error")
            notify_token_expired(email)
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


def _schedule_to_utc(schedule_time: str) -> tuple:
    """Convert 'HH:MM' IST string to (hour_utc, minute_utc)."""
    try:
        h, m = map(int, schedule_time.split(":"))
    except Exception:
        h, m = 8, 30  # default
    # IST = UTC + 5:30
    total_minutes = h * 60 + m - 330  # subtract 5h30m
    total_minutes = total_minutes % (24 * 60)  # wrap at midnight
    return total_minutes // 60, total_minutes % 60


def reschedule_user(sched: BackgroundScheduler, user_id: int, schedule_time: str):
    """Add or update a per-user GTT job in the scheduler."""
    job_id = f"gtt_user_{user_id}"
    hour_utc, minute_utc = _schedule_to_utc(schedule_time)
    try:
        sched.reschedule_job(
            job_id,
            trigger="cron",
            hour=hour_utc,
            minute=minute_utc,
            day_of_week="mon-fri",
        )
        logger.info("Rescheduled job %s → %02d:%02d UTC", job_id, hour_utc, minute_utc)
    except Exception:
        # Job doesn't exist yet — add it
        sched.add_job(
            run_premarket_gtt_job,
            trigger="cron",
            hour=hour_utc,
            minute=minute_utc,
            day_of_week="mon-fri",
            id=job_id,
            kwargs={"user_ids": [user_id]},
            replace_existing=True,
        )
        logger.info("Registered new job %s → %02d:%02d UTC", job_id, hour_utc, minute_utc)


def rebuild_user_schedules(sched: BackgroundScheduler):
    """
    Called on app startup to reconstruct per-user APScheduler jobs from DB.
    Replaces the old global 'premarket_gtt' job.
    """
    try:
        users = user_store.get_all_gtt_enabled_users()
    except Exception as exc:
        logger.warning("rebuild_user_schedules: could not fetch users: %s", exc)
        return
    for user in users:
        reschedule_user(sched, user["id"], user.get("schedule_time", "08:30"))
    logger.info("rebuild_user_schedules: registered %d user job(s).", len(users))


def create_scheduler() -> BackgroundScheduler:
    """Create the background scheduler. Per-user jobs are registered by rebuild_user_schedules."""
    sched = BackgroundScheduler(timezone="UTC")
    return sched
