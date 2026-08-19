# data_manager.py
import os
import re
import threading
from datetime import datetime

import numpy as np
import pandas as pd
import requests
import requests_cache
import yfinance as yf

# --- GitHub configuration ---
GITHUB_USERNAME = "pathikpatel-ml"
GITHUB_REPOSITORY = "stock_dashboard_project"

# --- File configuration ---
SIGNALS_FILENAME_TEMPLATE = "stock_candle_signals_from_listing_{date_str}.csv"
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"

# --- Turtle Strategy file configuration ---
TURTLE_SIGNALS_FILENAME_TEMPLATE = "turtle_signals_{date_str}.csv"
NSE_CATEGORIES_FILE = "nse_categories.csv"
TURTLE_LIVE_PRICES_FILE = "turtle_live_prices.csv"

KNOWN_PSU_SYMBOLS = {
    "BHEL", "BPCL", "COALINDIA", "CONCOR", "GAIL", "HAL", "HPCL", "HUDCO", "IOC",
    "IRCON", "IRCTC", "IRFC", "IREDA", "LICI", "NBCC", "NLCINDIA", "NMDC", "NTPC",
    "OIL", "ONGC", "PFC", "POWERGRID", "RAILTEL", "RCF", "RECLTD", "SAIL", "SBI", "SBIN",
    "SBICARD", "SBILIFE", "SCI", "UNIONBANK", "PNB", "IOB", "INDIANB", "BANKINDIA",
    "CENTRALBK", "CANBK"
}

# --- Global cache state ---
v20_signals_cache = pd.DataFrame()
V20_CACHE_DATE = None

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))

v20_signals_df = pd.DataFrame()
growth_df = pd.DataFrame()
all_available_symbols = []
v20_processed_df = pd.DataFrame()

LOADED_V20_FILE_DATE = None
LOADED_V20_SOURCE = None

# --- Turtle Strategy cache state ---
turtle_signals_df = pd.DataFrame()
nse_categories_df = pd.DataFrame()
turtle_live_prices_df = pd.DataFrame()
LOADED_TURTLE_FILE_DATE = None
LOADED_TURTLE_SOURCE = None


def _filter_out_psu_symbols(df):
    if df.empty or "Symbol" not in df.columns:
        return df

    filtered_df = df.copy()
    filtered_df["Symbol"] = filtered_df["Symbol"].astype(str).str.upper().str.strip()
    return filtered_df[~filtered_df["Symbol"].isin(KNOWN_PSU_SYMBOLS)].reset_index(drop=True)


def process_v20_signals(signals_df_local):
    """
    Process V20 signals and calculate proximity from live prices.
    Returns an empty frame when live data is unavailable.
    """
    if signals_df_local.empty or "Symbol" not in signals_df_local.columns:
        return pd.DataFrame()

    df_to_process = signals_df_local.copy()
    print("DASH (V20 NearestBuy): Fetching CMPs...")
    unique_symbols = df_to_process["Symbol"].dropna().astype(str).str.upper().unique()
    if len(unique_symbols) == 0:
        return pd.DataFrame()

    yf_symbols = [f"{symbol}.NS" for symbol in unique_symbols]

    # Run all yfinance downloads in a daemon thread with a 90-second hard cap.
    # result_holder[0] is updated after every successful chunk so partial data
    # is preserved even if we hit the deadline mid-way through.
    result_holder = [{}]

    def _fetch_chunks():
        prices = {}
        for i in range(0, len(yf_symbols), 50):
            chunk = yf_symbols[i:i + 50]
            try:
                data = yf.download(
                    tickers=chunk,
                    period="2d",
                    progress=False,
                    auto_adjust=False,
                    group_by="ticker",
                    timeout=10,
                )
                if data is None or data.empty:
                    continue
                for sym_ns in chunk:
                    base_sym = sym_ns.replace(".NS", "")
                    price_series = None
                    if isinstance(data.columns, pd.MultiIndex):
                        if (sym_ns, "Close") in data.columns:
                            price_series = data[(sym_ns, "Close")]
                        elif (sym_ns.upper(), "Close") in data.columns:
                            price_series = data[(sym_ns.upper(), "Close")]
                    elif "Close" in data.columns and len(chunk) == 1:
                        price_series = data["Close"]
                    if price_series is not None and not price_series.dropna().empty:
                        prices[base_sym.upper()] = price_series.dropna().iloc[-1]
                result_holder[0] = dict(prices)  # persist partial progress
            except Exception:
                continue

    t = threading.Thread(target=_fetch_chunks, daemon=True)
    t.start()
    t.join(timeout=90)
    if t.is_alive():
        print(f"WARNING: CMP fetch timed out after 90s — using {len(result_holder[0])} partial prices.")
    latest_prices_map = result_holder[0]

    df_to_process["Latest Close Price"] = (
        df_to_process["Symbol"].astype(str).str.upper().map(latest_prices_map)
    )
    df_to_process.dropna(subset=["Latest Close Price"], inplace=True)
    if df_to_process.empty:
        return pd.DataFrame()

    results = []
    for _, row in df_to_process.iterrows():
        symbol = str(row.get("Symbol", "")).upper()
        buy_target = row.get("Buy_Price_Low")
        cmp_val = row.get("Latest Close Price")

        if not symbol or pd.isna(buy_target) or buy_target == 0 or pd.isna(cmp_val):
            continue

        prox_pct = ((cmp_val - buy_target) / buy_target) * 100
        buy_date = row.get("Buy_Date")
        buy_date_str = pd.to_datetime(buy_date).strftime("%Y-%m-%d") if pd.notna(buy_date) else "N/A"

        sell_price = row.get("Sell_Price_High", np.nan)
        results.append(
            {
                "Symbol": symbol,
                "Signal Buy Date": buy_date_str,
                "Target Buy Price (Low)": round(buy_target, 2),
                "Latest Close Price": round(cmp_val, 2),
                "Proximity to Buy (%)": round(prox_pct, 2),
                "Closeness (%)": round(abs(prox_pct), 2),
                "Potential Gain (%)": round(row.get("Sequence_Gain_Percent", np.nan), 2),
                "Target Sell Price": round(sell_price, 2) if not pd.isna(sell_price) else np.nan,
            }
        )

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results).sort_values(by=["Closeness (%)", "Symbol"]).reset_index(drop=True)


