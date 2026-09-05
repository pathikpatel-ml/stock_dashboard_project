#!/usr/bin/env python
"""
One-time historical backfill of Turtle Quant BUY/SELL transition events.

Computes each stock's FULL available weekly price history (yfinance 'max' period) through our
own compute.py classification logic, week by week, and records every genuine BUY/SELL
transition into turtlequant_signal_transitions -- the same table the daily
generate_turtlequant_signals.py job appends to incrementally going forward.

IMPORTANT: this is NOT a reproduction of any external indicator's historical output. There is
no source formula available for the original "TQ:W52" TradingView indicator (see
modules/turtlequant/constants.py's module docstring) -- this walks our OWN reconstructed
formula backward through time. Confirmed with the user 2026-09-05: dates from this backfill
will likely differ from a manually-read TradingView chart using the real indicator; the value
here is an internally-consistent historical record using the same logic that already runs
forward from today, not a byte-for-byte match to any other source.

This only needs to run once (or whenever you want to recompute everything from scratch) -- it
does NOT touch turtlequant_signals_latest/_history (those stay exactly as the daily job leaves
them); it only writes to turtlequant_signal_transitions.

Usage
-----
    python backfill_turtlequant_transitions.py                # full universe
    python backfill_turtlequant_transitions.py --limit 25      # quick subset (testing)
"""
import argparse
import os
import time

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from database import market_data_writer as mdw
from modules.breakout import data_feed
from modules.turtlequant import compute as tqc
from modules.turtlequant import constants as C
from modules.turtlequant import screener as sc

REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
UNIVERSE_FILE = os.path.join(REPO_BASE_PATH, "NSE_EQ_All_Stocks_Analysis.csv")

_UNIVERSE_FROM_DB = {
    "symbol": "Symbol", "company_name": "Company Name", "sector": "Sector", "industry": "Industry",
    "current_price": "Current_Price",
}


def _from_postgres(table: str, rename_map: dict) -> pd.DataFrame:
    try:
        conn = mdw.get_connection()
        try:
            df = mdw.fetch_dataframe(conn, table)
        finally:
            conn.close()
        return df.rename(columns=rename_map) if not df.empty else df
    except Exception as exc:
        print(f"WARNING: Postgres read of {table} failed, falling back to local CSV: {exc}")
        return pd.DataFrame()


def load_universe() -> pd.DataFrame:
    df = _from_postgres("nse_universe", _UNIVERSE_FROM_DB)
    if df.empty:
        if not os.path.exists(UNIVERSE_FILE):
            raise SystemExit(f"Universe not found in Postgres (nse_universe) or at {UNIVERSE_FILE}.")
        df = pd.read_csv(UNIVERSE_FILE)
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    df = df.dropna(subset=["Symbol"])
    df = df[df["Symbol"].str.len() > 0]
    return df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)


def compute_symbol_history(symbol: str, index_weekly_close: pd.Series) -> pd.DataFrame:
    """Full historical weekly BUY/HOLD/SELL classification for ``symbol``, using its complete
    available weekly price history. Returns columns Signal_Date, Signal -- one row per week
    from MIN_WEEKLY_ROWS onward (not enough prior history to classify before that). Never
    raises -- empty DataFrame on any fetch/data issue.

    Indicator series (RSI/ADX/SuperTrend/rolling MAs) are each computed ONCE over the whole
    weekly series (all are causal/backward-looking by construction -- no lookahead bias), then
    indexed at each historical week position, rather than recomputed per week.
    """
    try:
        weekly = data_feed.get_weekly(symbol, period="max")
    except Exception:
        return pd.DataFrame(columns=["Signal_Date", "Signal"])
    if weekly is None or weekly.empty or len(weekly) < C.MIN_WEEKLY_ROWS:
        return pd.DataFrame(columns=["Signal_Date", "Signal"])

    high, low, close, volume = weekly["High"], weekly["Low"], weekly["Close"], weekly["Volume"]

    rs_long_series = tqc.relative_strength_vs_index_series(close, index_weekly_close, C.RS_LONG_TERM_WEEKS)
    rs_short_series = tqc.relative_strength_vs_index_series(close, index_weekly_close, C.RS_SHORT_TERM_WEEKS)
    adx_series = tqc.adx(high, low, close, C.DMI_LENGTH)
    rsi_series = tqc.rsi(close, C.RSI_LENGTH)
    supertrend_series = tqc.supertrend(high, low, close, C.SUPERTREND_ATR_LENGTH, C.SUPERTREND_ATR_FACTOR)
    price_ma_series = tqc.rolling_ma(close, C.MA_LENGTH)
    volume_ma_series = tqc.rolling_ma(volume, C.MA_LENGTH)

    rows = []
    for i in range(C.MIN_WEEKLY_ROWS, len(weekly)):
        rs_long = rs_long_series.iloc[i]
        rs_short = rs_short_series.iloc[i]
        adx_value = adx_series.iloc[i]
        rsi_value = rsi_series.iloc[i]
        supertrend_bullish = bool(supertrend_series.iloc[i] == 1)
        vma, pma = volume_ma_series.iloc[i], price_ma_series.iloc[i]
        volume_ok = bool(volume.iloc[i] > vma) if pd.notna(vma) else None
        price_ok = bool(close.iloc[i] > pma) if pd.notna(pma) else None

        signal = tqc.classify(
            float(rs_long) if pd.notna(rs_long) else None,
            float(rs_short) if pd.notna(rs_short) else None,
            float(adx_value) if pd.notna(adx_value) else None,
            volume_ok,
            price_ok,
            float(rsi_value) if pd.notna(rsi_value) else None,
            supertrend_bullish,
        )
        rows.append({"Signal_Date": weekly.index[i].strftime("%Y-%m-%d"), "Signal": signal})

    return pd.DataFrame(rows)


