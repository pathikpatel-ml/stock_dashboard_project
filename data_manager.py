# data_manager.py
import os
import re
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
MA_SIGNALS_FILENAME_TEMPLATE = "ma_signals_{date_str}.csv"
COMPREHENSIVE_FILENAME_PREFIX = "comprehensive_stock_analysis_"
GROWTH_FILE_NAME = "Master_company_market_trend_analysis.csv"
FULL_UNIVERSE_FILE_NAME = "NSE_EQ_All_Stocks_Analysis.csv"
YEARLY_FUNDAMENTALS_FILE_NAME = "stock_fundamentals_yearly.csv"

KNOWN_PSU_SYMBOLS = {
    "BHEL", "BPCL", "COALINDIA", "CONCOR", "GAIL", "HAL", "HPCL", "HUDCO", "IOC",
    "IRCON", "IRCTC", "IRFC", "IREDA", "LICI", "NBCC", "NLCINDIA", "NMDC", "NTPC",
    "OIL", "ONGC", "PFC", "POWERGRID", "RAILTEL", "RCF", "RECLTD", "SAIL", "SBI", "SBIN",
    "SBICARD", "SBILIFE", "SCI", "UNIONBANK", "PNB", "IOB", "INDIANB", "BANKINDIA",
    "CENTRALBK", "CANBK"
}

# --- Global cache state ---
v20_signals_cache = pd.DataFrame()
ma_signals_cache = pd.DataFrame()
V20_CACHE_DATE = None
MA_CACHE_DATE = None

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
ACTIVE_GROWTH_DF_PATH = os.path.join(REPO_BASE_PATH, GROWTH_FILE_NAME)

signals_df = pd.DataFrame()
v20_signals_df = pd.DataFrame()
growth_df = pd.DataFrame()
all_available_symbols = []
v20_processed_df = pd.DataFrame()
comprehensive_stocks_df = pd.DataFrame()
nse_categories_df = pd.DataFrame()
ma_signals_df = pd.DataFrame()
fundamentals_yearly_df = pd.DataFrame()

LOADED_V20_FILE_DATE = None
LOADED_MA_FILE_DATE = None
LOADED_V20_SOURCE = None
LOADED_MA_SOURCE = None


def _truthy_flag(value):
    if pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _filter_out_psu_symbols(df):
    if df.empty or "Symbol" not in df.columns:
        return df

    filtered_df = df.copy()
    filtered_df["Symbol"] = filtered_df["Symbol"].astype(str).str.upper().str.strip()
    return filtered_df[~filtered_df["Symbol"].isin(KNOWN_PSU_SYMBOLS)].reset_index(drop=True)


def _build_fallback_category_string(row):
    categories = []

    sector = str(row.get("Sector", "")).strip()
    industry = str(row.get("Industry", "")).strip()
    market_cap = str(row.get("Market_Cap", "")).strip()

    if sector:
        categories.append(f"Sector: {sector}")
    if industry:
        categories.append(f"Industry: {industry}")
    if market_cap:
        categories.append(f"Market Cap: {market_cap}")
    if _truthy_flag(row.get("Is PSU")):
        categories.append("PSU")
    if _truthy_flag(row.get("Is Bank/Finance")):
        categories.append("Bank/Finance")

    return ", ".join(dict.fromkeys(categories))


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
    latest_prices_map = {}

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
                    latest_prices_map[base_sym.upper()] = price_series.dropna().iloc[-1]
        except Exception:
            # Keep startup resilient when Yahoo is temporarily unavailable.
            continue

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

        results.append(
            {
                "Symbol": symbol,
                "Signal Buy Date": buy_date_str,
                "Target Buy Price (Low)": round(buy_target, 2),
                "Latest Close Price": round(cmp_val, 2),
                "Proximity to Buy (%)": round(prox_pct, 2),
                "Closeness (%)": round(abs(prox_pct), 2),
                "Potential Gain (%)": round(row.get("Sequence_Gain_Percent", np.nan), 2),
            }
        )

    if not results:
        return pd.DataFrame()

    return pd.DataFrame(results).sort_values(by=["Closeness (%)", "Symbol"]).reset_index(drop=True)


