from datetime import datetime, timezone


def get_portfolio_value(groww) -> float:
    """Return total equity portfolio value from Groww holdings."""
    try:
        holdings = groww.get_holdings()
        return sum(
            float(h.get("last_price", 0)) * float(h.get("quantity", 0))
            for h in holdings
        )
    except Exception:
        return 0.0


def is_token_valid(access_token_set_at) -> bool:
    """Groww tokens expire at 6:00 AM IST (00:30 UTC) daily — same window as Zerodha."""
    if access_token_set_at is None:
        return False
    if isinstance(access_token_set_at, str):
        try:
            access_token_set_at = datetime.fromisoformat(access_token_set_at)
        except ValueError:
            return False
    now_utc = datetime.now(timezone.utc)
    if access_token_set_at.tzinfo is None:
        access_token_set_at = access_token_set_at.replace(tzinfo=timezone.utc)
    set_date = access_token_set_at.date()
    today = now_utc.date()
    if set_date < today:
        return False
    todays_expiry = datetime(today.year, today.month, today.day, 0, 30, tzinfo=timezone.utc)
    if now_utc > todays_expiry and access_token_set_at < todays_expiry:
        return False
    return True
