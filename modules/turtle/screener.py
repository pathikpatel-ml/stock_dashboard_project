"""
Orchestration layer for the Turtle Strategy screener (docs/TURTLE_STRATEGY_PLAN.md).

Wires the pure functions in ``compute.py`` to real data:
  * OHLCV via ``modules.breakout.data_feed`` (reused — no new fetcher, per plan §3).
  * The pre-computed universe (Sector/Industry/Current_Price/MA200) from
    ``NSE_EQ_All_Stocks_Analysis.csv``.
  * Consolidated TTM + historical-max-annual Net Profit/Net Sales from
    ``turtle_screener_fundamentals.csv`` (screener.in, via ``generate_turtle_fundamentals.py`` —
    see ``modules.turtle.standalone_fundamentals``). Both ATH_Profit_Flag and ATH_Sales_Flag are
    a direct TTM-vs-max-annual comparison now, no EPS/shares-outstanding proxy needed, since TTM
    and annual both come from the same screener.in table (same units, same consolidated basis).
  * The benchmark (Nifty 500 proxy, LOCKED decision #2) via a direct yfinance call — NOT
    through ``data_feed``, which always appends ``.NS`` and is NSE-equity-only.
  * NSE sectoral index membership from ``nse_categories.csv`` — used to pick each stock's RS
    peer-group basket (its sectoral index if it's in one, e.g. NIFTY PHARMA, else the broad
    Sector column) -- see constants.py's ``BROAD_INDEX_TAGS`` note.
  * Each sectoral index's own real 52-week RS, via ``fetch_sectoral_index_rs`` (same direct
    yfinance treatment as the benchmark) for indices with a verified ticker -- see
    constants.py's ``SECTORAL_INDEX_TICKERS`` note. Takes priority over the leave-one-out
    member-average for any peer group it covers.

``run_pipeline`` is a two-pass batch: pass 1 fetches OHLCV once per symbol and computes each
stock's own relative strength; pass 2 derives the RS peer-group basket from those
already-computed values (no redundant per-stock refetching) -- using each sectoral index's own
real RS where available, else falling back to the equal-weight member average -- then finalizes
flags/classification.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from modules.breakout import data_feed
from . import compute
from . import constants as C

SIGNAL_COLUMNS = [
    "Symbol", "Company", "Sector", "Industry", "Current_Price",
    "ATH_Price_Flag", "TTM_Net_Profit", "ATH_Profit_Flag", "Above_MA212_Flag",
    "RS_Peer_Group", "RS_vs_Sector", "RS_vs_Benchmark", "Outperformance_Flag",
    "TTM_Net_Sales", "ATH_Sales", "ATH_Sales_Flag", "Signal",
]


def _fetch_index_rs(ticker: str) -> Optional[float]:
    """Fetch one index's own 52-week (weekly high-close) relative strength directly from its
    yfinance ticker -- shared by ``fetch_benchmark_rs`` and ``fetch_sectoral_index_rs``.
    Returns None (never raises) on any fetch/parse failure; callers decide what that means.
    """
    try:
        hist = yf.Ticker(ticker).history(
            period=C.DAILY_HISTORY_PERIOD, interval="1d", auto_adjust=False, timeout=20
        )
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist.columns:
        return None

    # Index must be assigned BEFORE dropna(), not after -- dropna() on the value series alone
    # can drop a different number of rows than the raw index has (any NaN close in the fetch),
    # and reassigning the ORIGINAL (undropped) index onto the now-shorter series raises a
    # length-mismatch ValueError. Assigning first means dropna() correctly drops the matching
    # index entry along with each dropped value. Real bug, surfaced live by a genuine NaN close
    # in a sectoral index fetch (the per-stock path in run_pipeline never hit this because
    # modules.breakout.data_feed already returns a normalised DatetimeIndex upstream, so no
    # separate reassignment is needed there at all).
    close = pd.to_numeric(hist["Close"], errors="coerce")
    close.index = pd.DatetimeIndex(hist.index).tz_localize(None)
    close = close.dropna()
    return compute.relative_strength(close)


def fetch_benchmark_rs(session=None) -> float:
    """Fetch the benchmark's 52-week (weekly high-close) relative strength (LOCKED decision #2).

    Tries ``BENCHMARK_TICKER`` (Nifty 500 proxy for BSE 500), then each entry in
    ``BENCHMARK_FALLBACK_TICKERS``. Raises RuntimeError if none return usable data — per the
    locked decision, a benchmark fetch failure must stop the run, not silently degrade.
    """
    tickers = [C.BENCHMARK_TICKER] + list(C.BENCHMARK_FALLBACK_TICKERS)
    for ticker in tickers:
        rs = _fetch_index_rs(ticker)
        if rs is not None:
            return rs

    raise RuntimeError(
        f"Could not fetch benchmark relative strength from any of {tickers}. "
        "Per the locked benchmark decision, refusing to silently fall back further."
    )


def fetch_sectoral_index_rs(tickers: Optional[Dict[str, str]] = None) -> Dict[str, float]:
    """Fetch each sectoral index's own 52-week RS directly (same treatment as
    ``fetch_benchmark_rs``) -- more accurate than averaging member stocks' RS, since it
    reflects the index's real market-cap-weighted performance. Only ``C.SECTORAL_INDEX_TICKERS``
    entries are attempted (every one individually verified live before being added -- see that
    constant's docstring). A single index's fetch failure just means it's absent from the
    returned dict, NOT a run-stopping error like the benchmark -- ``run_pipeline`` falls back
    to the leave-one-out peer-average for any tag missing here (unlike the benchmark, which
    the whole run depends on, an individual sectoral index's RS has a graceful degradation
    path already built for exactly this "no tag mapping" case).
    """
    tickers = tickers if tickers is not None else C.SECTORAL_INDEX_TICKERS
    result: Dict[str, float] = {}
    for index_name, ticker in tickers.items():
        rs = _fetch_index_rs(ticker)
        if rs is not None:
            result[index_name] = rs
    return result


def _fetch_index_ath_and_rs(ticker: str) -> Optional[Dict[str, object]]:
    """Fetch one index's own ATH-price flag + 52-week RS -- same two-series treatment
    (monthly ``max`` period for the true all-time-high, daily ``2y`` for the RS/current-price)
    already used for individual stocks in ``run_pipeline``, just fed an index ticker instead
    of a stock symbol. Returns None (never raises) if the daily fetch fails; the monthly fetch
    failing just means the ATH check falls back to the daily-only max, mirroring
    ``run_pipeline``'s existing monthly-fetch-optional behaviour.
    """
    try:
        daily = yf.Ticker(ticker).history(
            period=C.DAILY_HISTORY_PERIOD, interval="1d", auto_adjust=False, timeout=20
        )
    except Exception:
        daily = None
    if daily is None or daily.empty or "Close" not in daily.columns:
        return None

    # Index-before-dropna (see _fetch_index_rs's comment for why the reverse order raises a
    # length-mismatch ValueError whenever the fetch has any NaN close).
    daily_close = pd.to_numeric(daily["Close"], errors="coerce")
    daily_close.index = pd.DatetimeIndex(daily.index).tz_localize(None)
    daily_close = daily_close.dropna()
    if daily_close.empty:
        return None

    try:
        monthly = yf.Ticker(ticker).history(
            period=C.MONTHLY_HISTORY_PERIOD, interval="1mo", timeout=20
        )
    except Exception:
        monthly = None
    monthly_max = float(monthly["Close"].max()) if monthly is not None and not monthly.empty else None

    current_price = float(daily_close.iloc[-1])
    historical_max = float(daily_close.max())
    if monthly_max is not None:
        historical_max = max(historical_max, monthly_max)

    return {
        "ath_price_flag": compute.ath_price_flag(current_price, historical_max),
        "rs": compute.relative_strength(daily_close),
    }


def fetch_sector_pulse_table(
    tickers: Optional[Dict[str, str]] = None,
    nifty50_ticker: str = None,
) -> pd.DataFrame:
    """Build the "Sector Pulse" dashboard table: one row per sectoral index (not per stock),
    with its own ATH_Price_Flag and RS_vs_Nifty50 -- both computed the exact same way as for
    a stock, just applied to the index's own price series directly.

    ``RS_vs_Nifty50`` uses Nifty 50's own RS (``C.NIFTY_50_INDEX_TICKER``) as the comparison
    baseline -- a deliberately different reference point from RS_vs_Benchmark's Nifty 500, per
    what was asked for this table specifically. If Nifty 50's own RS can't be fetched, returns
    an empty DataFrame (this whole table is meaningless without that baseline) rather than a
    partially-broken one. An individual sectoral index's fetch failure just drops that one row.
    """
    tickers = tickers if tickers is not None else C.SECTORAL_INDEX_TICKERS
    nifty50_ticker = nifty50_ticker if nifty50_ticker is not None else C.NIFTY_50_INDEX_TICKER

    nifty50_rs = _fetch_index_rs(nifty50_ticker)
    if nifty50_rs is None:
        return pd.DataFrame(columns=["Sector", "ATH_Price_Flag", "RS_vs_Nifty50"])

    rows = []
    for index_name, ticker in tickers.items():
        result = _fetch_index_ath_and_rs(ticker)
        if result is None:
            continue
        rs = result["rs"]
        rows.append({
            "Sector": index_name,
            "ATH_Price_Flag": result["ath_price_flag"],
            "RS_vs_Nifty50": round(rs - nifty50_rs, 2) if rs is not None else None,
        })
    return pd.DataFrame(rows, columns=["Sector", "ATH_Price_Flag", "RS_vs_Nifty50"])


def build_fundamentals_lookup(fundamentals_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """``turtle_screener_fundamentals.csv`` (Symbol, TTM_Net_Profit, TTM_Net_Sales,
    Max_Annual_Net_Profit, Max_Annual_Net_Sales — see ``generate_turtle_fundamentals.py``) ->
    per-symbol lookup dict, keyed by uppercased Symbol.
    """
    if fundamentals_df is None or fundamentals_df.empty:
        return {}
    df = fundamentals_df.copy()
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()

    result: Dict[str, Dict[str, float]] = {}
    for _, row in df.iterrows():
        result[row["Symbol"]] = {
            "ttm_net_profit": row.get("TTM_Net_Profit"),
            "ttm_net_sales": row.get("TTM_Net_Sales"),
            "max_annual_net_profit": row.get("Max_Annual_Net_Profit"),
            "max_annual_net_sales": row.get("Max_Annual_Net_Sales"),
        }
    return result


def build_categories_lookup(categories_df: pd.DataFrame) -> Dict[str, str]:
    """``nse_categories.csv`` (Symbol, NSE_Categories) -> per-symbol lookup of the raw
    comma-joined categories string, keyed by uppercased Symbol. Feeds
    ``compute.sectoral_index_tag`` for the RS peer-group basket (see constants.py).
    """
    if categories_df is None or categories_df.empty or "NSE_Categories" not in categories_df.columns:
        return {}
    df = categories_df.copy()
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    return dict(zip(df["Symbol"], df["NSE_Categories"]))


def _stock_price_history(symbol: str) -> Dict[str, Optional[object]]:
    """Fetch monthly + daily OHLCV for ``symbol`` via the reused breakout data_feed."""
    monthly = data_feed.get_monthly(symbol, period=C.MONTHLY_HISTORY_PERIOD)
    daily = data_feed.get_daily(symbol, period=C.DAILY_HISTORY_PERIOD)
    return {"monthly": monthly, "daily": daily}


def run_pipeline(
    universe_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    benchmark_rs: float,
    categories_df: Optional[pd.DataFrame] = None,
    sectoral_index_rs: Optional[Dict[str, float]] = None,
    limit: Optional[int] = None,
    verbose: bool = True,
    pause_seconds: float = 0.0,
) -> Dict[str, pd.DataFrame]:
    """Run the Turtle screen over ``universe_df`` (NSE_EQ_All_Stocks_Analysis.csv shape).

    Returns {"signals": df, "rejections": df}. A symbol is only rejected (skipped from
    ``signals``) when its OHLCV can't be fetched at all — everything else degrades to safe
    per-flag defaults (see compute.py) rather than dropping the row, since a stock missing
    e.g. fundamentals data can still be meaningfully scored on price-only signals.

    ``categories_df`` (``nse_categories.csv`` shape, optional) drives the RS peer-group
    basket: a stock in a sectoral NSE index (NIFTY BANK, NIFTY PHARMA, ...) is compared
    against that index's other members instead of the broad ``Sector`` column -- see
    constants.py's ``BROAD_INDEX_TAGS`` note. Omitted/empty -> every stock falls back to the
    broad Sector grouping (the pre-2026-08-15 behaviour).

    ``sectoral_index_rs`` (optional, from ``fetch_sectoral_index_rs()``) takes priority over
    the leave-one-out peer-average WHENEVER a stock's peer-group tag has an entry in it: the
    sectoral index's own real 52-week RS is used directly (same treatment as
    RS_vs_Benchmark), rather than approximating it via an equal-weight average of member
    stocks. Falls back to the peer-average for any tag missing here (no verified ticker for
    that index, or it's a broad-Sector fallback, which never has an index price to fetch).

    ``pause_seconds`` (default 0, i.e. off) adds a light delay after each symbol's fetch —
    cheap insurance against Yahoo Finance throttling across the ~2,365-symbol full universe.
    Left at 0 for tests, which stub the fetch entirely and don't need pacing.
    """
    fundamentals_lookup = build_fundamentals_lookup(fundamentals_df)
    categories_lookup = build_categories_lookup(categories_df)
    sectoral_index_rs = sectoral_index_rs or {}
    rows = universe_df.head(limit) if limit else universe_df

    per_symbol: List[dict] = []
    rejects: List[dict] = []

    for i, (_, urow) in enumerate(rows.iterrows(), 1):
        symbol = str(urow.get("Symbol", "")).strip().upper()
        if not symbol:
            continue
        try:
            history = _stock_price_history(symbol)
        except Exception as exc:  # network resilience — never crash the batch
            rejects.append({"Symbol": symbol, "reason": f"fetch_error:{exc}"})
            continue
        finally:
            if pause_seconds:
                time.sleep(pause_seconds)

        monthly, daily = history["monthly"], history["daily"]
        if monthly is None or monthly.empty or "Close" not in monthly.columns:
            rejects.append({"Symbol": symbol, "reason": "no_monthly_data"})
            continue

        monthly_max_close = float(monthly["Close"].max())

        daily_close = None
        if daily is not None and not daily.empty and "Close" in daily.columns:
            daily_close = pd.to_numeric(daily["Close"], errors="coerce").dropna()
            if daily_close.empty:
                daily_close = None

        stock_rs = compute.relative_strength(daily_close) if daily_close is not None else None

        csv_current_price = urow.get("Current_Price")
        csv_ma200 = urow.get("MA200")  # only MA the weekly CSV has -- emergency fallback only

        # Round-3 fix: price and its exit-price average must come from the SAME fresh series,
        # or a stock at/near its live ATH can show "Above_MA212 = false" purely because the
        # weekly-cron CSV (up to ~2.5 months stale in the incident that prompted this) is
        # comparing a live-ish number against a stale one. So: live daily close for the
        # displayed/used price (feeds Current_Price, ATH-price, and above_exit_flag alike),
        # and a live EXIT_MA_PERIOD-day SMA (212, Turtle's actual methodology) computed from
        # that same daily series for above_exit_flag. Each falls back independently to the
        # CSV snapshot only when the live source is unavailable (no daily data at all for
        # price; fewer than EXIT_MA_PERIOD daily rows for the SMA specifically -- the CSV
        # only has MA200, close enough for that rare fallback case).
        if daily_close is not None:
            live_price = float(daily_close.iloc[-1])
            historical_max_close = max(float(daily_close.max()), monthly_max_close)
        else:
            live_price = csv_current_price  # csv-fallback: no daily data at all
            historical_max_close = monthly_max_close

        if daily_close is not None and len(daily_close) >= C.EXIT_MA_PERIOD:
            live_exit_ma = float(daily_close.rolling(C.EXIT_MA_PERIOD).mean().iloc[-1])  # source=live
        else:
            live_exit_ma = csv_ma200  # source=csv-fallback (MA200): <212 daily rows

        sector = urow.get("Sector")
        fundamentals = fundamentals_lookup.get(symbol, {})

        # RS peer group: prefer the stock's NSE sectoral index (NIFTY BANK, NIFTY PHARMA,
        # ...) over the broad Sector tag -- see constants.py's BROAD_INDEX_TAGS note. Falls
        # back to the broad Sector for stocks not in any sectoral index. ``sector_is_valid``
        # uses pd.isna, NOT a plain truthy check -- ``bool(float("nan"))`` is True in Python,
        # so a naive ``if sector`` let NaN-sector stocks all collapse into one bogus
        # "SECTOR:nan" bucket and get compared against each other, which is meaningless
        # (caught live: 79 real stocks affected). A missing/NaN sector with no sectoral tag
        # either now gets peer_group_key=None, which pandas' groupby drops entirely -- same
        # "undefined, no peers" outcome group-size-1 sectors already get.
        sectoral_tag = compute.sectoral_index_tag(categories_lookup.get(symbol))
        sector_is_valid = sector is not None and not (isinstance(sector, float) and pd.isna(sector))
        if sectoral_tag:
            peer_group_key = sectoral_tag
            peer_group_label = sectoral_tag
        elif sector_is_valid:
            peer_group_key = f"SECTOR:{sector}"
            peer_group_label = f"Sector: {sector}"
        else:
            peer_group_key = None
            peer_group_label = None

        per_symbol.append({
            "Symbol": symbol,
            "Company": urow.get("Company Name", symbol),
            "Sector": sector,
            "Industry": urow.get("Industry"),
            # Live daily close (csv-fallback only if daily data is missing) -- both
            # displayed and fed into every price-based flag, so nothing compares a fresh
            # number against a stale one.
            "Current_Price": live_price,
            "ExitMA": live_exit_ma,
            "historical_max_close": historical_max_close,
            "stock_rs": stock_rs,
            "peer_group_key": peer_group_key,
            "peer_group_label": peer_group_label,
            "ttm_net_profit": fundamentals.get("ttm_net_profit"),
            "ttm_net_sales": fundamentals.get("ttm_net_sales"),
            "max_annual_net_profit": fundamentals.get("max_annual_net_profit"),
            "max_annual_net_sales": fundamentals.get("max_annual_net_sales"),
        })

        if verbose and i % 100 == 0:
            print(f"  turtle: fetched {i}/{len(rows)} symbols")

    if not per_symbol:
        return {"signals": pd.DataFrame(columns=SIGNAL_COLUMNS), "rejections": pd.DataFrame(rejects)}

    fetched_df = pd.DataFrame(per_symbol)

    # Equal-weight RS peer-group basket, derived from the already-fetched stock_rs values —
    # no redundant refetching per peer. Grouped by peer_group_key (a stock's sectoral NSE
    # index if it has one, else "SECTOR:<Sector>" -- see the per-symbol loop above). Leave-
    # one-out: each stock is compared against the mean of its *peers*, excluding its own
    # value, so it isn't compared against a basket it belongs to (which biases small groups
    # and makes a single-member group structurally unable to outperform). sum/count are kept
    # per group so the per-stock exclusion is O(1) instead of recomputing a mean per stock.
    group_stats = (
        fetched_df.dropna(subset=["stock_rs"]).groupby("peer_group_key")["stock_rs"].agg(["sum", "count"]).to_dict("index")
    )

    def _leave_one_out_group_rs(peer_group_key, own_stock_rs):
        stats = group_stats.get(peer_group_key)
        if stats is None or own_stock_rs is None or stats["count"] <= 1:
            return None  # undefined for a single-member group (or no valid peers)
        return (stats["sum"] - own_stock_rs) / (stats["count"] - 1)

    def _sector_rs_for(peer_group_key, own_stock_rs):
        # A sectoral index with a verified ticker (sectoral_index_rs) uses the index's own
        # real RS directly -- more accurate than the leave-one-out member average, and the
        # same treatment RS_vs_Benchmark already gets. Falls back to the peer-average for any
        # tag without a ticker mapping (no verified yfinance ticker for that index, or it's a
        # "SECTOR:<Sector>" broad fallback key, which never has an index price to fetch).
        if peer_group_key in sectoral_index_rs:
            return sectoral_index_rs[peer_group_key]
        return _leave_one_out_group_rs(peer_group_key, own_stock_rs)

    signals = []
    for row in per_symbol:
        sector_rs = _sector_rs_for(row["peer_group_key"], row["stock_rs"])

        ath_price = compute.ath_price_flag(row["Current_Price"], row["historical_max_close"])
        ath_profit = compute.ath_profit_flag(row["ttm_net_profit"], row["max_annual_net_profit"])
        above_exit = compute.above_exit_flag(row["Current_Price"], row["ExitMA"])
        outperformance = compute.outperformance_flag(row["stock_rs"], sector_rs, benchmark_rs)
        signal = compute.classify(ath_price, ath_profit, above_exit, outperformance)

        # Informational only -- NOT part of classify() (the locked 3-signal + exit-price
        # methodology is unchanged); mirrors the ATH_Profit_Flag/TTM_Net_Profit display pair.
        ath_sales = compute.ath_sales_flag(row["ttm_net_sales"], row["max_annual_net_sales"])

        rs_vs_sector = (
            row["stock_rs"] - sector_rs if row["stock_rs"] is not None and sector_rs is not None else None
        )
        rs_vs_benchmark = row["stock_rs"] - benchmark_rs if row["stock_rs"] is not None else None

        signals.append({
            "Symbol": row["Symbol"],
            "Company": row["Company"],
            "Sector": row["Sector"],
            "Industry": row["Industry"],
            "Current_Price": row["Current_Price"],
            "ATH_Price_Flag": ath_price,
            "TTM_Net_Profit": row["ttm_net_profit"],
            "ATH_Profit_Flag": ath_profit,
            "Above_MA212_Flag": above_exit,
            "RS_Peer_Group": row["peer_group_label"],
            "RS_vs_Sector": round(rs_vs_sector, 2) if rs_vs_sector is not None else None,
            "RS_vs_Benchmark": round(rs_vs_benchmark, 2) if rs_vs_benchmark is not None else None,
            "Outperformance_Flag": outperformance,
            "TTM_Net_Sales": row["ttm_net_sales"],
            "ATH_Sales": row["max_annual_net_sales"],
            "ATH_Sales_Flag": ath_sales,
            "Signal": signal,
        })

    signals_df = pd.DataFrame(signals).reindex(columns=SIGNAL_COLUMNS)
    return {"signals": signals_df, "rejections": pd.DataFrame(rejects)}
