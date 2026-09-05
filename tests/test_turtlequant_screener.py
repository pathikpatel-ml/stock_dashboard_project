"""
End-to-end-style test of the Turtle Quant screening pipeline (modules/turtlequant/screener.py),
mirroring tests/test_turtle_screener.py's monkeypatch style: no live network, weekly OHLCV is
stubbed via monkeypatching modules.breakout.data_feed.get_weekly and
modules.turtlequant.screener._fetch_index_weekly_close.

Symbol design (deterministic by construction):
  - BUYSTOCK  -> BUY  (steady strong uptrend, far outperforming the index, rising volume)
  - SELLSTOCK -> SELL (steady downtrend -- SuperTrend bearish alone is enough)
  - HOLDSTOCK -> HOLD (steady uptrend but underperforming the index on both RS windows --
                        RS negative but not past the -0.25 exit threshold)
  - REJECT_NODATA  -> rejected, reason "no_weekly_data" (fetch returns None)
  - REJECT_SHORT   -> rejected, reason "insufficient_weekly_data" (fewer than MIN_WEEKLY_ROWS)

All series use 81 weekly points (index 0..80) at exactly 7-day (Monday) spacing, so "52 weeks
before the latest point" lands exactly on index 28, and "13 weeks before" on index 67 -- see
tests/test_turtlequant_engine.py::test_relative_strength_vs_index_known_ratio for the same
alignment fact used directly.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.breakout import data_feed
from modules.turtlequant import screener as sc

N = 81


def _linear(start, end, n=N):
    step = (end - start) / (n - 1)
    return [start + step * i for i in range(n)]


def _weekly_df(closes, volumes=None):
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=len(closes), freq="W-MON")
    if volumes is None:
        volumes = [1_000_000] * len(closes)
    return pd.DataFrame(
        {"High": closes, "Low": closes, "Close": closes, "Volume": volumes}, index=dates
    )


def _weekly_close_series(closes):
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=len(closes), freq="W-MON")
    return pd.Series(closes, index=dates)


INDEX_WEEKLY_CLOSE = _weekly_close_series(_linear(100, 160))

WEEKLY = {
    "BUYSTOCK": _weekly_df(_linear(100, 400), volumes=_linear(100_000, 500_000)),
    "SELLSTOCK": _weekly_df(_linear(400, 100)),
    "HOLDSTOCK": _weekly_df(_linear(100, 140)),
    "REJECT_SHORT": _weekly_df(_linear(100, 120, n=20)),  # < MIN_WEEKLY_ROWS (60)
    # REJECT_NODATA: no entry at all -> fake_get_weekly returns None.
}

UNIVERSE = pd.DataFrame([
    {"Symbol": "BUYSTOCK", "Company Name": "Buy Co", "Sector": "Alpha", "Industry": "Widgets"},
    {"Symbol": "SELLSTOCK", "Company Name": "Sell Co", "Sector": "Alpha", "Industry": "Widgets"},
    {"Symbol": "HOLDSTOCK", "Company Name": "Hold Co", "Sector": "Beta", "Industry": "Gadgets"},
    {"Symbol": "REJECT_SHORT", "Company Name": "Short Co", "Sector": "Beta", "Industry": "Gadgets"},
    {"Symbol": "REJECT_NODATA", "Company Name": "No Data Co", "Sector": "Beta", "Industry": "Gadgets"},
])


def _fake_get_weekly(symbol, period=None, use_cache=True):
    return WEEKLY.get(symbol)


def _fake_fetch_index_weekly_close(ticker=None):
    return INDEX_WEEKLY_CLOSE


@pytest.fixture(autouse=True)
def _patch_fetches(monkeypatch):
    monkeypatch.setattr(data_feed, "get_weekly", _fake_get_weekly)
    monkeypatch.setattr(sc, "_fetch_index_weekly_close", _fake_fetch_index_weekly_close)


def test_run_pipeline_schema_and_signal_domain():
    out = sc.run_pipeline(UNIVERSE, verbose=False, pause_seconds=0.0)
    signals = out["signals"]
    assert list(signals.columns) == sc.SIGNAL_COLUMNS
    assert set(signals["Signal"].unique()) <= {"BUY", "HOLD", "SELL"}


def test_run_pipeline_buy_sell_hold_by_construction():
    out = sc.run_pipeline(UNIVERSE, verbose=False, pause_seconds=0.0)
    signals = out["signals"].set_index("Symbol")

    assert signals.loc["BUYSTOCK", "Signal"] == "BUY"
    assert signals.loc["SELLSTOCK", "Signal"] == "SELL"
    assert signals.loc["HOLDSTOCK", "Signal"] == "HOLD"


def test_signal_date_is_the_weekly_candles_own_date_not_today():
    # Confirmed with the user 2026-09-05: signal_date must be the date of the weekly candle the
    # classification is actually based on, not "whatever day the batch job happened to run" --
    # otherwise re-running mid-week against the same still-forming candle would fabricate a new
    # dated row every day instead of updating that one week's row.
    out = sc.run_pipeline(UNIVERSE, verbose=False, pause_seconds=0.0)
    signals = out["signals"].set_index("Symbol")

    expected = WEEKLY["BUYSTOCK"].index[-1].strftime("%Y-%m-%d")
    assert signals.loc["BUYSTOCK", "Signal_Date"] == expected


def test_run_pipeline_rejects_missing_and_short_history():
    out = sc.run_pipeline(UNIVERSE, verbose=False, pause_seconds=0.0)
    rejections = out["rejections"].set_index("Symbol")["reason"].to_dict()

    assert rejections["REJECT_NODATA"] == "no_weekly_data"
    assert rejections["REJECT_SHORT"] == "insufficient_weekly_data"
    signals_symbols = set(out["signals"]["Symbol"])
    assert "REJECT_NODATA" not in signals_symbols
    assert "REJECT_SHORT" not in signals_symbols


def test_run_pipeline_raises_if_index_unfetchable(monkeypatch):
    monkeypatch.setattr(sc, "_fetch_index_weekly_close", lambda ticker=None: None)
    with pytest.raises(RuntimeError):
        sc.run_pipeline(UNIVERSE, verbose=False, pause_seconds=0.0)


def test_run_pipeline_limit_and_always_returns_dataframes():
    out = sc.run_pipeline(UNIVERSE, limit=1, verbose=False, pause_seconds=0.0)
    assert len(out["signals"]) + len(out["rejections"]) == 1
