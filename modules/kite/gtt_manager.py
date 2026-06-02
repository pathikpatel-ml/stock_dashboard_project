import math

from kiteconnect import KiteConnect


def get_existing_gtt_symbols(kite) -> set:
    """Return set of tradingsymbols that already have an active GTT."""
    try:
        gtts = kite.get_gtts()
        return {g["condition"]["tradingsymbol"] for g in gtts
                if g.get("status") in ("active", "triggered")}
    except Exception:
        return set()


def build_candidates(v20_df, breakout_df, proximity_threshold_pct: float) -> list:
    """
    Return list of dicts: {symbol, buy_price, strategy, current_ltp}
    Only includes signals where the stock is within proximity_threshold_pct of its buy target.
    """
    candidates = []

    # V20 signals — buy when LTP drops to "Target Buy Price (Low)"
    if v20_df is not None and not v20_df.empty:
        for _, row in v20_df.iterrows():
            try:
                proximity = abs(float(row.get("Proximity to Buy (%)", 999)))
                buy_price = float(row.get("Target Buy Price (Low)", 0))
                ltp = float(row.get("Latest Close Price", 0))
                if proximity <= proximity_threshold_pct and buy_price > 0 and ltp > 0:
                    candidates.append({
                        "symbol": str(row["Symbol"]).strip(),
                        "buy_price": round(buy_price, 2),
                        "strategy": "v20",
                        "current_ltp": round(ltp, 2),
                    })
            except (ValueError, KeyError, TypeError):
                continue

    # Breakout watchlist — buy when LTP reaches Entry_Price (currently below it)
    if breakout_df is not None and not breakout_df.empty:
        for _, row in breakout_df.iterrows():
            try:
                entry = float(row.get("Entry_Price", 0))
                cmp = float(row.get("CMP", 0))
                if entry <= 0 or cmp <= 0:
                    continue
                prox_pct = (cmp - entry) / entry * 100  # negative = below entry
                # Only watchlist entries where CMP is slightly below the breakout entry
                if -proximity_threshold_pct <= prox_pct <= 0:
                    candidates.append({
                        "symbol": str(row["Symbol"]).strip(),
                        "buy_price": round(entry, 2),
                        "strategy": "breakout",
                        "current_ltp": round(cmp, 2),
                    })
            except (ValueError, KeyError, TypeError):
                continue

    return candidates


def place_buy_gtt(kite, symbol: str, buy_price: float,
                  quantity: int, current_ltp: float) -> int:
    """Place a single-leg GTT buy order. Returns the Kite trigger_id."""
    resp = kite.place_gtt(
        trigger_type=KiteConnect.GTT_TYPE_SINGLE,
        tradingsymbol=symbol,
        exchange="NSE",
        trigger_values=[buy_price],
        last_price=current_ltp,
        orders=[{
            "transaction_type": KiteConnect.TRANSACTION_TYPE_BUY,
            "quantity": quantity,
            "product": KiteConnect.PRODUCT_CNC,
            "order_type": KiteConnect.ORDER_TYPE_LIMIT,
            "price": buy_price,
        }],
    )
    return resp["trigger_id"]


def calculate_quantity(portfolio_value: float, allocation_pct: float,
                       buy_price: float) -> int:
    """Return max shares to buy given allocation constraints."""
    if buy_price <= 0:
        return 0
    max_value = portfolio_value * (allocation_pct / 100.0)
    return math.floor(max_value / buy_price)
