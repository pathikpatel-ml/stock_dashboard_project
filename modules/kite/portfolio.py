from datetime import datetime, timezone, timedelta


def get_portfolio_value(kite) -> float:
    """Return total equity portfolio value from Kite holdings."""
    holdings = kite.holdings()
    return sum(h.get("last_price", 0) * h.get("quantity", 0) for h in holdings)


def is_token_valid(access_token_set_at) -> bool:
    """Kite access tokens expire at approximately 06:00 IST (00:30 UTC) every day."""
    if access_token_set_at is None:
        return False
    now_utc = datetime.now(timezone.utc)
    # Make offset-aware if naive
    if access_token_set_at.tzinfo is None:
        access_token_set_at = access_token_set_at.replace(tzinfo=timezone.utc)
    # Token set date
    set_date = access_token_set_at.date()
    today = now_utc.date()
    if set_date < today:
        return False
    # Also check if today's expiry (00:30 UTC) has passed
    todays_expiry = datetime(today.year, today.month, today.day, 0, 30, tzinfo=timezone.utc)
    if now_utc > todays_expiry and access_token_set_at < todays_expiry:
        return False
    return True