def process_ma_signals_for_ui(ma_events_df):
    if ma_events_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    active_primary = {}
    active_secondary = {}

    for symbol, group in ma_events_df.sort_values(by=["Symbol", "Date"]).groupby("Symbol"):
        last_primary_buy = group[group["Event_Type"] == "Primary_Buy"].tail(1)
        if last_primary_buy.empty:
            continue

        sell_after_buy = group[
            (group["Event_Type"] == "Primary_Sell")
            & (group["Date"] > last_primary_buy.iloc[0]["Date"])
        ]
        if not sell_after_buy.empty:
            continue

        active_primary[symbol] = last_primary_buy.iloc[0].to_dict()
        relevant_events = group[group["Date"] >= last_primary_buy.iloc[0]["Date"]]
        last_sec_buy = relevant_events[relevant_events["Event_Type"] == "Secondary_Buy_Dip"].tail(1)
        if last_sec_buy.empty:
            continue

        sec_sell_after_buy = relevant_events[
            (relevant_events["Event_Type"] == "Secondary_Sell_Rise")
            & (relevant_events["Date"] > last_sec_buy.iloc[0]["Date"])
        ]
        if sec_sell_after_buy.empty:
            active_secondary[symbol] = last_sec_buy.iloc[0].to_dict()

    active_symbols = set(active_primary.keys())
    if not active_symbols:
        return pd.DataFrame(), pd.DataFrame()

    prices = yf.download(
        tickers=[f"{symbol}.NS" for symbol in active_symbols],
        period="2d",
        progress=False,
    )["Close"].iloc[-1]
    latest_prices_map = prices.to_dict()

    primary_list = [
        {
            "Symbol": symbol,
            "Company Name": data.get("Company Name"),
            "Type": data.get("Type"),
            "Market Cap": data.get("MarketCap"),
            "Primary Buy Date": data["Date"].strftime("%Y-%m-%d"),
            "Primary Buy Price": round(data["Price"], 2),
            "Current Price": round(latest_prices_map.get(f"{symbol}.NS", 0), 2),
            "Difference (%)": round(
                ((latest_prices_map.get(f"{symbol}.NS", 0) - data["Price"]) / data.get("Price", 1)) * 100,
                2,
            ),
        }
        for symbol, data in active_primary.items()
        if f"{symbol}.NS" in latest_prices_map
    ]
    secondary_list = [
        {
            "Symbol": symbol,
            "Company Name": data.get("Company Name"),
            "Type": data.get("Type"),
            "Market Cap": data.get("MarketCap"),
            "Secondary Buy Date": data["Date"].strftime("%Y-%m-%d"),
            "Secondary Buy Price": round(data["Price"], 2),
            "Current Price": round(latest_prices_map.get(f"{symbol}.NS", 0), 2),
            "Difference (%)": round(
                ((latest_prices_map.get(f"{symbol}.NS", 0) - data["Price"]) / data.get("Price", 1)) * 100,
                2,
            ),
        }
        for symbol, data in active_secondary.items()
        if f"{symbol}.NS" in latest_prices_map
    ]

    return pd.DataFrame(primary_list), pd.DataFrame(secondary_list)


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


def _yearly_file_sort_key(filename):
    lower_name = str(filename).lower()
    is_sample = "sample" in lower_name
    date_str = _extract_date_from_name(str(filename), r"(\d{8})") or "00000000"
    try:
        date_rank = -int(date_str)
    except ValueError:
        date_rank = 0
    return (is_sample, date_rank, lower_name)


def _list_local_yearly_fundamentals_candidates():
    candidates = []

    root_file = YEARLY_FUNDAMENTALS_FILE_NAME
    root_path = os.path.join(REPO_BASE_PATH, root_file)
    if os.path.exists(root_path):
        candidates.append((root_path, root_file))

    output_dir = os.path.join(REPO_BASE_PATH, "output")
    if os.path.isdir(output_dir):
        for filename in os.listdir(output_dir):
            lower_name = filename.lower()
            if not lower_name.startswith("stock_fundamentals_yearly") or not lower_name.endswith(".csv"):
                continue
            file_path = os.path.join(output_dir, filename)
            candidates.append((file_path, os.path.join("output", filename)))

    seen = set()
    deduped = []
    for file_path, display_name in sorted(candidates, key=lambda item: _yearly_file_sort_key(item[1])):
        key = file_path.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append((file_path, display_name))
    return deduped


