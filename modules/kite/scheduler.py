import logging
import os
import traceback
from datetime import date, datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from modules.auth import user_store
from modules.auth.crypto import decrypt, encrypt
from modules.kite import auth as kite_auth
from modules.kite import gtt_manager, portfolio
from modules.auth.notifications import notify_user_gtt_reminder, notify_user_gtt_reminder_groww

logger = logging.getLogger(__name__)


def run_premarket_gtt_job() -> dict:
    """
    Runs daily before market open (03:00 UTC = 08:30 IST, Mon-Fri).
    Processes both Zerodha and Groww users.

    REFRESH MODE (new day): deletes all previous automation GTTs, creates fresh ones.
    ADD MODE (same-day rerun): skips existing symbols, only adds new ones.

    Returns {"logs": [...], "success": bool, "token_expired": bool}
    """
    import data_manager  # avoid circular import at module load

    logs = []
    token_expired = False

    def log(msg: str, level: str = "info"):
        logger.info(msg) if level == "info" else logger.error(msg)
        logs.append(msg)

    log(f"GTT job started at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # ── Load today's signals (shared across brokers) ─────────────────────
    v20_df = data_manager.v20_processed_df
    breakout_df = data_manager.breakout_signals_df
    v20_count = 0 if v20_df is None or v20_df.empty else len(v20_df)
    brk_count = 0 if breakout_df is None or breakout_df.empty else len(breakout_df)
    log(f"Signals loaded — V20: {v20_count} rows, Breakout: {brk_count} rows.")

    today = date.today()

    # ── Zerodha users ─────────────────────────────────────────────────────
    try:
        zerodha_users = user_store.get_all_gtt_enabled_users()
    except Exception as exc:
        log(f"ERROR fetching Zerodha users: {exc}", "error")
        zerodha_users = []

    log(f"Zerodha: {len(zerodha_users)} user(s) with GTT enabled." if zerodha_users
        else "Zerodha: no users with GTT enabled.")

    for user in zerodha_users:
        if _process_zerodha_user(user, v20_df, breakout_df, today, logs):
            token_expired = True

    # ── Groww users ───────────────────────────────────────────────────────
    try:
        groww_users = user_store.get_all_groww_gtt_enabled_users()
    except Exception as exc:
        log(f"ERROR fetching Groww users: {exc}", "error")
        groww_users = []

    log(f"Groww: {len(groww_users)} user(s) with GTT enabled." if groww_users
        else "Groww: no users with GTT enabled.")

    for user in groww_users:
        if _process_groww_user(user, v20_df, breakout_df, today, logs):
            token_expired = True

    log("GTT job finished.")
    return {"logs": logs, "success": not token_expired, "token_expired": token_expired}


# ── Shared refresh helper ─────────────────────────────────────────────────────

def _delete_previous_gtts(user_id: int, broker: str, today, delete_fn, log):
    """
    Deletes all GTT/Smart Orders we created on previous days.
    delete_fn(gtt_id) → True (deleted) | False (already gone/triggered) | raises
    Logs every outcome and returns (deleted_count, skipped_count).
    """
    prev = user_store.get_previous_gtt_ids(user_id, broker=broker)
    if not prev:
        log("  No previous GTTs to clean up.")
        return 0, 0

    log(f"  Deleting {len(prev)} previous GTT(s) for clean-slate refresh...")
    deleted, skipped = 0, 0
    for row in prev:
        gtt_id = row["gtt_id"]
        symbol = row.get("symbol", "?")
        strategy = row.get("strategy", "refresh")
        try:
            success = delete_fn(gtt_id)
            if success:
                deleted += 1
                user_store.insert_gtt_log(user_id, today, symbol, strategy,
                                          gtt_id, "deleted_refresh", None, broker=broker)
                log(f"    [{symbol}] deleted (id={gtt_id})")
            else:
                skipped += 1
                log(f"    [{symbol}] id={gtt_id} already triggered/gone — skipped")
        except Exception as exc:
            log(f"    [{symbol}] ERROR deleting id={gtt_id}: {exc}", "error")

    log(f"  Cleanup done — deleted={deleted}, already_gone={skipped}")
    return deleted, skipped


# ── Zerodha ───────────────────────────────────────────────────────────────────

def _process_zerodha_user(user: dict, v20_df, breakout_df, today, logs) -> bool:
    """Process one Zerodha user. Returns True if token was expired."""
    user_id = user["id"]
    email = user["email"]
    logger.info("Processing Zerodha GTT for user %s (id=%s)", email, user_id)
    logs.append(f"--- [Zerodha] user id={user_id} ---")

    def log(msg: str, level: str = "info"):
        logger.info(msg) if level == "info" else logger.error(msg)
        logs.append(msg)

    # ── Token check ──────────────────────────────────────────────────────
    if not portfolio.is_token_valid(user.get("access_token_set_at")):
        log("  TOKEN_EXPIRED: Zerodha token not valid today.", "error")
        notify_user_gtt_reminder(email)
        return True
    log("  Token valid [OK]")

    # ── Build client ─────────────────────────────────────────────────────
    try:
        kite = kite_auth.build_authenticated_client(
            user["api_key_enc"], user["access_token_enc"]
        )
        log("  Kite client built [OK]")
    except Exception as exc:
        log(f"  ERROR building Kite client: {exc}", "error")
        notify_user_gtt_reminder(email)
        return False

    # ── Portfolio ────────────────────────────────────────────────────────
    try:
        portfolio_value = portfolio.get_portfolio_value(kite)
        logger.info("Zerodha portfolio for user %s: Rs.%.0f", email, portfolio_value)
        log("  Portfolio loaded [OK]")
    except Exception as exc:
        log(f"  ERROR fetching portfolio: {exc}", "error")
        return False

    if portfolio_value <= 0:
        log("  WARN: Portfolio is zero — skipping.")
        return False

    # ── Settings & exclusions ────────────────────────────────────────────
    settings = user_store.get_kite_settings(user_id)
    proximity_pct = settings.get("proximity_threshold_pct", 2.0)
    allocation_pct = settings.get("max_allocation_pct", 3.0)
    exclusions = set(user_store.get_exclusions(user_id))
    log(f"  Proximity: {proximity_pct}% | Allocation: {allocation_pct}%")

    # ── REFRESH or ADD mode ──────────────────────────────────────────────
    last_run = user_store.get_last_gtt_run_date(user_id)
    refresh_mode = last_run is not None and str(last_run) < str(today)
    log(f"  Mode: {'REFRESH (new day, last run=' + str(last_run) + ')' if refresh_mode else 'ADD (same day or first run)'}")

    if refresh_mode:
        _delete_previous_gtts(
            user_id, "zerodha", today,
            delete_fn=lambda gtt_id: gtt_manager.delete_gtt(kite, gtt_id),
            log=log,
        )

    # ── Live existing GTTs (after cleanup) ───────────────────────────────
    try:
        existing_symbols = gtt_manager.get_existing_gtt_symbols(kite)
        log(f"  Live GTT symbols remaining: {existing_symbols or 'none'}")
    except Exception as exc:
        log(f"  ERROR fetching existing GTTs: {exc}", "error")
        existing_symbols = set()

    # ── Candidates ───────────────────────────────────────────────────────
    try:
        candidates = gtt_manager.build_candidates(
            v20_df, breakout_df, proximity_pct, excluded_symbols=exclusions
        )
    except Exception as exc:
        log(f"  ERROR building candidates: {exc}", "error")
        return False

    log(f"  Candidates within threshold: {len(candidates)}")
    for c in candidates:
        log(f"    -> {c['symbol']} ({c['strategy']}) signal={c.get('signal_strength','?')} buy@Rs.{c['buy_price']}")

    if not candidates:
        log("  No signals close enough — nothing to do.")
        return False

    # ── Place GTTs ────────────────────────────────────────────────────────
    for c in candidates:
        symbol = c["symbol"]
        if symbol in existing_symbols:
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      None, "skipped_exists", None, broker="zerodha")
            log(f"  [{symbol}] skipped — live GTT already exists (user-placed).")
            continue

        qty = gtt_manager.calculate_quantity(portfolio_value, allocation_pct, c["buy_price"])
        if qty < 1:
            note = f"Rs.{portfolio_value:.0f} x {allocation_pct}% / Rs.{c['buy_price']} < 1 share"
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      None, "skipped_low_qty", note, broker="zerodha")
            log(f"  [{symbol}] skipped — qty < 1 ({note}).")
            continue

        try:
            gtt_id = gtt_manager.place_buy_gtt(kite, symbol, c["buy_price"],
                                                qty, c["current_ltp"])
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      gtt_id, "created", None, broker="zerodha")
            log(f"  [{symbol}] GTT CREATED id={gtt_id} qty={qty} @Rs.{c['buy_price']}")
            existing_symbols.add(symbol)
        except Exception as exc:
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      None, "failed", str(exc), broker="zerodha")
            log(f"  [{symbol}] ERROR: {exc}", "error")

    return False


