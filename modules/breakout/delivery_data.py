"""
Delivery-volume ("Smart Money") data from the NSE Bhav Copy (doc §3.4, §10.2, §11.3).

NSE publishes a daily "Security-wise Deliverable Position" file
(``sec_bhavdata_full_<DDMMYYYY>.csv``) containing, per security:
    SYMBOL, SERIES, ..., TTL_TRD_QNTY, ..., DELIV_QTY, DELIV_PER

This module:
  * downloads that daily CSV (browser-like session + retries + mirror URLs),
  * parses the EQ-series rows into tidy daily delivery records,
  * persists a parsed daily file per date under ``data/delivery/``,
  * aggregates daily records to a volume-weighted monthly delivery % per symbol, and
  * applies the Filter-4/5 delivery rules.

The download functions touch the network and are exercised by the daily GitHub Action
(``download_delivery_data.py``); the parse/aggregate/filter functions are pure and unit-tested.
"""
from __future__ import annotations

import io
import os
import time
from datetime import date, datetime
from typing import List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import requests

from . import constants as C

# ---------------------------------------------------------------------------
# Storage layout
# ---------------------------------------------------------------------------
REPO_BASE_PATH = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DELIVERY_DIR = os.path.join(REPO_BASE_PATH, "data", "delivery")
MONTHLY_STORE = os.path.join(DELIVERY_DIR, "delivery_monthly.csv")
DAILY_FILE_TEMPLATE = "sec_deliv_{date_str}.csv"  # date_str = YYYYMMDD

# NSE mirror URLs for the full security-wise bhav-data file.
_BHAV_URLS = [
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv",
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv",
]
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}


def _strip_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).strip() for c in df.columns]
    return df