def _list_remote_yearly_fundamentals_candidates():
    candidates = [YEARLY_FUNDAMENTALS_FILE_NAME]
    api_root = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/contents/output"
    try:
        response = requests.get(api_root, timeout=10)
        response.raise_for_status()
        for file_item in response.json():
            file_name = file_item.get("name", "")
            lower_name = str(file_name).lower()
            if lower_name.startswith("stock_fundamentals_yearly") and lower_name.endswith(".csv"):
                candidates.append(f"output/{file_name}")
    except Exception:
        pass

    deduped = sorted(dict.fromkeys(candidates), key=_yearly_file_sort_key)
    return deduped


def _normalize_comprehensive_columns(df):
    if df.empty:
        return pd.DataFrame()

    renamed = df.rename(
        columns={
            "Company Name": "Company_Name",
            "Net Profit (Cr)": "Net_Profit_Cr",
            "Latest Quarter Profit (Cr)": "Latest_Quarter_Profit",
            "ROCE (%)": "ROCE",
            "ROE (%)": "ROE",
            "Debt to Equity": "Debt_to_Equity",
            "Public Holding (%)": "Public_Holding_Percent",
            "Market Cap": "Market_Cap",
            "MA_10": "MA10",
            "MA_50": "MA50",
            "MA_100": "MA100",
            "MA_200": "MA200",
        }
    ).copy()

    defaults = {
        "Company_Name": "",
        "Net_Profit_Cr": np.nan,
        "Latest_Quarter_Profit": np.nan,
        "ROCE": np.nan,
        "ROE": np.nan,
        "Debt_to_Equity": np.nan,
        "Public_Holding_Percent": np.nan,
        "Current_Price": np.nan,
        "MA10": np.nan,
        "MA50": np.nan,
        "MA100": np.nan,
        "MA200": np.nan,
        "NSE_Categories": "",
    }
    for column, default_value in defaults.items():
        if column not in renamed.columns:
            renamed[column] = default_value

    numeric_columns = [
        "Net_Profit_Cr",
        "Latest_Quarter_Profit",
        "ROCE",
        "ROE",
        "Debt_to_Equity",
        "Public_Holding_Percent",
        "Current_Price",
        "MA10",
        "MA50",
        "MA100",
        "MA200",
    ]
    for column in numeric_columns:
        renamed[column] = pd.to_numeric(renamed[column], errors="coerce")

    if "Symbol" in renamed.columns:
        renamed["Symbol"] = renamed["Symbol"].astype(str).str.upper()
        renamed = _filter_out_psu_symbols(renamed)

    categories_missing = renamed["NSE_Categories"].fillna("").astype(str).str.strip().eq("")
    if categories_missing.any():
        renamed.loc[categories_missing, "NSE_Categories"] = renamed.loc[categories_missing].apply(
            _build_fallback_category_string,
            axis=1,
        )

    return renamed


def _normalize_fundamentals_yearly_columns(df):
    if df.empty:
        return pd.DataFrame()

    normalized = df.copy()
    rename_map = {
        "Symbol": "ticker",
        "Ticker": "ticker",
        "Year": "year",
        "Sector": "sector",
        "Market Cap": "market_cap",
    }
    normalized = normalized.rename(columns=rename_map)

    required_columns = [
        "ticker",
        "year",
        "sales_growth_pct",
        "roce_pct",
        "pb_ratio",
        "book_value_growth_pct",
        "eps_growth_pct",
        "promoter_holding_pct",
        "ps_ratio",
        "pcf_ratio",
        "promoter_pledging_pct",
        "quality_turnover_pct",
        "interest_coverage_ratio",
        "sector",
        "market_cap",
    ]

    for column in required_columns:
        if column not in normalized.columns:
            normalized[column] = np.nan

    normalized["ticker"] = normalized["ticker"].astype(str).str.upper().str.strip()
    normalized["year"] = pd.to_numeric(normalized["year"], errors="coerce")
    normalized = normalized.dropna(subset=["ticker", "year"]).copy()
    normalized["year"] = normalized["year"].astype(int)

    numeric_columns = [column for column in required_columns if column not in {"ticker", "year", "sector"}]
    for column in numeric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["sector"] = normalized["sector"].fillna("Unknown").astype(str).str.strip()
    normalized.loc[normalized["sector"].eq(""), "sector"] = "Unknown"
    normalized = normalized.drop_duplicates(subset=["ticker", "year"], keep="last")
    return normalized.sort_values(["ticker", "year"]).reset_index(drop=True)