# ── Groww ─────────────────────────────────────────────────────────────────────

def _process_groww_user(user: dict, v20_df, breakout_df, today, logs) -> bool:
    """
    Process one Groww user.
    Auto-refreshes token via TOTP if expired. Returns True if token unavailable.
    """
    from modules.groww import auth as groww_auth, gtt_manager as groww_gtt, portfolio as groww_portfolio

    user_id = user["id"]
    email = user["email"]
    logger.info("Processing Groww GTT for user %s (id=%s)", email, user_id)
    logs.append(f"--- [Groww] user id={user_id} ---")

    def log(msg: str, level: str = "info"):
        logger.info(msg) if level == "info" else logger.error(msg)
        logs.append(msg)

    # ── TOTP auto-refresh if token expired ───────────────────────────────
    is_auto = user.get("totp_auto_refresh", False) and user.get("totp_secret_enc")
    token_valid = groww_portfolio.is_token_valid(user.get("access_token_set_at"))

    if not token_valid:
        if is_auto:
            try:
                log("  Token expired — attempting TOTP auto-refresh...")
                new_token = groww_auth.auto_refresh_token(
                    user["app_id_enc"], user["totp_secret_enc"]
                )
                user_store.upsert_groww_settings(
                    user_id,
                    access_token_enc=encrypt(new_token),
                    access_token_set_at=datetime.now(timezone.utc),
                )
                user["access_token_enc"] = encrypt(new_token)
                log("  Token auto-refreshed via TOTP [OK]")
            except Exception as exc:
                log(f"  TOTP auto-refresh failed: {exc}", "error")
                notify_user_gtt_reminder_groww(email)
                return True
        else:
            log("  TOKEN_EXPIRED: Groww token not valid today (manual mode).", "error")
            notify_user_gtt_reminder_groww(email)
            return True

    log("  Token valid [OK]")

    # ── Build client ─────────────────────────────────────────────────────
    try:
        groww = groww_auth.build_authenticated_client(
            user["app_id_enc"], user["access_token_enc"]
        )
        log("  Groww client built [OK]")
    except Exception as exc:
        log(f"  ERROR building Groww client: {exc}", "error")
        return False

    # ── Portfolio ────────────────────────────────────────────────────────
    try:
        portfolio_value = groww_portfolio.get_portfolio_value(groww)
        logger.info("Groww portfolio for user %s: Rs.%.0f", email, portfolio_value)
        log("  Portfolio loaded [OK]")
    except Exception as exc:
        log(f"  ERROR fetching portfolio: {exc}", "error")
        return False

    if portfolio_value <= 0:
        log("  WARN: Portfolio is zero — skipping.")
        return False

    # ── Settings & exclusions ────────────────────────────────────────────
    settings = user_store.get_groww_settings(user_id)
    proximity_pct = settings.get("proximity_threshold_pct", 2.0)
    allocation_pct = settings.get("max_allocation_pct", 3.0)
    exclusions = set(user_store.get_groww_exclusions(user_id))
    log(f"  Proximity: {proximity_pct}% | Allocation: {allocation_pct}%")

    # ── REFRESH or ADD mode ──────────────────────────────────────────────
    last_run = user_store.get_last_gtt_run_date(user_id)
    refresh_mode = last_run is not None and str(last_run) < str(today)
    log(f"  Mode: {'REFRESH (new day, last run=' + str(last_run) + ')' if refresh_mode else 'ADD (same day or first run)'}")

    if refresh_mode:
        _delete_previous_gtts(
            user_id, "groww", today,
            delete_fn=lambda oid: groww_gtt.cancel_smart_order_by_id(groww, oid),
            log=log,
        )

    # ── Live existing Smart Orders (after cleanup) ────────────────────────
    try:
        existing_symbols = groww_gtt.get_existing_smart_order_symbols(groww)
        log(f"  Live Smart Order symbols remaining: {existing_symbols or 'none'}")
    except Exception as exc:
        log(f"  ERROR fetching existing Smart Orders: {exc}", "error")
        existing_symbols = set()

    # ── Candidates ───────────────────────────────────────────────────────
    try:
        candidates = gtt_manager.build_candidates(
            v20_df, breakout_df, proximity_pct, excluded_symbols=exclusions
        )
    except Exception as exc:
        log(f"  ERROR building candidates: {exc}", "error")
        return False

    log(f"  Candidates within threshold: {len(candidates)}")
    if not candidates:
        log("  No signals close enough — nothing to do.")
        return False

    # ── Place Smart Orders ────────────────────────────────────────────────
    for c in candidates:
        symbol = c["symbol"]
        if symbol in existing_symbols:
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      None, "skipped_exists", None, broker="groww")
            log(f"  [{symbol}] skipped — live Smart Order already exists (user-placed).")
            continue

        qty = groww_gtt.calculate_quantity(portfolio_value, allocation_pct, c["buy_price"])
        if qty < 1:
            note = f"Rs.{portfolio_value:.0f} x {allocation_pct}% / Rs.{c['buy_price']} < 1 share"
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      None, "skipped_low_qty", note, broker="groww")
            log(f"  [{symbol}] skipped — qty < 1.")
            continue

        try:
            order_id = groww_gtt.place_buy_smart_order(
                groww, symbol, c["buy_price"], qty, c["current_ltp"]
            )
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      order_id, "created", None, broker="groww")
            log(f"  [{symbol}] SMART ORDER CREATED id={order_id} qty={qty} @Rs.{c['buy_price']}")
            existing_symbols.add(symbol)
        except Exception as exc:
            user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                      None, "failed", str(exc), broker="groww")
            log(f"  [{symbol}] ERROR: {exc}", "error")

    return False


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