def _extract_date_from_name(filename, pattern):
    match = re.search(pattern, filename)
    return match.group(1) if match else None


def _sorted_local_matches(filename_regex):
    matches = []
    for filename in os.listdir(REPO_BASE_PATH):
        if re.fullmatch(filename_regex, filename):
            matches.append(filename)

    def sort_key(name):
        date_str = _extract_date_from_name(name, r"(\d{8})")
        return date_str or ""

    return sorted(matches, key=sort_key, reverse=True)


def _fetch_remote_matches(prefix):
    api_url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/contents"
    response = requests.get(api_url, timeout=10)
    response.raise_for_status()
    files = response.json()
    names = [file["name"] for file in files if file["name"].startswith(prefix)]
    return sorted(names, reverse=True)


def _read_csv_with_candidates(today_filename, filename_regex, parse_dates=None):
    parse_dates = parse_dates or []

    local_today_path = os.path.join(REPO_BASE_PATH, today_filename)
    if os.path.exists(local_today_path):
        df = pd.read_csv(local_today_path, parse_dates=parse_dates)
        return df, today_filename, "local"

    raw_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{today_filename}"
    try:
        df = pd.read_csv(raw_url, parse_dates=parse_dates)
        return df, today_filename, "github-raw"
    except Exception:
        pass

    for filename in _sorted_local_matches(filename_regex):
        file_path = os.path.join(REPO_BASE_PATH, filename)
        try:
            df = pd.read_csv(file_path, parse_dates=parse_dates)
            return df, filename, "local-fallback"
        except Exception:
            continue

    prefix = today_filename.split("{")[0] if "{" in today_filename else re.split(r"\d{8}", today_filename)[0]
    try:
        for filename in _fetch_remote_matches(prefix):
            if not re.fullmatch(filename_regex, filename):
                continue
            remote_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{filename}"
            try:
                df = pd.read_csv(remote_url, parse_dates=parse_dates)
                return df, filename, "github-fallback"
            except Exception:
                continue
    except Exception:
        pass

    return pd.DataFrame(), None, None


def _read_static_csv_with_github_fallback(filename):
    """GitHub-raw first, local disk only as a resilience fallback, for a single non-dated
    rolling file (e.g. ``turtle_live_prices.csv``, ``nse_categories.csv``) that gets
    overwritten in place rather than written to a new dated filename each time.

    Why GitHub-raw FIRST (the opposite order from ``_read_csv_with_candidates``'s dated-file
    case): a dated filename is naturally self-healing -- "today's" exact filename usually
    doesn't exist yet on a Render container's disk frozen from an earlier boot, so the local
    check misses and falls through to GitHub automatically. A same-name rolling file has no
    such natural cache-buster: the stale local copy from the last boot always exists at that
    exact path, so an exists-then-read-local-first check would keep serving stale data
    forever. Real bug, reported live: the Turtle tab's intraday-price banner showed a 2-day-old
    timestamp despite the underlying cron running successfully every ~2-3h and updating
    GitHub fine -- this was why. Local read is kept only as a fallback for when GitHub itself
    is unreachable.
    """
    raw_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{filename}"
    try:
        return pd.read_csv(raw_url)
    except Exception:
        pass

    local_path = os.path.join(REPO_BASE_PATH, filename)
    if os.path.exists(local_path):
        try:
            return pd.read_csv(local_path)
        except Exception:
            pass

    return pd.DataFrame()