def extract_transitions(symbol: str, history: pd.DataFrame) -> list:
    """Walk a symbol's full chronological history and pull out only the genuine BUY/SELL
    transitions, via the same modules.turtlequant.compute.detect_transition the live daily
    job uses -- same rules, same semantics, just applied to the whole past at once."""
    transitions = []
    previous_signal, previous_date = None, None
    for row in history.itertuples():
        transition = tqc.detect_transition(previous_signal, previous_date, row.Signal, row.Signal_Date)
        if transition:
            transitions.append({
                "symbol": symbol,
                "transition_date": row.Signal_Date,
                "from_signal": transition["from_signal"],
                "to_signal": transition["to_signal"],
            })
        previous_signal, previous_date = row.Signal, row.Signal_Date
    return transitions


def main():
    ap = argparse.ArgumentParser(description="Backfill Turtle Quant historical BUY/SELL transitions")
    ap.add_argument("--limit", type=int, default=None, help="process only the first N symbols")
    ap.add_argument("--pause", type=float, default=0.15,
                     help="seconds to pause after each symbol's fetch (default: 0.15)")
    args = ap.parse_args()

    universe = load_universe()
    rows = universe.head(args.limit) if args.limit else universe
    print(f"Universe: {len(rows)} symbols (of {len(universe)} total).")

    index_weekly_close = sc._fetch_index_weekly_close(period="max")
    if index_weekly_close is None:
        raise SystemExit(f"Could not fetch comparative index ({C.COMPARATIVE_TICKER}) full history. Aborting.")
    print(f"Comparative index: {len(index_weekly_close)} weekly rows "
          f"({index_weekly_close.index[0].date()} to {index_weekly_close.index[-1].date()}).")

    all_transitions = []
    rejected = 0
    for i, (_, urow) in enumerate(rows.iterrows(), 1):
        symbol = str(urow.get("Symbol", "")).strip().upper()
        if not symbol:
            continue
        history = compute_symbol_history(symbol, index_weekly_close)
        if history.empty:
            rejected += 1
        else:
            all_transitions.extend(extract_transitions(symbol, history))

        if args.pause:
            time.sleep(args.pause)
        if i % 100 == 0:
            print(f"  backfill: processed {i}/{len(rows)} symbols, "
                  f"{len(all_transitions)} transitions found so far, {rejected} rejected")

    print(f"\nProcessed {len(rows)} symbols. Rejected (insufficient history): {rejected}. "
          f"Total transitions found: {len(all_transitions)}.")

    if not all_transitions:
        print("No transitions to write.")
        return

    transitions_df = pd.DataFrame(all_transitions)
    counts = transitions_df["to_signal"].value_counts().to_dict()
    print(f"  -> BUY events: {counts.get('BUY', 0)}  SELL events: {counts.get('SELL', 0)}")

    try:
        conn = mdw.get_connection()
        try:
            n = mdw.upsert_dataframe(
                conn, "turtlequant_signal_transitions", transitions_df,
                conflict_columns=["symbol", "transition_date"], touch_updated_at=False,
            )
            print(f"DB: turtlequant_signal_transitions upserted {n} rows")
        finally:
            conn.close()
    except Exception as exc:
        print(f"WARNING: Postgres write failed: {exc}")


if __name__ == "__main__":
    main()
