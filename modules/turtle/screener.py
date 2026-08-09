"""
Orchestration layer for the Turtle Strategy screener (docs/TURTLE_STRATEGY_PLAN.md).

Wires the pure functions in ``compute.py`` to real data:
  * OHLCV via ``modules.breakout.data_feed`` (reused — no new fetcher, per plan §3).
  * The pre-computed universe (Sector/Industry/Current_Price/MA200/TTM profit pieces) from
    ``NSE_EQ_All_Stocks_Analysis.csv``.
  * Historical EPS/sales from ``stock_fundamentals_yearly.csv``.
  * The benchmark (Nifty 500 proxy, LOCKED decision #2) via a direct yfinance call — NOT
    through ``data_feed``, which always appends ``.NS`` and is NSE-equity-only.

``run_pipeline`` is a two-pass batch: pass 1 fetches OHLCV once per symbol and computes each
stock's own relative strength; pass 2 derives the equal-weight sector RS basket from those
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
    "RS_vs_Sector", "RS_vs_Benchmark", "Outperformance_Flag", "ATH_Sales", "ATH_Sales_Flag", "Signal",
]


def fetch_benchmark_rs(session=None) -> float:
    """Fetch the benchmark's 365-day relative strength (LOCKED decision #2).

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


def _parse_ttm_profit(latest_quarter_profit, last_3q_profits_str) -> Optional[float]:
    """Sum Latest Quarter Profit + Last 3Q Profits (a comma-separated string) into TTM profit."""
    if latest_quarter_profit is None or pd.isna(latest_quarter_profit):
        return None
    total = float(latest_quarter_profit)
    if last_3q_profits_str is not None and not pd.isna(last_3q_profits_str):
        for part in str(last_3q_profits_str).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                total += float(part)
            except ValueError:
                continue
    return total


