import logging
import traceback
from datetime import date, datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from modules.auth import user_store
from modules.auth.crypto import decrypt
from modules.kite import auth as kite_auth
from modules.kite import gtt_manager, portfolio

logger = logging.getLogger(__name__)


def _send_reauth_notification(email: str):
    try:
        from modules.notification_engine import get_notification_engine, NotificationChannel
        engine = get_notification_engine()
        engine.send_notification(
            title="Kite Token Expired — Action Required",
            message=(
                "Your Zerodha Kite access token has expired. "
                "Please reconnect your Zerodha account in the Stock Dashboard."
            ),
            channel=NotificationChannel.EMAIL,
            recipient=email,
        )
    except Exception as exc:
        logger.warning("Could not send reauth notification to %s: %s", email, exc)


def run_premarket_gtt_job() -> list[str]:
    """
    Runs daily before market open (03:00 UTC = 08:30 IST, Mon-Fri).
    Returns a list of human-readable log lines for UI display.
    """
    import data_manager  # avoid circular import at module load

    logs = []

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
        return logs

    if not users:
        log("No users with GTT enabled and a connected Kite account.")
        return logs
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
        log(f"--- Processing user: {email} ---")

        # ── 3. Token check ───────────────────────────────────────────────────
        token_set_at = user.get("access_token_set_at")
        log(f"  Token set at: {token_set_at}")
        if not portfolio.is_token_valid(token_set_at):
            log(f"  WARN: Token expired — skipping and sending notification.")
            _send_reauth_notification(email)
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
            _send_reauth_notification(email)
            continue

        # ── 5. Portfolio value ───────────────────────────────────────────────
        try:
            portfolio_value = portfolio.get_portfolio_value(kite)
            log(f"  Portfolio value: Rs.{portfolio_value:,.0f}")
        except Exception as exc:
            log(f"  ERROR fetching portfolio: {exc}", "error")
            _send_reauth_notification(email)
            continue

        if portfolio_value <= 0:
            log("  WARN: Portfolio value is ₹0 — skipping GTT creation.")
            continue

        # ── 6. GTT candidates ────────────────────────────────────────────────
        settings = user_store.get_kite_settings(user_id)
        proximity_pct = settings.get("proximity_threshold_pct", 2.0)
        allocation_pct = settings.get("max_allocation_pct", 3.0)
        log(f"  Proximity threshold: {proximity_pct}% | Max allocation: {allocation_pct}%")

        try:
            candidates = gtt_manager.build_candidates(v20_df, breakout_df, proximity_pct)
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
                err = str(exc).lower()
                if "trigger already met" in err or "already met" in err:
                    # Price is already at/below buy target — buy manually at market
                    user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                              None, "buy_at_market",
                                              f"Live price already at/below Rs.{c['buy_price']} — buy manually")
                    log(f"  [{symbol}] BUY NOW at market — price already at Rs.{c['buy_price']} target!")
                else:
                    user_store.insert_gtt_log(user_id, today, symbol, c["strategy"],
                                              None, "failed", str(exc))
                    log(f"  [{symbol}] ERROR: {exc}", "error")

    log("GTT job finished.")
    return logs


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
