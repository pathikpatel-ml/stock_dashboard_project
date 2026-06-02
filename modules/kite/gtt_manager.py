import math
import logging

import pandas as pd
from kiteconnect import KiteConnect

logger = logging.getLogger(__name__)

# V20 signal strengths that warrant a GTT buy order
_BULLISH_SIGNALS = {"STRONG BUY", "BUY NOW", "BUY"}


def get_existing_gtt_symbols(kite) -> set:
    """Return set of tradingsymbols that already have an active GTT."""
    try:
        gtts = kite.get_gtts()
        return {g["condition"]["tradingsymbol"] for g in gtts
                if g.get("status") in ("active", "triggered")}
    except Exception:
        return set()


def _macd_is_bullish(symbol: str) -> bool:
    """
    Return True if the stock's MACD line is above the signal line (bullish).
    Uses 30 days of daily data — fast, only called for proximity-filtered stocks.
    Returns True on any error so we don't accidentally block valid signals.
    """
    try:
        import yfinance as yf
        ticker = symbol + ".NS"
        df = yf.download(ticker, period="60d", interval="1d",
                         progress=False, auto_adjust=True)
        if df is None or len(df) < 27:
            return True  # not enough data, allow through

        close = df["Close"].squeeze()
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()

        # Bullish = MACD line above signal line on the latest candle
        return float(macd_line.iloc[-1]) > float(signal_line.iloc[-1])
    except Exception as exc:
        logger.warning("MACD check failed for %s: %s — allowing through.", symbol, exc)
        return True


def build_candidates(v20_df, breakout_df, proximity_threshold_pct: float) -> list:
    """
    Return list of dicts: {symbol, buy_price, strategy, current_ltp, signal_strength}
    Only includes signals that are:
      - Within proximity_threshold_pct of the buy target
      - Have a bullish signal (BUY / BUY NOW / STRONG BUY) for V20
      - Or are breakout watchlist entries where CMP is just below entry
    """
    candidates = []

    # ── V20 signals ─────────────────────────────────────────────────────────
    if v20_df is not None and not v20_df.empty:
        signal_col = None
        for col in ("Signal_Strength", "signal_strength", "Signal Strength"):
            if col in v20_df.columns:
                signal_col = col
                break

        for _, row in v20_df.iterrows():
            try:
                proximity = abs(float(row.get("Proximity to Buy (%)", 999)))
                buy_price = float(row.get("Target Buy Price (Low)", 0))
                ltp = float(row.get("Latest Close Price", 0))
                symbol = str(row["Symbol"]).strip()

                if proximity > proximity_threshold_pct or buy_price <= 0 or ltp <= 0:
                    continue

                # ── Signal strength filter ────────────────────────────────
                if signal_col:
                    strength = str(row.get(signal_col, "")).strip().upper()
                    if strength and strength not in _BULLISH_SIGNALS:
                        logger.info("  [%s] skipped — signal is '%s', not bullish.", symbol, strength)
                        continue
                else:
                    # No signal column in df — check MACD directly
                    if not _macd_is_bullish(symbol):
                        logger.info("  [%s] skipped — MACD bearish.", symbol)
                        continue

                candidates.append({
                    "symbol": symbol,
                    "buy_price": round(buy_price, 2),
                    "strategy": "v20",
                    "current_ltp": round(ltp, 2),
                    "signal_strength": row.get(signal_col, "unknown") if signal_col else "macd_ok",
                })
            except (ValueError, KeyError, TypeError):
                continue

    # ── Breakout watchlist ───────────────────────────────────────────────────
    if breakout_df is not None and not breakout_df.empty:
        for _, row in breakout_df.iterrows():
            try:
                entry = float(row.get("Entry_Price", 0))
                cmp = float(row.get("CMP", 0))
                if entry <= 0 or cmp <= 0:
                    continue
                prox_pct = (cmp - entry) / entry * 100
                if -proximity_threshold_pct <= prox_pct <= 0:
                    candidates.append({
                        "symbol": str(row["Symbol"]).strip(),
                        "buy_price": round(entry, 2),
                        "strategy": "breakout",
                        "current_ltp": round(cmp, 2),
                        "signal_strength": "breakout",
                    })
            except (ValueError, KeyError, TypeError):
                continue

    return candidates


def place_buy_gtt(kite, symbol: str, buy_price: float,
                  quantity: int, current_ltp: float) -> int:
    """
    Place a single-leg GTT buy order.

    Kite validation rules:
      - last_price must be > trigger_value  (otherwise "trigger already met")
      - trigger_value must be at least 0.25% below last_price

    We pass last_price = max(current_ltp, buy_price * 1.005) to always
    satisfy both rules. This is a hint only — the real market trigger
    fires at buy_price regardless.
    """
    # Ensure last_price is at least 0.5% above trigger so Kite always accepts
    effective_last_price = max(current_ltp, round(buy_price * 1.005, 2))

    resp = kite.place_gtt(
        trigger_type=KiteConnect.GTT_TYPE_SINGLE,
        tradingsymbol=symbol,
        exchange="NSE",
        trigger_values=[buy_price],
        last_price=effective_last_price,
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
    if buy_price <= 0:
        return 0
    max_value = portfolio_value * (allocation_pct / 100.0)
    return math.floor(max_value / buy_price)