def build_fundamentals_lookup(fundamentals_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """``stock_fundamentals_yearly.csv`` (ticker, year, eps, sales, ...) -> per-ticker lookup:
    ``max_eps`` / ``max_sales`` (all-time highs, for ATH_Profit_Flag / the displayed ATH_Sales
    column), plus ``latest_sales`` and ``max_sales_excl_latest`` (for ATH_Sales_Flag — see
    ``compute.ath_sales_flag`` for why this is a same-year comparison, unlike profit's TTM one).
    """
    if fundamentals_df is None or fundamentals_df.empty:
        return {}
    df = fundamentals_df.copy()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()

    result: Dict[str, Dict[str, float]] = {}
    for ticker, g in df.groupby("ticker"):
        g = g.dropna(subset=["year"]).sort_values("year")
        max_eps = g["eps"].max()
        max_sales = g["sales"].max()
        latest_sales = g["sales"].iloc[-1] if not g.empty else None
        prior_sales = g["sales"].iloc[:-1]
        max_sales_excl_latest = prior_sales.max() if not prior_sales.empty else None
        result[ticker] = {
            "max_eps": max_eps,
            "max_sales": max_sales,
            "latest_sales": latest_sales,
            "max_sales_excl_latest": max_sales_excl_latest,
        }
    return result


def _stock_price_history(symbol: str) -> Dict[str, Optional[object]]:
    """Fetch monthly + daily OHLCV for ``symbol`` via the reused breakout data_feed."""
    monthly = data_feed.get_monthly(symbol, period=C.MONTHLY_HISTORY_PERIOD)
    daily = data_feed.get_daily(symbol, period=C.DAILY_HISTORY_PERIOD)
    return {"monthly": monthly, "daily": daily}


def run_pipeline(
    universe_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame,
    benchmark_rs: float,
    limit: Optional[int] = None,
    verbose: bool = True,
    pause_seconds: float = 0.0,
) -> Dict[str, pd.DataFrame]:
    """Run the Turtle screen over ``universe_df`` (NSE_EQ_All_Stocks_Analysis.csv shape).

    Returns {"signals": df, "rejections": df}. A symbol is only rejected (skipped from
    ``signals``) when its OHLCV can't be fetched at all — everything else degrades to safe
    per-flag defaults (see compute.py) rather than dropping the row, since a stock missing
    e.g. fundamentals data can still be meaningfully scored on price-only signals.

    ``pause_seconds`` (default 0, i.e. off) adds a light delay after each symbol's fetch —
    cheap insurance against Yahoo Finance throttling across the ~2,365-symbol full universe.
    Left at 0 for tests, which stub the fetch entirely and don't need pacing.
    """
    fundamentals_lookup = build_fundamentals_lookup(fundamentals_df)
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
        #
        # NOT ath_profit_flag's shares-outstanding derivation, deliberately: Market_Cap only
        # refreshes weekly, and shares = market_cap / price is only valid when both come from
        # the SAME moment. Pairing a stale Market_Cap with today's live price doesn't recover
        # the real share count -- it silently drifts EPS with every price tick even when
        # profit and shares haven't actually changed. That's why csv_current_price (the CSV's
        # own matched price) is kept separate below and fed to ath_profit_flag specifically.
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
            "Market_Cap": urow.get("Market Cap"),
            "CSV_Current_Price": csv_current_price,  # same snapshot as Market_Cap -- see above
            "TTM_Net_Profit": _parse_ttm_profit(
                urow.get("Latest Quarter Profit (Cr)"), urow.get("Last 3Q Profits (Cr)")
            ),
            "historical_max_close": historical_max_close,
            "stock_rs": stock_rs,
            "max_eps": fundamentals.get("max_eps"),
            "max_sales": fundamentals.get("max_sales"),
            "latest_sales": fundamentals.get("latest_sales"),
            "max_sales_excl_latest": fundamentals.get("max_sales_excl_latest"),
        })

        if verbose and i % 100 == 0:
            print(f"  turtle: fetched {i}/{len(rows)} symbols")

    if not per_symbol:
        return {"signals": pd.DataFrame(columns=SIGNAL_COLUMNS), "rejections": pd.DataFrame(rejects)}

    fetched_df = pd.DataFrame(per_symbol)

    # Equal-weight sector RS basket, derived from the already-fetched stock_rs values — no
    # redundant refetching per sector member. Leave-one-out: each stock is compared against
    # the mean of its *peers*, excluding its own value, so it isn't compared against a
    # basket it belongs to (which biases small sectors and makes a single-member sector
    # structurally unable to outperform). sum/count are kept per sector so the per-stock
    # exclusion is O(1) instead of recomputing a mean per stock.
    sector_stats = (
        fetched_df.dropna(subset=["stock_rs"]).groupby("Sector")["stock_rs"].agg(["sum", "count"]).to_dict("index")
    )

    def _leave_one_out_sector_rs(sector, own_stock_rs):
        stats = sector_stats.get(sector)
        if stats is None or own_stock_rs is None or stats["count"] <= 1:
            return None  # undefined for a single-member sector (or no valid peers)
        return (stats["sum"] - own_stock_rs) / (stats["count"] - 1)

    signals = []
    for row in per_symbol:
        sector_rs = _leave_one_out_sector_rs(row["Sector"], row["stock_rs"])

        ath_price = compute.ath_price_flag(row["Current_Price"], row["historical_max_close"])
        # market_cap_price is the CSV's own price (same snapshot as Market_Cap), not the live
        # price -- see the comment above where CSV_Current_Price is captured. Using the live
        # price here would silently redefine "shares outstanding" every time the price ticks.
        ath_profit = compute.ath_profit_flag(
            row["TTM_Net_Profit"], row["Market_Cap"], row["CSV_Current_Price"], row["max_eps"]
        )
        above_exit = compute.above_exit_flag(row["Current_Price"], row["ExitMA"])
        outperformance = compute.outperformance_flag(row["stock_rs"], sector_rs, benchmark_rs)
        signal = compute.classify(ath_price, ath_profit, above_exit, outperformance)

        # Informational only -- NOT part of classify() (the locked 3-signal + exit-price
        # methodology is unchanged); mirrors the ATH_Profit_Flag/TTM_Net_Profit display pair.
        ath_sales = compute.ath_sales_flag(row["latest_sales"], row["max_sales_excl_latest"])

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
            "TTM_Net_Profit": row["TTM_Net_Profit"],
            "ATH_Profit_Flag": ath_profit,
            "Above_MA212_Flag": above_exit,
            "RS_vs_Sector": round(rs_vs_sector, 2) if rs_vs_sector is not None else None,
            "RS_vs_Benchmark": round(rs_vs_benchmark, 2) if rs_vs_benchmark is not None else None,
            "Outperformance_Flag": outperformance,
            "ATH_Sales": row["max_sales"],
            "ATH_Sales_Flag": ath_sales,
            "Signal": signal,
        })

    signals_df = pd.DataFrame(signals).reindex(columns=SIGNAL_COLUMNS)
    return {"signals": signals_df, "rejections": pd.DataFrame(rejects)}