# ---------------------------------------------------------------------------
# Download (network) — used by the daily workflow
# ---------------------------------------------------------------------------
def download_bhavcopy(on_date: date, retries: int = 3, pause: float = 1.5) -> Optional[pd.DataFrame]:
    """Download and return the raw security-wise bhav-data frame for ``on_date``.

    Returns None on a market holiday / unavailable date. Uses a session that first warms
    up cookies from the NSE homepage, then tries each mirror URL with retries.
    """
    ddmmyyyy = on_date.strftime("%d%m%Y")
    session = requests.Session()
    session.headers.update(_HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=15)
    except Exception:
        pass  # cookie warm-up is best-effort

    for url_tmpl in _BHAV_URLS:
        url = url_tmpl.format(ddmmyyyy=ddmmyyyy)
        for attempt in range(retries):
            try:
                resp = session.get(url, timeout=30)
                if resp.status_code == 200 and resp.content and b"SYMBOL" in resp.content[:200]:
                    df = pd.read_csv(io.StringIO(resp.content.decode("utf-8", "ignore")))
                    return _strip_cols(df)
            except Exception:
                pass
            time.sleep(pause * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Parse (pure)
# ---------------------------------------------------------------------------
def parse_delivery(raw: pd.DataFrame, series: str = "EQ") -> pd.DataFrame:
    """Tidy the raw bhav-data frame into daily delivery records for the given ``series``.

    Output columns: Symbol, Date, TotalVolume, DeliveryQty, DeliveryPct.
    DELIV_QTY / DELIV_PER are '-' for non-deliverable series; those rows are coerced to NaN.
    """
    if raw is None or raw.empty:
        return pd.DataFrame(columns=["Symbol", "Date", "TotalVolume", "DeliveryQty", "DeliveryPct"])

    df = _strip_cols(raw.copy())
    if "SERIES" in df.columns:
        df = df[df["SERIES"].astype(str).str.strip() == series]
    if df.empty:
        return pd.DataFrame(columns=["Symbol", "Date", "TotalVolume", "DeliveryQty", "DeliveryPct"])

    def _num(col):
        return pd.to_numeric(
            df[col].astype(str).str.strip().replace({"-": np.nan, "": np.nan}), errors="coerce"
        )

    out = pd.DataFrame(
        {
            "Symbol": df["SYMBOL"].astype(str).str.strip().str.upper(),
            "Date": pd.to_datetime(df["DATE1"].astype(str).str.strip(), errors="coerce", dayfirst=True),
            "TotalVolume": _num("TTL_TRD_QNTY"),
            "DeliveryQty": _num("DELIV_QTY"),
            "DeliveryPct": _num("DELIV_PER"),
        }
    )
    return out.dropna(subset=["Symbol", "Date"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Persist daily parsed file
# ---------------------------------------------------------------------------
def save_daily(parsed: pd.DataFrame, on_date: date, directory: str = DELIVERY_DIR) -> str:
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, DAILY_FILE_TEMPLATE.format(date_str=on_date.strftime("%Y%m%d")))
    parsed.to_csv(path, index=False)
    return path


def load_all_daily(directory: str = DELIVERY_DIR) -> pd.DataFrame:
    """Concatenate every stored daily parsed file into one frame."""
    if not os.path.isdir(directory):
        return pd.DataFrame(columns=["Symbol", "Date", "TotalVolume", "DeliveryQty", "DeliveryPct"])
    frames = []
    for name in sorted(os.listdir(directory)):
        if name.startswith("sec_deliv_") and name.endswith(".csv"):
            try:
                frames.append(pd.read_csv(os.path.join(directory, name), parse_dates=["Date"]))
            except Exception:
                continue
    if not frames:
        return pd.DataFrame(columns=["Symbol", "Date", "TotalVolume", "DeliveryQty", "DeliveryPct"])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Aggregate (pure) — daily -> volume-weighted monthly delivery %
# ---------------------------------------------------------------------------
def aggregate_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    """Volume-weighted monthly delivery % per symbol.

    Monthly DeliveryPct = sum(DeliveryQty) / sum(TotalVolume) * 100 over the month — the
    accurate aggregation (a simple mean of daily % would over-weight thin days).

    Output columns: Symbol, Month (YYYY-MM), DeliveryPct, TotalDelivQty, TotalTrdQty, Days.
    """
    cols = ["Symbol", "Month", "DeliveryPct", "TotalDelivQty", "TotalTrdQty", "Days"]
    if daily is None or daily.empty:
        return pd.DataFrame(columns=cols)

    d = daily.copy()
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    d = d.dropna(subset=["Date", "Symbol"])
    d["Month"] = d["Date"].dt.strftime("%Y-%m")

    grp = d.groupby(["Symbol", "Month"], as_index=False).agg(
        TotalDelivQty=("DeliveryQty", "sum"),
        TotalTrdQty=("TotalVolume", "sum"),
        Days=("Date", "count"),
    )
    grp["DeliveryPct"] = np.where(
        grp["TotalTrdQty"] > 0,
        (grp["TotalDelivQty"] / grp["TotalTrdQty"] * 100.0).round(2),
        np.nan,
    )
    return grp[cols].sort_values(["Symbol", "Month"]).reset_index(drop=True)


def update_monthly_store(daily: pd.DataFrame, store_path: str = MONTHLY_STORE) -> pd.DataFrame:
    """Rebuild the consolidated monthly store from all daily files and persist it."""
    monthly = aggregate_monthly(daily)
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    monthly.to_csv(store_path, index=False)
    return monthly


def load_monthly_store(store_path: str = MONTHLY_STORE) -> pd.DataFrame:
    if os.path.exists(store_path):
        try:
            return pd.read_csv(store_path)
        except Exception:
            pass
    return pd.DataFrame(columns=["Symbol", "Month", "DeliveryPct", "TotalDelivQty", "TotalTrdQty", "Days"])


# ---------------------------------------------------------------------------
# Trend + filter (pure) — doc §3.4 / §15 #5,#6
# ---------------------------------------------------------------------------
def delivery_rising(monthly_pcts: Sequence[float]) -> bool:
    """True when delivery % is non-decreasing across the lookback (Smart-Money accumulation)."""
    s = [p for p in monthly_pcts if p is not None and not (isinstance(p, float) and np.isnan(p))]
    if len(s) < 2:
        return False
    return all(b >= a - 1e-9 for a, b in zip(s, s[1:]))


def evaluate_delivery_filter(
    monthly_pcts: Sequence[float],
    lookback: int = C.DELIVERY_LOOKBACK_MONTHS,
) -> Tuple[bool, str, dict]:
    """Apply Filter 4/5 to a symbol's recent monthly delivery % series (oldest -> newest).

    Returns (passes, reason, metrics). Rules (doc §3.4):
      * latest (breakout-month) delivery % must be >= 50%.
      * < 30% latest  -> hard reject.
      * all of the last ``lookback`` months < 40% -> reject (consistently weak).
      * rising trend over the lookback is reported as a bonus flag (not required).
    """
    vals = [float(p) for p in monthly_pcts
            if p is not None and not (isinstance(p, float) and np.isnan(p))]
    metrics = {"latest": None, "rising": False, "n_months": len(vals)}
    if not vals:
        return False, "no_delivery_data", metrics

    latest = vals[-1]
    recent = vals[-lookback:]
    rising = delivery_rising(recent)
    metrics.update({"latest": round(latest, 2), "rising": rising})

    if latest < C.DELIVERY_HARD_REJECT_PCT:
        return False, f"hard_reject_delivery ({latest:.1f}% < {C.DELIVERY_HARD_REJECT_PCT}%)", metrics
    if all(v < C.DELIVERY_WEAK_REJECT_PCT for v in recent):
        return False, f"consistently_weak_delivery (all < {C.DELIVERY_WEAK_REJECT_PCT}%)", metrics
    if latest < C.DELIVERY_MIN_PCT:
        return False, f"below_min_delivery ({latest:.1f}% < {C.DELIVERY_MIN_PCT}%)", metrics
    return True, "ok", metrics
