import logging
import math

logger = logging.getLogger(__name__)


def get_existing_smart_order_symbols(groww) -> set:
    """Return set of tradingsymbols that already have an active Smart Order (Groww GTT)."""
    try:
        orders = groww.get_smart_orders()
        return {
            o.get("tradingsymbol", o.get("symbol", "")).upper()
            for o in orders
            if o.get("status", "").upper() in ("ACTIVE", "TRIGGERED", "PLACED", "PENDING")
        }
    except Exception:
        return set()


def place_buy_smart_order(groww, symbol: str, buy_price: float,
                          quantity: int, current_ltp: float) -> str:
    """
    Place a Groww Smart Order (GTT equivalent) buy order at buy_price.

    Two cases handled automatically:
    1. Price ABOVE target → trigger when price falls to buy_price (LTE condition)
    2. Price BELOW target → trigger when price rises back to buy_price (GTE condition)

    NOTE: Verify exact field names against growwapi SDK docs when activating real API.
    """
    trigger_condition = "LTE" if current_ltp >= buy_price else "GTE"

    result = groww.create_smart_order(
        exchange="NSE",
        tradingsymbol=symbol,
        trigger_type="GTT_SINGLE",
        trigger_price=buy_price,
        trigger_condition=trigger_condition,
        transaction_type="BUY",
        quantity=quantity,
        order_type="LIMIT",
        price=buy_price,
        product="CNC",
    )
    order_id = result.get("order_id") or result.get("smart_order_id") or str(result)
    return str(order_id)


def calculate_quantity(portfolio_value: float, allocation_pct: float,
                       buy_price: float) -> int:
    if buy_price <= 0:
        return 0
    max_value = portfolio_value * (allocation_pct / 100.0)
    return math.floor(max_value / buy_price)