def get_v20_for_stock(symbol):
    global v20_signals_df
    if v20_signals_df.empty:
        return pd.DataFrame()

    stock_v20 = v20_signals_df[v20_signals_df["Symbol"].astype(str).str.upper() == symbol.upper()]
    if stock_v20.empty:
        return pd.DataFrame()

    return process_v20_signals(stock_v20)


def load_v20_data_on_startup():
    """Load V20 signals from disk/GitHub into ``v20_signals_df``/``v20_processed_df``.

    Split out from ``load_and_process_data_on_startup()`` (2026-08-19) so the V20 render
    callback can call this on every render, not just once at process boot -- mirroring the
    fix Turtle already had. Without it, a single bad/slow fetch at the one boot-time load (or
    simply a long-lived Render container that hasn't redeployed since a new day's file was
    published) left the V20 tab permanently empty/stale until the next redeploy, with no way
    to self-heal. Reported live: "V20 Strategy — no data is loading."
    """
    global v20_signals_df, all_available_symbols, v20_processed_df
    global LOADED_V20_FILE_DATE, LOADED_V20_SOURCE

    today_str = datetime.now().strftime("%Y%m%d")

    v20_filename = SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str)
    v20_signals_df, loaded_v20_name, LOADED_V20_SOURCE = _read_csv_with_candidates(
        today_filename=v20_filename,
        filename_regex=r"stock_candle_signals_from_listing_\d{8}\.csv",
        parse_dates=["Buy_Date", "Sell_Date"],
    )
    LOADED_V20_FILE_DATE = _extract_date_from_name(loaded_v20_name or "", r"(\d{8})")
    if v20_signals_df.empty:
        print("STARTUP ERROR: Failed to load any V20 data file.")
        v20_processed_df = pd.DataFrame()
    else:
        v20_signals_df = _filter_out_psu_symbols(v20_signals_df)
        print(
            f"STARTUP: Loaded {len(v20_signals_df)} V20 rows from "
            f"{loaded_v20_name} via {LOADED_V20_SOURCE}."
        )
        v20_processed_df = process_v20_signals(v20_signals_df)
        print(f"STARTUP: Processed {len(v20_processed_df)} active V20 signals.")

    all_available_symbols = (
        v20_signals_df["Symbol"].dropna().astype(str).str.upper().unique().tolist()
        if not v20_signals_df.empty
        else []
    )


def load_and_process_data_on_startup():
    load_v20_data_on_startup()
    load_turtle_data_on_startup()


def load_turtle_data_on_startup():
    """Load Turtle Strategy signals and the (static, not dated) NSE index-membership file.

    Reuses the same local -> GitHub-raw -> fallback resolution as the V20 loader.
    No PSU filtering — Turtle is a general quant screen, unlike V20's PSU exclusion.
    """
    global turtle_signals_df, nse_categories_df, turtle_live_prices_df
    global LOADED_TURTLE_FILE_DATE, LOADED_TURTLE_SOURCE

    today_str = datetime.now().strftime("%Y%m%d")

    turtle_signals_df, loaded_name, LOADED_TURTLE_SOURCE = _read_csv_with_candidates(
        today_filename=TURTLE_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str),
        filename_regex=r"turtle_signals_\d{8}\.csv",
    )
    LOADED_TURTLE_FILE_DATE = _extract_date_from_name(loaded_name or "", r"(\d{8})")

    # Both are non-dated, overwritten-in-place files -- GitHub-raw-first, not local-first (see
    # _read_static_csv_with_github_fallback's docstring for why local-first silently serves
    # stale data forever on a long-lived Render container between redeploys).
    nse_categories_df = _read_static_csv_with_github_fallback(NSE_CATEGORIES_FILE)
    turtle_live_prices_df = _read_static_csv_with_github_fallback(TURTLE_LIVE_PRICES_FILE)

    print(
        f"STARTUP: Turtle — {len(turtle_signals_df)} signals, "
        f"{len(nse_categories_df)} category rows, "
        f"{len(turtle_live_prices_df)} live prices (source={LOADED_TURTLE_SOURCE})."
    )


def get_turtle_signals_by_offset(offset: int = 0):
    """Return (df, filename) for the ``offset``-th most recent local turtle_signals_*.csv
    (0 = latest, 1 = the one before it — used by the tab's "Yesterday" toggle). Local files
    only (no GitHub-remote fallback, unlike startup loading) since this is an on-demand UI
    lookup, not the initial app load.
    """
    matches = _sorted_local_matches(r"turtle_signals_\d{8}\.csv")
    if offset >= len(matches):
        return pd.DataFrame(), None
    filename = matches[offset]
    try:
        return pd.read_csv(os.path.join(REPO_BASE_PATH, filename)), filename
    except Exception:
        return pd.DataFrame(), None
