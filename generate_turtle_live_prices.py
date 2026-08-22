#!/usr/bin/env python
"""
Lightweight intraday price refresh for the Turtle Strategy tab.

generate_turtle_signals.py's full ADD/HOLD/EXIT classification needs ~2 years of daily
history per symbol (for 52-week relative strength and the ATH check) fetched one symbol at
a time -- that's why it takes 30-60 min and only runs once a day. But the *displayed price*
doesn't need any of that: it's one number, and Yahoo will hand back hundreds of them in a
single batched request. So this script is a separate, much cheaper job: BATCHED
``yf.download()`` calls (~100 tickers per request, same pattern as
``modules.stock_screener.add_moving_averages_to_stocks``) that only fetch the latest close,
meant to run several times during market hours to keep the on-screen price fresh between the
once-daily full recompute. The ADD/HOLD/EXIT signal itself, and the ATH/Above-MA200/RS flags
behind it, are intentionally left untouched here -- they depend on 52-week trends that don't
meaningfully change hour to hour, and re-deriving them would mean re-running the expensive
per-symbol pipeline this script exists to avoid.

Writes a single rolling ``turtle_live_prices.csv`` (Symbol, Live_Price, Price_As_Of), merged
with whatever was already cached so a symbol that fails this run keeps its last known-good
live price rather than reverting to the (older) daily-batch price. If a run fetches nothing
at all (e.g. Yahoo is unreachable), the existing cache is left untouched rather than wiped.

Usage
-----
    python generate_turtle_live_prices.py                # full universe
    python generate_turtle_live_prices.py --limit 100     # quick subset (testing)
"""
import argparse
import os
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")
LIVE_PRICES_FILE = os.path.join(REPO_BASE_PATH, "turtle_live_prices.csv")
BATCH_SIZE = 100

# CSV column name -> Postgres column name.
_LIVE_PRICES_DB_COLUMNS = {"Symbol": "symbol", "Live_Price": "live_price", "Price_As_Of": "price_as_of"}


def load_universe_symbols(universe_file: str = UNIVERSE_FILE) -> list:
    # nse_universe is produced by a separate, earlier-running weekly workflow -- Postgres is
    # the real cross-workflow hand-off now that its CSV isn't committed to git; the local file
    # read below is just a local-dev fallback (see generate_turtle_signals.py::_from_postgres).
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, "nse_universe")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres read of nse_universe failed, falling back to local CSV: {exc}")
        df = pd.DataFrame()

    if not df.empty:
        symbols = df["symbol"].dropna().astype(str).str.upper().str.strip().unique().tolist()
    else:
        if not os.path.exists(universe_file):
            raise SystemExit(
                f"Universe not found in Postgres (nse_universe) or at {universe_file}.\n"
                "Run the weekly stock screening first (generate_weekly_stock_list.py)."
            )
        df = pd.read_csv(universe_file, usecols=["Symbol"])
        symbols = df["Symbol"].dropna().astype(str).str.upper().str.strip().unique().tolist()
    return sorted(s for s in symbols if s)


def fetch_batch_prices(symbols: list, downloader=None) -> dict:
    """Batched ``yf.download`` for ``symbols`` -> ``{symbol: latest_close}``. Never raises."""
    if not symbols:
        return {}
    downloader = downloader or yf.download
    tickers = [f"{s}.NS" for s in symbols]
    try:
        data = downloader(
            tickers=tickers, period="2d", progress=False, auto_adjust=False,
            group_by="ticker", threads=True, timeout=30,
        )
    except Exception as exc:
        print(f"  batch fetch error ({len(symbols)} symbols): {exc}")
        return {}
    if data is None or data.empty:
        return {}

    prices = {}
    for symbol in symbols:
        ticker = f"{symbol}.NS"
        try:
            if isinstance(data.columns, pd.MultiIndex):
                if (ticker, "Close") not in data.columns:
                    continue
                close_series = data[(ticker, "Close")]
            elif len(symbols) == 1 and "Close" in data.columns:
                close_series = data["Close"]
            else:
                continue
            close_series = pd.to_numeric(close_series, errors="coerce").dropna()
            if not close_series.empty:
                prices[symbol] = float(close_series.iloc[-1])
        except Exception:
            continue
    return prices


