#!/usr/bin/env python
"""
Generate Multi-Year Breakout signals + near-breakout watchlist.

Runs the breakout screening pipeline (modules/breakout/screener.py) over the chosen universe,
fetching monthly/daily OHLCV from yfinance and recent delivery % from the NSE Bhav Copy monthly
store, then writes two dated CSVs that the dashboard loads at startup:

    breakout_signals_<YYYYMMDD>.csv     -> Module 1 (Breakout Alerts Feed)
    breakout_watchlist_<YYYYMMDD>.csv   -> Module 2 (Near-Breakout Watchlist)

Two universe sources are supported (--source):
    nse-full      (default) the full NSE EQ-series list (~2,000 symbols, doc §12.1 STEP 1).
                  Downloaded from NSE archives on first run and cached locally as
                  nse_equity_list.csv. The doc explicitly says the ATH filter does the
                  quality work — no fundamental pre-screen needed.
    v20-screened  the V20 fundamentally-screened list (Master_company_market_trend_analysis.csv,
                  ~209 quality stocks). Faster but covers ~8% of NSE.

Usage
-----
    python generate_breakout_signals.py                       # full NSE, delivery required
    python generate_breakout_signals.py --source v20-screened # the old quality-screened subset
    python generate_breakout_signals.py --limit 25            # quick subset (testing)
    python generate_breakout_signals.py --delivery-optional   # bootstrap before delivery exists
"""
import argparse
import io
import os
import time

import pandas as pd
import requests

from modules.breakout import delivery_data as dd
from modules.breakout import screener as sc

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
V20_UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "Master_company_market_trend_analysis.csv")
NSE_UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "nse_equity_list.csv")
NSE_EQUITY_L_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
SIGNALS_TEMPLATE = "breakout_signals_{date_str}.csv"
WATCHLIST_TEMPLATE = "breakout_watchlist_{date_str}.csv"

# Reuse the V20 PSU exclusion set (kept in sync with data_manager.KNOWN_PSU_SYMBOLS).
KNOWN_PSU_SYMBOLS = {
    "BHEL", "BPCL", "COALINDIA", "CONCOR", "GAIL", "HAL", "HPCL", "HUDCO", "IOC",
    "IRCON", "IRCTC", "IRFC", "IREDA", "LICI", "NBCC", "NLCINDIA", "NMDC", "NTPC",
    "OIL", "ONGC", "PFC", "POWERGRID", "RAILTEL", "RCF", "RECLTD", "SAIL", "SBI", "SBIN",
    "SBICARD", "SBILIFE", "SCI", "UNIONBANK", "PNB", "IOB", "INDIANB", "BANKINDIA",
    "CENTRALBK", "CANBK",
}


def _normalise_universe(df: pd.DataFrame) -> pd.DataFrame:
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    if "Company Name" not in df.columns:
        df["Company Name"] = df["Symbol"]
    df = df[~df["Symbol"].isin(KNOWN_PSU_SYMBOLS)]
    df = df.dropna(subset=["Symbol"])
    df = df[df["Symbol"].str.len() > 0]
    return df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)


def load_v20_universe() -> pd.DataFrame:
    if not os.path.exists(V20_UNIVERSE_FILE):
        raise SystemExit(
            f"V20 universe file not found: {V20_UNIVERSE_FILE}\n"
            "Run the weekly stock screening first (generate_weekly_stock_list.py)."
        )
    return _normalise_universe(pd.read_csv(V20_UNIVERSE_FILE))


