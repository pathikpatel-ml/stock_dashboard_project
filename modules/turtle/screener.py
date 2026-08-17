"""
Orchestration layer for the Turtle Strategy screener (docs/TURTLE_STRATEGY_PLAN.md).

Wires the pure functions in ``compute.py`` to real data:
  * OHLCV via ``modules.breakout.data_feed`` (reused — no new fetcher, per plan §3).
  * The pre-computed universe (Sector/Industry/Current_Price/MA200) from
    ``NSE_EQ_All_Stocks_Analysis.csv``.
  * Standalone TTM + historical-max-annual Net Profit/Net Sales from
    ``turtle_screener_fundamentals.csv`` (screener.in, via ``generate_turtle_fundamentals.py`` —
    see ``modules.turtle.standalone_fundamentals``). Both ATH_Profit_Flag and ATH_Sales_Flag are
    a direct TTM-vs-max-annual comparison now, no EPS/shares-outstanding proxy needed, since TTM
    and annual both come from the same screener.in table (same units, same standalone basis).
  * The benchmark (Nifty 500 proxy, LOCKED decision #2) via a direct yfinance call — NOT
    through ``data_feed``, which always appends ``.NS`` and is NSE-equity-only.
  * NSE sectoral index membership from ``nse_categories.csv`` — used to pick each stock's RS
    peer-group basket (its sectoral index if it's in one, e.g. NIFTY PHARMA, else the broad
    Sector column) -- see constants.py's ``BROAD_INDEX_TAGS`` note.

``run_pipeline`` is a two-pass batch: pass 1 fetches OHLCV once per symbol and computes each
stock's own relative strength; pass 2 derives the equal-weight RS peer-group basket from those
already-computed values (no redundant per-stock refetching), then finalizes flags/classification.
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


def fetch_benchmark_rs(session=None) -> float:
    """Fetch the benchmark's 52-week (weekly high-close) relative strength (LOCKED decision #2).

    Tries ``BENCHMARK_TICKER`` (Nifty 500 proxy for BSE 500), then each entry in
    ``BENCHMARK_FALLBACK_TICKERS``. Raises RuntimeError if none return usable data — per the
    locked decision, a benchmark fetch failure must stop the run, not silently degrade.
    """
    tickers = [C.BENCHMARK_TICKER] + list(C.BENCHMARK_FALLBACK_TICKERS)
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(
                period=C.DAILY_HISTORY_PERIOD, interval="1d", auto_adjust=False, timeout=20
            )
        except Exception:
            hist = None
        if hist is None or hist.empty or "Close" not in hist.columns:
            continue

        close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
        close.index = pd.DatetimeIndex(hist.index).tz_localize(None)
        rs = compute.relative_strength(close)
        if rs is not None:
            return rs

    raise RuntimeError(
        f"Could not fetch benchmark relative strength from any of {tickers}. "
        "Per the locked benchmark decision, refusing to silently fall back further."
    )


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

    ``pause_seconds`` (default 0, i.e. off) adds a light delay after each symbol's fetch —
    cheap insurance against Yahoo Finance throttling across the ~2,365-symbol full universe.
    Left at 0 for tests, which stub the fetch entirely and don't need pacing.
    """
    fundamentals_lookup = build_fundamentals_lookup(fundamentals_df)
    categories_lookup = build_categories_lookup(categories_df)
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

    signals = []
    for row in per_symbol:
        sector_rs = _leave_one_out_group_rs(row["peer_group_key"], row["stock_rs"])

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