def load_existing_cache(live_prices_file: str = LIVE_PRICES_FILE) -> dict:
    # Carry-forward cache for symbols this run's fetch misses. Postgres (this script's own
    # previous run) is the real source now that turtle_live_prices.csv isn't committed to git
    # between runs; the local file is just a local-dev fallback.
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, "turtle_live_prices")
        finally:
            conn.close()
        if not df.empty:
            return {
                str(row["symbol"]).upper(): {"Live_Price": row["live_price"], "Price_As_Of": row["price_as_of"]}
                for _, row in df.iterrows()
            }
    except Exception as exc:
        print(f"WARNING: Postgres read of turtle_live_prices failed, falling back to local CSV: {exc}")

    if not os.path.exists(live_prices_file):
        return {}
    try:
        df = pd.read_csv(live_prices_file)
        return {
            str(row["Symbol"]).upper(): {"Live_Price": row["Live_Price"], "Price_As_Of": row["Price_As_Of"]}
            for _, row in df.iterrows()
        }
    except Exception:
        return {}


def refresh_live_prices(
    symbols: list,
    existing_cache: dict,
    downloader=None,
    batch_size: int = BATCH_SIZE,
    pause_seconds: float = 0.0,
    verbose: bool = True,
) -> tuple:
    """Refresh ``existing_cache`` with newly-fetched prices for ``symbols``. Pure w.r.t. I/O
    (the caller decides whether/where to persist the result) so it's directly unit-testable.

    Returns ``(merged_cache, updated_symbols)`` -- symbols not in ``updated_symbols`` kept
    whatever was already in ``existing_cache`` (or are absent if they never had one).
    """
    cache = dict(existing_cache)
    updated_symbols = set()
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    total_batches = max(1, (len(symbols) + batch_size - 1) // batch_size)

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i : i + batch_size]
        prices = fetch_batch_prices(batch, downloader=downloader)
        for symbol, price in prices.items():
            cache[symbol] = {"Live_Price": price, "Price_As_Of": now_iso}
            updated_symbols.add(symbol)
        if verbose:
            print(f"  batch {i // batch_size + 1}/{total_batches}: "
                  f"{len(prices)}/{len(batch)} prices fetched")
        if pause_seconds and i + batch_size < len(symbols):
            time.sleep(pause_seconds)

    return cache, updated_symbols


def main():
    ap = argparse.ArgumentParser(description="Refresh Turtle Strategy live prices (intraday)")
    ap.add_argument("--limit", type=int, default=None, help="refresh only the first N symbols (testing)")
    ap.add_argument("--pause", type=float, default=0.5,
                     help="seconds to pause between batches (default: 0.5)")
    args = ap.parse_args()

    symbols = load_universe_symbols(UNIVERSE_FILE)
    if args.limit:
        symbols = symbols[: args.limit]
    print(f"Universe: {len(symbols)} symbols.")

    existing_cache = load_existing_cache(LIVE_PRICES_FILE)
    updated_cache, updated_symbols = refresh_live_prices(symbols, existing_cache, pause_seconds=args.pause)

    if not updated_symbols:
        print("WARNING: no live prices fetched this run -- leaving existing cache untouched.")
        return

    rows = [
        {"Symbol": symbol, "Live_Price": info["Live_Price"], "Price_As_Of": info["Price_As_Of"]}
        for symbol, info in sorted(updated_cache.items())
    ]
    result_df = pd.DataFrame(rows, columns=["Symbol", "Live_Price", "Price_As_Of"])
    result_df.to_csv(LIVE_PRICES_FILE, index=False)
    print(f"\nLive prices : {len(updated_symbols)} refreshed this run, {len(rows)} total cached "
          f"-> {os.path.basename(LIVE_PRICES_FILE)}")

    try:
        conn = mdw.get_connection()
        try:
            n = mdw.upsert_dataframe(
                conn, "turtle_live_prices",
                result_df.rename(columns=_LIVE_PRICES_DB_COLUMNS),
                conflict_columns=["symbol"],
            )
            print(f"DB: turtle_live_prices upserted {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed, CSV above is still the source of truth for now: {exc}")


if __name__ == "__main__":
    main()
