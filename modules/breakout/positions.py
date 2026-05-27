"""
Active-positions tracking (doc §9.1 Module 3) from a user-maintained CSV.

The app is read-only and executes no trades, so the user records the trades they actually
took in ``breakout_positions.csv``. This module reads that file and computes the live tracking
metrics: P&L %, T1 status, weekly 21-EMA, consecutive weekly closes below the EMA, risk-to-SL,
upside-to-T1, days held, and the colour-coded SL alert status (green/yellow/red).

Input CSV schema (one row per position):
    Symbol, Entry_Date, Entry_Price, Stop_Loss, Target_1, Quantity, Status, T1_Reached, Notes
    - Status    : OPEN | CLOSED
    - T1_Reached: Yes | No   (set Yes once you have booked 50% at Target 1)
"""
from __future__ import annotations

import os
from typing import List, Optional

import numpy as np
import pandas as pd

from . import constants as C
from . import data_feed
from . import trade_math as tm

REPO_BASE_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POSITIONS_FILE = os.path.join(REPO_BASE_PATH, "breakout_positions.csv")

POSITION_INPUT_COLUMNS = [
    "Symbol", "Entry_Date", "Entry_Price", "Stop_Loss", "Target_1",
    "Quantity", "Status", "T1_Reached", "Notes",
]


def load_positions(path: str = POSITIONS_FILE) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=POSITION_INPUT_COLUMNS)
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame(columns=POSITION_INPUT_COLUMNS)
    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    return df


def _sl_status(cmp: float, sl: float) -> str:
    """Green (safe) / Yellow (within 3% of SL) / Red (SL hit) — doc §9.1 Module 3."""
    if cmp <= sl:
        return "Red"
    if (cmp - sl) / cmp * 100.0 <= C.SL_YELLOW_PROXIMITY_PCT:
        return "Yellow"
    return "Green"


def track_positions(positions_df: pd.DataFrame, cmp_lookup=None) -> pd.DataFrame:
    """Compute live tracking metrics for each OPEN position.

    ``cmp_lookup`` optionally maps Symbol -> current price (for tests / offline). When omitted,
    CMP and the weekly 21-EMA are fetched from yfinance via ``data_feed``.
    """
    if positions_df is None or positions_df.empty:
        return pd.DataFrame()

    out: List[dict] = []
    today = pd.Timestamp.now().normalize()

    for _, row in positions_df.iterrows():
        symbol = str(row.get("Symbol", "")).upper().strip()
        if not symbol or str(row.get("Status", "OPEN")).upper() == "CLOSED":
            continue
        entry = float(row.get("Entry_Price", np.nan))
        sl = float(row.get("Stop_Loss", np.nan))
        t1 = float(row.get("Target_1", np.nan))
        entry_date = pd.to_datetime(row.get("Entry_Date"), errors="coerce")
        t1_reached_flag = str(row.get("T1_Reached", "No")).strip().lower() in ("yes", "true", "1")

        # Current price
        if cmp_lookup is not None and symbol in cmp_lookup:
            cmp = float(cmp_lookup[symbol])
        else:
            daily = data_feed.get_daily(symbol)
            cmp = float(daily["Close"].iloc[-1]) if daily is not None and not daily.empty else np.nan

        # Weekly 21-EMA trailing context (only meaningful after T1 reached)
        ema_val, consec_below, exit_signal = np.nan, 0, False
        weekly = None if cmp_lookup is not None else data_feed.get_weekly(symbol)
        if weekly is not None and not weekly.empty:
            st = tm.evaluate_weekly_trailing(weekly["Close"].to_numpy())
            ema_val, consec_below, exit_signal = st.ema, st.consecutive_below, st.exit_signal

        pnl_pct = (cmp - entry) / entry * 100.0 if entry else np.nan
        risk_to_sl = (cmp - sl) / cmp * 100.0 if cmp else np.nan
        upside_to_t1 = (t1 - cmp) / cmp * 100.0 if cmp else np.nan
        days_held = int((today - entry_date).days) if pd.notna(entry_date) else None

        if t1_reached_flag:
            t1_status = "Partially Exited"
        elif pd.notna(cmp) and cmp >= t1:
            t1_status = "Reached"
        else:
            t1_status = "Not Reached"

        out.append(
            {
                "Symbol": symbol,
                "Entry Date": entry_date.strftime("%Y-%m-%d") if pd.notna(entry_date) else "N/A",
                "Entry Price": round(entry, 2) if pd.notna(entry) else None,
                "Current Price": round(cmp, 2) if pd.notna(cmp) else None,
                "Stop Loss": round(sl, 2) if pd.notna(sl) else None,
                "Target 1": round(t1, 2) if pd.notna(t1) else None,
                "T1 Status": t1_status,
                "21 EMA (Weekly)": round(ema_val, 2) if pd.notna(ema_val) else None,
                "Consec Below EMA": consec_below if t1_reached_flag else 0,
                "EMA Exit Signal": "Yes" if (exit_signal and t1_reached_flag) else "No",
                "P&L %": round(pnl_pct, 2) if pd.notna(pnl_pct) else None,
                "Risk to SL %": round(risk_to_sl, 2) if pd.notna(risk_to_sl) else None,
                "Upside to T1 %": round(upside_to_t1, 2) if pd.notna(upside_to_t1) else None,
                "Days Held": days_held,
                "SL Status": _sl_status(cmp, sl) if (pd.notna(cmp) and pd.notna(sl)) else "N/A",
            }
        )
    return pd.DataFrame(out)


def positions_template() -> pd.DataFrame:
    """A starter positions file with the header and one illustrative (CLOSED) example row."""
    return pd.DataFrame(
        [
            {
                "Symbol": "EXAMPLE", "Entry_Date": "2025-01-31", "Entry_Price": 226.0,
                "Stop_Loss": 212.85, "Target_1": 290.0, "Quantity": 100,
                "Status": "CLOSED", "T1_Reached": "Yes",
                "Notes": "Illustrative row — replace with your real positions or delete.",
            }
        ],
        columns=POSITION_INPUT_COLUMNS,
    )