def load_comprehensive_stock_data():
    """Load screener data from the newest full-universe file, then fall back as needed."""
    global comprehensive_stocks_df, nse_categories_df

    comprehensive_stocks_df = pd.DataFrame()
    nse_categories_df = pd.DataFrame()

    try:
        full_universe_local_path = os.path.join(REPO_BASE_PATH, FULL_UNIVERSE_FILE_NAME)
        if os.path.exists(full_universe_local_path):
            comprehensive_stocks_df = _normalize_comprehensive_columns(pd.read_csv(full_universe_local_path))
            print(f"Loaded {len(comprehensive_stocks_df)} stocks from bundled universe file {FULL_UNIVERSE_FILE_NAME}")

        if comprehensive_stocks_df.empty:
            try:
                full_universe_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{FULL_UNIVERSE_FILE_NAME}"
                comprehensive_stocks_df = _normalize_comprehensive_columns(pd.read_csv(full_universe_url))
                print(f"Loaded {len(comprehensive_stocks_df)} stocks from GitHub universe file {FULL_UNIVERSE_FILE_NAME}")
            except Exception:
                comprehensive_stocks_df = pd.DataFrame()

        local_matches = _sorted_local_matches(r"comprehensive_stock_analysis_\d+\.csv")
        remote_matches = []
        if comprehensive_stocks_df.empty and not local_matches:
            try:
                remote_matches = _fetch_remote_matches(COMPREHENSIVE_FILENAME_PREFIX)
            except Exception:
                remote_matches = []

        for filename in local_matches if comprehensive_stocks_df.empty else []:
            try:
                comprehensive_stocks_df = _normalize_comprehensive_columns(
                    pd.read_csv(os.path.join(REPO_BASE_PATH, filename))
                )
                print(f"Loaded {len(comprehensive_stocks_df)} stocks from local file {filename}")
                break
            except Exception:
                continue

        if comprehensive_stocks_df.empty:
            for filename in remote_matches:
                if not filename.startswith(COMPREHENSIVE_FILENAME_PREFIX):
                    continue
                try:
                    remote_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{filename}"
                    comprehensive_stocks_df = _normalize_comprehensive_columns(pd.read_csv(remote_url))
                    print(f"Loaded {len(comprehensive_stocks_df)} stocks from GitHub file {filename}")
                    break
                except Exception:
                    continue

        if comprehensive_stocks_df.empty and os.path.exists(ACTIVE_GROWTH_DF_PATH):
            comprehensive_stocks_df = _normalize_comprehensive_columns(pd.read_csv(ACTIVE_GROWTH_DF_PATH))
            print(f"Loaded {len(comprehensive_stocks_df)} stocks from bundled file {GROWTH_FILE_NAME}")

        nse_local_path = os.path.join(REPO_BASE_PATH, "nse_categories.csv")
        if os.path.exists(nse_local_path):
            nse_categories_df = pd.read_csv(nse_local_path)
        else:
            try:
                nse_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/nse_categories.csv"
                nse_categories_df = pd.read_csv(nse_url)
            except Exception:
                nse_categories_df = pd.DataFrame()

        if not nse_categories_df.empty and not comprehensive_stocks_df.empty:
            nse_categories_df["Symbol"] = nse_categories_df["Symbol"].astype(str).str.upper()
            category_map = nse_categories_df.set_index("Symbol")["NSE_Categories"]
            comprehensive_stocks_df["NSE_Categories"] = (
                comprehensive_stocks_df["Symbol"].map(category_map).fillna(comprehensive_stocks_df["NSE_Categories"])
            )
        elif not comprehensive_stocks_df.empty and "NSE_Categories" in comprehensive_stocks_df.columns:
            comprehensive_stocks_df["NSE_Categories"] = comprehensive_stocks_df["NSE_Categories"].fillna("")
    except Exception as e:
        print(f"Error loading comprehensive stock data: {e}")
        comprehensive_stocks_df = pd.DataFrame()
        nse_categories_df = pd.DataFrame()