def _download_nse_equity_l() -> pd.DataFrame:
    """Download NSE's EQUITY_L.csv (browser-like headers, NSE-cookie warm-up)."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        "Accept": "text/csv,application/octet-stream,*/*",
        "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get("https://www.nseindia.com", timeout=15)
    except Exception:
        pass
    for attempt in range(3):
        try:
            resp = session.get(NSE_EQUITY_L_URL, timeout=30)
            if resp.status_code == 200 and b"SYMBOL" in resp.content[:200]:
                raw = pd.read_csv(io.StringIO(resp.content.decode("utf-8", "ignore")))
                raw.columns = [c.strip() for c in raw.columns]
                return raw
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("Failed to download NSE EQUITY_L.csv after 3 attempts")


def load_full_nse_universe(refresh: bool = False) -> pd.DataFrame:
    """Full NSE EQ-series universe (doc §12.1 STEP 1). Caches to nse_equity_list.csv."""
    if not refresh and os.path.exists(NSE_UNIVERSE_FILE):
        try:
            cached = pd.read_csv(NSE_UNIVERSE_FILE)
            if not cached.empty and "Symbol" in cached.columns:
                return _normalise_universe(cached)
        except Exception:
            pass

    raw = _download_nse_equity_l()
    raw["SERIES"] = raw["SERIES"].astype(str).str.strip()
    eq = raw[raw["SERIES"] == "EQ"].copy()
    universe = pd.DataFrame({
        "Symbol": eq["SYMBOL"].astype(str).str.strip().str.upper(),
        "Company Name": eq["NAME OF COMPANY"].astype(str).str.strip(),
    })
    universe = _normalise_universe(universe)
    universe.to_csv(NSE_UNIVERSE_FILE, index=False)
    print(f"Cached {len(universe)} NSE EQ symbols to {os.path.basename(NSE_UNIVERSE_FILE)}")
    return universe


def load_universe(source: str = "nse-full", refresh: bool = False) -> pd.DataFrame:
    if source == "v20-screened":
        return load_v20_universe()
    return load_full_nse_universe(refresh=refresh)


def main():
    ap = argparse.ArgumentParser(description="Generate Multi-Year Breakout signals")
    ap.add_argument("--source", choices=["nse-full", "v20-screened"], default="nse-full",
                    help="universe source (default: nse-full)")
    ap.add_argument("--refresh-universe", action="store_true",
                    help="force re-download of NSE EQUITY_L.csv")
    ap.add_argument("--limit", type=int, default=None, help="screen only the first N symbols")
    ap.add_argument("--delivery-optional", action="store_true",
                    help="do not reject when delivery history is unavailable (bootstrap mode)")
    args = ap.parse_args()

    universe = load_universe(source=args.source, refresh=args.refresh_universe)
    monthly_store = dd.load_monthly_store()
    print(f"Universe ({args.source}): {len(universe)} symbols. Delivery store rows: {len(monthly_store)}.")
    if monthly_store.empty and not args.delivery_optional:
        print("WARNING: delivery store is empty — every breakout will be rejected at STEP 6.\n"
              "         Run download_delivery_data.py --backfill-days 120 first, or pass --delivery-optional.")

    out = sc.run_pipeline(
        universe,
        monthly_store,
        require_delivery=not args.delivery_optional,
        limit=args.limit,
        verbose=True,
    )

    date_str = pd.Timestamp.now().strftime("%Y%m%d")
    signals_path = os.path.join(REPO_BASE_PATH, SIGNALS_TEMPLATE.format(date_str=date_str))
    watch_path = os.path.join(REPO_BASE_PATH, WATCHLIST_TEMPLATE.format(date_str=date_str))

    # Always write the files (with headers) so the dashboard has a stable, current target.
    signals = out["signals"] if not out["signals"].empty else pd.DataFrame(columns=sc.SIGNAL_COLUMNS)
    watch = out["watchlist"] if not out["watchlist"].empty else pd.DataFrame(columns=sc.WATCHLIST_COLUMNS)
    signals.to_csv(signals_path, index=False)
    watch.to_csv(watch_path, index=False)

    print(f"\nBreakout signals : {len(signals):>4}  -> {os.path.basename(signals_path)}")
    print(f"Watchlist        : {len(watch):>4}  -> {os.path.basename(watch_path)}")
    print(f"Rejections       : {len(out['rejections']):>4}")


if __name__ == "__main__":
    main()
