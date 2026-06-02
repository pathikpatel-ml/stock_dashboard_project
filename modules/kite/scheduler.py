import logging
from datetime import date, datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from modules.auth import user_store
from modules.auth.crypto import decrypt
from modules.kite import auth as kite_auth
from modules.kite import gtt_manager, portfolio

logger = logging.getLogger(__name__)


def _send_reauth_notification(email: str):
    """Send email asking the user to reconnect their Kite session."""
    try:
        from modules.notification_engine import get_notification_engine, NotificationChannel
        engine = get_notification_engine()
        engine.send_notification(
            title="Kite Token Expired — Action Required",
            message=(
                "Your Zerodha Kite access token has expired. "
                "Please log in to the Stock Dashboard and reconnect your Zerodha account "
                "so GTT orders can be created before market open tomorrow."
            ),
            channel=NotificationChannel.EMAIL,
            recipient=email,
        )
    except Exception as exc:
        logger.warning("Could not send reauth notification to %s: %s", email, exc)


def run_premarket_gtt_job():
    """
    Runs daily before market open (scheduled at 03:00 UTC = 08:30 IST).
    For every user with GTT enabled and a valid access token, creates buy GTTs
    for signals within their proximity threshold, capped at their max allocation %.
    """
    import data_manager  # import here to avoid circular imports at module load

    logger.info("Pre-market GTT job started at %s UTC", datetime.now(timezone.utc))

    users = user_store.get_all_gtt_enabled_users()
    if not users:
        logger.info("No users with GTT enabled. Skipping.")
        return

    v20_df = data_manager.v20_processed_df
    breakout_df = data_manager.breakout_signals_df
    today = date.today()

    for user in users:
        user_id = user["id"]
        email = user["email"]
        logger.info("Processing GTT for user %s (id=%s)", email, user_id)

        # 1. Validate token freshness
        if not portfolio.is_token_valid(user.get("access_token_set_at")):
            logger.warning("Token expired for user %s — sending reauth notification.", email)
            _send_reauth_notification(email)
            continue

        # 2. Build authenticated Kite client
        try:
            kite = kite_auth.build_authenticated_client(
                user["api_key_enc"], user["access_token_enc"]
            )
        except Exception as exc:
            logger.error("Failed to build Kite client for %s: %s", email, exc)
            _send_reauth_notification(email)
            continue

        # 3. Get portfolio value
        try:
            portfolio_value = portfolio.get_portfolio_value(kite)
        except Exception as exc:
            logger.error("Failed to fetch portfolio for %s: %s", email, exc)
            _send_reauth_notification(email)
            continue

        if portfolio_value <= 0:
            logger.warning("Portfolio value is 0 for user %s — skipping.", email)
            continue

        # 4. Build GTT candidates from today's signals
        settings = user_store.get_kite_settings(user_id)
        proximity_pct = settings.get("proximity_threshold_pct", 2.0)
        allocation_pct = settings.get("max_allocation_pct", 3.0)

        candidates = gtt_manager.build_candidates(v20_df, breakout_df, proximity_pct)
        if not candidates:
            logger.info("No signals within proximity threshold for user %s.", email)
            continue

        # 5. Get existing GTT symbols to avoid duplicates
        existing_symbols = gtt_manager.get_existing_gtt_symbols(kite)

        for candidate in candidates:
            symbol = candidate["symbol"]

            if symbol in existing_symbols:
                user_store.insert_gtt_log(
                    user_id, today, symbol, candidate["strategy"],
                    None, "skipped_exists", None
                )
                logger.info("  [%s] skipped — GTT already exists.", symbol)
                continue

            qty = gtt_manager.calculate_quantity(
                portfolio_value, allocation_pct, candidate["buy_price"]
            )
            if qty < 1:
                user_store.insert_gtt_log(
                    user_id, today, symbol, candidate["strategy"],
                    None, "skipped_low_qty",
                    f"portfolio={portfolio_value:.0f}, alloc={allocation_pct}%, price={candidate['buy_price']}"
                )
                logger.info("  [%s] skipped — quantity < 1.", symbol)
                continue

            try:
                gtt_id = gtt_manager.place_buy_gtt(
                    kite,
                    symbol,
                    candidate["buy_price"],
                    qty,
                    candidate["current_ltp"],
                )
                user_store.insert_gtt_log(
                    user_id, today, symbol, candidate["strategy"],
                    gtt_id, "created", None
                )
                logger.info("  [%s] GTT created (id=%s, qty=%s, price=%s).",
                            symbol, gtt_id, qty, candidate["buy_price"])
                existing_symbols.add(symbol)  # prevent duplicate within same run
            except Exception as exc:
                user_store.insert_gtt_log(
                    user_id, today, symbol, candidate["strategy"],
                    None, "failed", str(exc)
                )
                logger.error("  [%s] GTT creation failed: %s", symbol, exc)

    logger.info("Pre-market GTT job completed.")


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