def load_fundamentals_yearly_data():
    global fundamentals_yearly_df

    fundamentals_yearly_df = pd.DataFrame()
    try:
        for local_path, display_name in _list_local_yearly_fundamentals_candidates():
            try:
                loaded_df = _normalize_fundamentals_yearly_columns(pd.read_csv(local_path))
                if loaded_df.empty:
                    continue
                fundamentals_yearly_df = loaded_df
                print(
                    f"Loaded {len(fundamentals_yearly_df)} yearly fundamentals rows from "
                    f"{display_name} (local)"
                )
                return
            except Exception:
                continue

        for remote_path in _list_remote_yearly_fundamentals_candidates():
            remote_url = (
                f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPOSITORY}/main/{remote_path}"
            )
            try:
                loaded_df = _normalize_fundamentals_yearly_columns(pd.read_csv(remote_url))
                if loaded_df.empty:
                    continue
                fundamentals_yearly_df = loaded_df
                print(
                    f"Loaded {len(fundamentals_yearly_df)} yearly fundamentals rows from "
                    f"{remote_path} (github)"
                )
                return
            except Exception:
                continue

        print(
            "Yearly fundamentals file not found in local root/output or GitHub root/output. "
            "Expected stock_fundamentals_yearly.csv or output/stock_fundamentals_yearly*.csv"
        )
    except Exception as e:
        print(f"Error loading yearly fundamentals data: {e}")
        fundamentals_yearly_df = pd.DataFrame()


def get_v20_for_stock(symbol):
    global v20_signals_df
    if v20_signals_df.empty:
        return pd.DataFrame()

    stock_v20 = v20_signals_df[v20_signals_df["Symbol"].astype(str).str.upper() == symbol.upper()]
    if stock_v20.empty:
        return pd.DataFrame()

    return process_v20_signals(stock_v20)


def get_ma_for_stock(symbol):
    try:
        from modules.ma_calculator import calculate_moving_averages

        return calculate_moving_averages(symbol)
    except Exception as e:
        print(f"Error calculating MA for {symbol}: {e}")
        return {}


def load_and_process_data_on_startup():
    global v20_signals_df, signals_df, all_available_symbols, v20_processed_df, ma_signals_df
    global LOADED_V20_FILE_DATE, LOADED_MA_FILE_DATE, LOADED_V20_SOURCE, LOADED_MA_SOURCE

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

    ma_filename = MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str)
    ma_signals_df, loaded_ma_name, LOADED_MA_SOURCE = _read_csv_with_candidates(
        today_filename=ma_filename,
        filename_regex=r"ma_signals_\d{8}\.csv",
        parse_dates=["Date"],
    )
    LOADED_MA_FILE_DATE = _extract_date_from_name(loaded_ma_name or "", r"(\d{8})")
    if ma_signals_df.empty:
        print("STARTUP ERROR: Failed to load any MA data file.")
        signals_df = pd.DataFrame()
    else:
        signals_df = ma_signals_df.copy()
        print(
            f"STARTUP: Loaded {len(ma_signals_df)} MA rows from "
            f"{loaded_ma_name} via {LOADED_MA_SOURCE}."
        )

    load_comprehensive_stock_data()
    load_fundamentals_yearly_data()

    symbols_v20 = v20_signals_df["Symbol"].dropna().astype(str).str.upper().unique().tolist() if not v20_signals_df.empty else []
    symbols_ma = ma_signals_df["Symbol"].dropna().astype(str).str.upper().unique().tolist() if not ma_signals_df.empty else []
    symbols_comp = (
        comprehensive_stocks_df["Symbol"].dropna().astype(str).str.upper().unique().tolist()
        if not comprehensive_stocks_df.empty and "Symbol" in comprehensive_stocks_df.columns
        else []
    )
    symbols_fundamentals = (
        fundamentals_yearly_df["ticker"].dropna().astype(str).str.upper().unique().tolist()
        if not fundamentals_yearly_df.empty and "ticker" in fundamentals_yearly_df.columns
        else []
    )
    all_available_symbols = sorted(set(symbols_v20 + symbols_ma + symbols_comp + symbols_fundamentals))

