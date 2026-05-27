"""
Full stock-screening pipeline for the Multi-Year Breakout strategy (doc §12.1, STEP 1-9),
plus the 52-week-high / 5-year-high scanners (doc §8) and the near-breakout watchlist.

``screen_symbol`` is the heart: given a symbol's price frames and its recent monthly delivery
percentages, it runs every filter in the documented order and returns one of:
    BREAKOUT  — latest monthly candle closed above a valid multi-year resistance, all filters
                + candle validation + R:R gate pass  -> goes to the Alerts Feed.
    WATCHLIST — valid multi-year resistance, price within 3% below it, not yet broken out.
    REJECT    — failed a filter (``reason`` says which step).

The per-symbol function is pure given its inputs (the price frames / delivery list), so it is
unit-tested with synthetic data; ``run_pipeline`` wires it to ``data_feed`` + the delivery store.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from . import constants as C
from . import data_feed
from . import trade_math as tm
from . import volume_trend as vt
from .candle_validation import validate_breakout_candle, detect_supply_absorption
from .resistance import detect_resistance, is_uptrend_dow
from .delivery_data import evaluate_delivery_filter


def tradingview_link(symbol: str) -> str:
    return f"https://www.tradingview.com/chart/?symbol=NSE:{symbol.upper()}"


# ---------------------------------------------------------------------------
# STEP 1 — Universe build (doc §12.1 STEP 1)
# ---------------------------------------------------------------------------
def universe_ok(monthly_df: pd.DataFrame, daily_df: Optional[pd.DataFrame]) -> Dict:
    """Penny / illiquid / recently-listed exclusion. Returns {ok, reason, cmp, avg_vol}."""
    if monthly_df is None or monthly_df.empty:
        return {"ok": False, "reason": "no_monthly_data", "cmp": None, "avg_vol": None}
    if len(monthly_df) < C.MIN_RESISTANCE_AGE_MONTHS:
        return {"ok": False, "reason": "listed_<5y", "cmp": None, "avg_vol": None}

    cmp = float(monthly_df["Close"].iloc[-1])
    if daily_df is not None and not daily_df.empty:
        cmp = float(daily_df["Close"].iloc[-1])
        avg_vol = float(daily_df["Volume"].tail(60).mean()) if "Volume" in daily_df else np.nan
    else:
        avg_vol = float(monthly_df["Volume"].tail(3).mean()) / 21.0 if "Volume" in monthly_df else np.nan

    if cmp < C.MIN_PRICE:
        return {"ok": False, "reason": f"penny_stock (CMP {cmp:.1f} < {C.MIN_PRICE})", "cmp": cmp, "avg_vol": avg_vol}
    if not np.isnan(avg_vol) and avg_vol < C.MIN_AVG_DAILY_VOLUME:
        return {"ok": False, "reason": f"illiquid (avg vol {avg_vol:.0f} < {C.MIN_AVG_DAILY_VOLUME})", "cmp": cmp, "avg_vol": avg_vol}
    return {"ok": True, "reason": "ok", "cmp": cmp, "avg_vol": avg_vol}


# ---------------------------------------------------------------------------
# Scanners (doc §8)
# ---------------------------------------------------------------------------
def is_52wk_high(daily_df: pd.DataFrame, proximity_pct: float = C.WEEK52_HIGH_PROXIMITY_PCT) -> bool:
    """Trading at or within ``proximity_pct`` of the 52-week high (last ~252 trading days)."""
    if daily_df is None or daily_df.empty:
        return False
    window = daily_df.tail(252)
    high_52w = float(window["High"].max())
    cmp = float(daily_df["Close"].iloc[-1])
    if high_52w <= 0:
        return False
    return cmp >= high_52w * (1.0 - proximity_pct / 100.0)


def is_5yr_high(monthly_df: pd.DataFrame, lookback: int = C.FIVE_YEAR_LOOKBACK_MONTHS) -> bool:
    """Latest close exceeds the highest high of the prior ``lookback`` months (doc §8.2)."""
    if monthly_df is None or len(monthly_df) < lookback:
        return False
    prior_high = float(monthly_df["High"].iloc[-lookback:-1].max())
    return float(monthly_df["Close"].iloc[-1]) > prior_high


# ---------------------------------------------------------------------------
# Core per-symbol screen (STEP 2-9)
# ---------------------------------------------------------------------------
def screen_symbol(
    symbol: str,
    company: str,
    monthly_df: pd.DataFrame,
    daily_df: Optional[pd.DataFrame] = None,
    delivery_pcts: Optional[Sequence[float]] = None,
    *,
    require_delivery: bool = True,
) -> Dict:
    """Run the full pipeline for one symbol. Returns a result dict (see module docstring)."""
    symbol = symbol.upper()
    result: Dict = {"Symbol": symbol, "Company": company, "status": "REJECT", "reason": "", "step": None}

    # STEP 1 — universe
    uni = universe_ok(monthly_df, daily_df)
    if not uni["ok"]:
        result.update(reason=uni["reason"], step=1)
        return result
    cmp = uni["cmp"]

    # STEP 3 coarse — ATH must not be far above the current ceiling (downtrend recovery)
    ath = float(monthly_df["High"].max())
    cur_ceiling = float(daily_df["High"].tail(252).max()) if (daily_df is not None and not daily_df.empty) else float(monthly_df["High"].iloc[-12:].max())
    if cur_ceiling > 0 and (ath - cur_ceiling) / cur_ceiling * 100.0 > C.ATH_REJECT_ABOVE_PCT:
        result.update(reason=f"downtrend_recovery (ATH {ath:.0f} > {C.ATH_REJECT_ABOVE_PCT}% above ceiling {cur_ceiling:.0f})", step=3)
        return result

    # STEP 3b — Dow Theory: reject Lower-High downtrends
    if not is_uptrend_dow(monthly_df):
        result.update(reason="lower_highs_downtrend", step=3)
        return result

    # STEP 4 — multi-year resistance detection
    res = detect_resistance(monthly_df, as_of_index=-1)
    if not res.valid:
        result.update(reason=f"resistance:{res.reason}", step=4)
        return result

    entry = float(monthly_df["Close"].iloc[-1])          # latest monthly close
    breakout_low = float(monthly_df["Low"].iloc[-1])
    breakout_vol = float(monthly_df["Volume"].iloc[-1]) if "Volume" in monthly_df else np.nan
    prior_vols = monthly_df["Volume"].iloc[:-1].tolist() if "Volume" in monthly_df else []
    distance_pct = tm.distance_to_breakout(cmp, res.resistance)

    # Common derived levels (used by both breakout & watchlist paths)
    sl = tm.stop_loss(breakout_low)
    t1 = tm.target_1(res.resistance, res.support)
    rr = tm.risk_reward(entry, sl, t1)

    # STEP 5 — volume trend
    monthly_vols = monthly_df["Volume"].tolist() if "Volume" in monthly_df else []
    vol_trend = vt.classify_volume_trend(monthly_vols)

    # STEP 6 — delivery (Smart Money)
    deliv_pass, deliv_reason, deliv_metrics = (True, "not_checked", {"latest": None, "rising": False})
    if delivery_pcts is not None and len(list(delivery_pcts)) > 0:
        deliv_pass, deliv_reason, deliv_metrics = evaluate_delivery_filter(delivery_pcts)
    elif require_delivery:
        deliv_pass, deliv_reason, deliv_metrics = (False, "no_delivery_data", {"latest": None, "rising": False})

    broke_out = entry > res.resistance

    # ---------------- Watchlist branch (not yet broken out) ----------------
    if not broke_out:
        if 0 < distance_pct <= C.NEAR_BREAKOUT_PROXIMITY_PCT:
            result.update(
                status="WATCHLIST",
                reason="near_breakout",
                CMP=round(cmp, 2),
                Resistance=res.resistance,
                Support=res.support,
                Range_Size=res.range_size,
                Range_Pct=round(res.range_size / res.support * 100.0, 2) if res.support else None,
                Distance_to_Breakout_Pct=distance_pct,
                Resistance_Age_Years=res.age_years,
                Resistance_Tests=res.n_tests,
                Volume_Trend=vol_trend,
                Delivery_Pct=deliv_metrics.get("latest"),
                Priority_Score=tm.priority_score(res.age_years, deliv_metrics.get("latest") or 0.0, distance_pct),
                Chart_Link=tradingview_link(symbol),
            )
            return result
        result.update(reason=f"not_near_breakout (distance {distance_pct:.1f}%)", step=2)
        return result

    # ---------------- Breakout branch ----------------
    if vol_trend == vt.DECLINING:
        result.update(reason="volume_declining", step=5)
        return result
    if not deliv_pass:
        result.update(reason=f"delivery:{deliv_reason}", step=6)
        return result

    # STEP 7 — breakout candle validation
    candle = validate_breakout_candle(
        open_=float(monthly_df["Open"].iloc[-1]),
        high=float(monthly_df["High"].iloc[-1]),
        low=breakout_low,
        close=entry,
        resistance=res.resistance,
        breakout_volume=breakout_vol,
        prior_volumes=prior_vols,
    )
    if not candle.is_valid:
        result.update(reason=f"candle:{';'.join(candle.reasons)}", step=7)
        return result

    # STEP 8 — Risk:Reward gate
    if not tm.passes_rr_gate(rr):
        result.update(reason=f"rr_below_gate ({rr})", step=8)
        return result

    # Bonus — supply absorption
    sa = detect_supply_absorption(monthly_df.iloc[:-1], res.resistance)

    # STEP 9 — alert
    result.update(
        status="BREAKOUT",
        reason="ok",
        step=9,
        CMP=round(cmp, 2),
        Entry_Price=round(entry, 2),
        Stop_Loss=sl,
        Target_1=t1,
        Risk_Reward=rr,
        Resistance=res.resistance,
        Support=res.support,
        Range_Size=res.range_size,
        Resistance_Age_Years=res.age_years,
        Resistance_Tests=res.n_tests,
        ATH=res.ath,
        Delivery_Pct=deliv_metrics.get("latest"),
        Delivery_Rising="Yes" if deliv_metrics.get("rising") else "No",
        Volume_Spike_x=candle.volume_spike_ratio,
        Volume_Trend=vol_trend,
        Candle_Quality=candle.quality,
        Candle_Flags=";".join(candle.flags),
        Supply_Absorption="Yes" if sa.present else "No",
        Chart_Link=tradingview_link(symbol),
    )
    return result


# ---------------------------------------------------------------------------
# Pipeline driver — wires screen_symbol to data_feed + the delivery store
# ---------------------------------------------------------------------------
SIGNAL_COLUMNS = [
    "Symbol", "Company", "Alert_Date", "CMP", "Entry_Price", "Stop_Loss", "Target_1",
    "Risk_Reward", "Resistance", "Support", "Range_Size", "Resistance_Age_Years",
    "Resistance_Tests", "ATH", "Delivery_Pct", "Delivery_Rising", "Volume_Spike_x",
    "Volume_Trend", "Candle_Quality", "Candle_Flags", "Supply_Absorption", "Chart_Link",
]
WATCHLIST_COLUMNS = [
    "Symbol", "Company", "CMP", "Resistance", "Distance_to_Breakout_Pct",
    "Resistance_Age_Years", "Resistance_Tests", "Support", "Range_Size", "Range_Pct",
    "Volume_Trend", "Delivery_Pct", "Priority_Score", "Chart_Link",
]


def _recent_delivery_for(symbol: str, monthly_store: pd.DataFrame, n: int = 6) -> List[float]:
    if monthly_store is None or monthly_store.empty:
        return []
    rows = monthly_store[monthly_store["Symbol"].astype(str).str.upper() == symbol.upper()]
    if rows.empty:
        return []
    rows = rows.sort_values("Month").tail(n)
    return [float(p) for p in rows["DeliveryPct"].tolist() if pd.notna(p)]


def run_pipeline(
    universe: pd.DataFrame,
    monthly_store: Optional[pd.DataFrame] = None,
    *,
    require_delivery: bool = True,
    limit: Optional[int] = None,
    verbose: bool = True,
) -> Dict[str, pd.DataFrame]:
    """Run the screen over ``universe`` (needs columns Symbol, Company Name).

    Returns {"signals": df, "watchlist": df, "rejections": df}. Fetches monthly/daily frames
    per symbol via ``data_feed`` and looks up recent delivery % from ``monthly_store``.
    """
    alert_date = pd.Timestamp.now().strftime("%Y-%m-%d")
    signals, watch, rejects = [], [], []
    rows = universe.head(limit) if limit else universe

    for i, (_, urow) in enumerate(rows.iterrows(), 1):
        symbol = str(urow.get("Symbol", "")).upper().strip()
        company = str(urow.get("Company Name", urow.get("Company", symbol)))
        if not symbol:
            continue
        try:
            monthly = data_feed.get_monthly(symbol)
            daily = data_feed.get_daily(symbol)
        except Exception as exc:  # network resilience
            rejects.append({"Symbol": symbol, "reason": f"fetch_error:{exc}", "step": 0})
            continue

        deliv = _recent_delivery_for(symbol, monthly_store)
        res = screen_symbol(symbol, company, monthly, daily, deliv, require_delivery=require_delivery)

        if res["status"] == "BREAKOUT":
            res["Alert_Date"] = alert_date
            signals.append(res)
        elif res["status"] == "WATCHLIST":
            watch.append(res)
        else:
            rejects.append({"Symbol": symbol, "reason": res.get("reason"), "step": res.get("step")})

        if verbose and i % 25 == 0:
            print(f"  screened {i}/{len(rows)} (signals={len(signals)}, watchlist={len(watch)})")

    signals_df = pd.DataFrame(signals)
    watch_df = pd.DataFrame(watch)
    if not signals_df.empty:
        signals_df = signals_df.reindex(columns=SIGNAL_COLUMNS)
    if not watch_df.empty:
        watch_df = watch_df.reindex(columns=WATCHLIST_COLUMNS).sort_values(
            "Priority_Score", ascending=False
        ).reset_index(drop=True)
    return {
        "signals": signals_df,
        "watchlist": watch_df,
        "rejections": pd.DataFrame(rejects),
    }
