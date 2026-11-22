"""
Tests for the Turtle Quant screening pipeline (modules/turtlequant/screener.py).

2026-10-02: the original weekly RS/SuperTrend/ADX/RSI technical-signal system was removed per
explicit user request. What's left is a pure, network-free fundamental quality/valuation screen
-- these tests no longer monkeypatch any fetch, since run_pipeline now does no I/O at all.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.turtlequant import screener as sc

UNIVERSE = pd.DataFrame([
    {"Symbol": "BUYSTOCK", "Company Name": "Buy Co", "Sector": "Alpha", "Industry": "Widgets", "Current_Price": 400.0},
    {"Symbol": "HOLDSTOCK", "Company Name": "Hold Co", "Sector": "Beta", "Industry": "Gadgets", "Current_Price": 140.0},
])


def test_run_pipeline_schema():
    out = sc.run_pipeline(UNIVERSE, verbose=False)
    signals = out["signals"]
    assert list(signals.columns) == sc.SIGNAL_COLUMNS
    assert len(signals) == 2
    assert out["rejections"].empty


def test_run_pipeline_passes_through_universe_fields():
    out = sc.run_pipeline(UNIVERSE, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["Company"] == "Buy Co"
    assert row["Industry"] == "Widgets"
    assert row["Current_Price"] == pytest.approx(400.0)


def test_run_pipeline_limit():
    out = sc.run_pipeline(UNIVERSE, limit=1, verbose=False)
    assert len(out["signals"]) == 1


# ---------------------------------------------------------------------------
# Screener.in Sector/Broad_Sector preference (2026-09-24) -- same rule as
# modules/turtle/screener.py::run_pipeline, applied here so both tabs are consistent.
# ---------------------------------------------------------------------------
def test_run_pipeline_prefers_screener_sector_over_universe_yahoo_tag():
    fundamentals = pd.DataFrame([
        {"Symbol": "BUYSTOCK", "Broad_Sector": "Energy", "Sector": "Oil, Gas & Consumable Fuels"},
    ])
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=fundamentals, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["Sector"] == "Oil, Gas & Consumable Fuels"
    assert row["Broad_Sector"] == "Energy"


def test_run_pipeline_falls_back_to_universe_sector_when_screener_has_none():
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=None, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["Sector"] == "Alpha"  # the universe CSV's own Yahoo-style tag
    assert pd.isna(row["Broad_Sector"]) or row["Broad_Sector"] is None


def test_run_pipeline_falls_back_per_symbol_when_screener_has_only_some():
    # Only BUYSTOCK has screener.in data -- HOLDSTOCK must still fall back to its universe tag.
    fundamentals = pd.DataFrame([
        {"Symbol": "BUYSTOCK", "Broad_Sector": "Energy", "Sector": "Oil, Gas & Consumable Fuels"},
    ])
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=fundamentals, verbose=False)
    signals = out["signals"].set_index("Symbol")
    assert signals.loc["BUYSTOCK", "Sector"] == "Oil, Gas & Consumable Fuels"
    assert signals.loc["HOLDSTOCK", "Sector"] == "Beta"


# ---------------------------------------------------------------------------
# 2026-11-22 (per explicit user request): the 11 fundamental quality/valuation metrics (22
# columns) that used to be threaded through here were removed entirely from Turtle Quant --
# never displayed on this tab's dashboard table anyway. Turtle Strategy/turtle_fundamentals
# still computes and stores them, untouched; their own tests cover that path.
# ---------------------------------------------------------------------------
# ATH Profit/Sales (2026-11-22, per explicit user request) -- same shared
# turtle_fundamentals-derived computation Turtle Strategy's own table uses
# (modules/turtle/compute.py::ath_profit_flag/ath_sales_flag), not a cross-tab dependency on
# Turtle Strategy's own output table.
# ---------------------------------------------------------------------------
def test_run_pipeline_computes_ath_profit_and_sales_flags_true():
    fundamentals = pd.DataFrame([{
        "Symbol": "BUYSTOCK",
        "TTM_Net_Profit": 120.0, "Max_Annual_Net_Profit": 100.0,   # TTM >= max annual -> True
        "TTM_Net_Sales": 500.0, "Max_Annual_Net_Sales": 500.0,     # equal -> True
    }])
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=fundamentals, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert row["TTM_Net_Profit"] == pytest.approx(120.0)
    assert bool(row["ATH_Profit_Flag"]) is True
    assert row["TTM_Net_Sales"] == pytest.approx(500.0)
    assert bool(row["ATH_Sales_Flag"]) is True


def test_run_pipeline_computes_ath_profit_and_sales_flags_false():
    fundamentals = pd.DataFrame([{
        "Symbol": "BUYSTOCK",
        "TTM_Net_Profit": 80.0, "Max_Annual_Net_Profit": 100.0,   # below max -> False
        "TTM_Net_Sales": 400.0, "Max_Annual_Net_Sales": 500.0,
    }])
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=fundamentals, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert bool(row["ATH_Profit_Flag"]) is False
    assert bool(row["ATH_Sales_Flag"]) is False


def test_run_pipeline_ath_flags_false_when_no_fundamentals():
    out = sc.run_pipeline(UNIVERSE, fundamentals_df=None, verbose=False)
    row = out["signals"].set_index("Symbol").loc["BUYSTOCK"]
    assert pd.isna(row["TTM_Net_Profit"])
    assert bool(row["ATH_Profit_Flag"]) is False  # missing data -> False, same as compute.py's own convention
    assert bool(row["ATH_Sales_Flag"]) is False


def test_signal_columns_includes_ath_profit_and_sales():
    assert {"TTM_Net_Profit", "ATH_Profit_Flag", "TTM_Net_Sales", "ATH_Sales_Flag"} <= set(sc.SIGNAL_COLUMNS)


# ---------------------------------------------------------------------------
# fetch_nifty50_reference / compute_universe_drawdown (2026-11-22) -- the Nifty-50-anchored
# drawdown comparison. yfinance/data_feed are both stubbed -- no live network.
# ---------------------------------------------------------------------------
class _FakeHistory:
    def __init__(self, df):
        self._df = df

    def history(self, period=None, interval=None, auto_adjust=None, timeout=None):
        return self._df


def test_fetch_nifty50_reference_derives_from_live_ohlc(monkeypatch):
    ohlc = pd.DataFrame(
        {"High": [100, 105, 103], "Low": [90, 95, 98], "Close": [95, 97, 101]},
        index=pd.DatetimeIndex(["2026-01-01", "2026-01-05", "2026-11-20"]),
    )
    monkeypatch.setattr(sc.yf, "Ticker", lambda ticker: _FakeHistory(ohlc))

    ref = sc.fetch_nifty50_reference()

    assert ref["ath_price"] == 105
    assert ref["today_price"] == 101


def test_fetch_nifty50_reference_returns_none_on_fetch_exception(monkeypatch):
    def boom(ticker):
        raise RuntimeError("yfinance down")

    monkeypatch.setattr(sc.yf, "Ticker", boom)
    assert sc.fetch_nifty50_reference() is None


def test_fetch_nifty50_reference_returns_none_on_empty_history(monkeypatch):
    monkeypatch.setattr(sc.yf, "Ticker", lambda ticker: _FakeHistory(pd.DataFrame()))
    assert sc.fetch_nifty50_reference() is None


_NIFTY_REF = {
    "ath_price": 200.0, "ath_date": pd.Timestamp("2026-01-05").date(),
    "low_52wk_price": 150.0, "low_52wk_date": pd.Timestamp("2026-10-08").date(),
    "today_price": 190.0, "today_date": pd.Timestamp("2026-11-20").date(),
}


_FAKE_MONTHLY = pd.DataFrame(
    {"Close": [float(90 + i) for i in range(12)]},
    index=pd.date_range("2025-01-31", periods=12, freq="ME"),
)


def test_compute_universe_drawdown_builds_one_row_per_symbol(monkeypatch):
    def fake_get_daily(symbol, period=None):
        return pd.DataFrame(
            {"High": [100.0, 85.0, 92.0], "Low": [95.0, 80.0, 88.0], "Close": [98.0, 82.0, 90.0]},
            index=pd.DatetimeIndex(["2026-01-05", "2026-10-08", "2026-11-20"]),
        )

    monkeypatch.setattr(sc.data_feed, "get_daily", fake_get_daily)
    monkeypatch.setattr(sc.data_feed, "get_monthly", lambda symbol, period=None: _FAKE_MONTHLY)

    result = sc.compute_universe_drawdown(UNIVERSE, _NIFTY_REF, verbose=False)

    assert list(result.columns) == ["Symbol", sc.PRICE_ATH_FIELD] + list(sc.bd.DRAWDOWN_FIELDS)
    assert set(result["Symbol"]) == {"BUYSTOCK", "HOLDSTOCK"}
    row = result.set_index("Symbol").loc["BUYSTOCK"]
    assert row["stock_ath_return_pct"] == pytest.approx(-10.0)
    # daily Close max=98, monthly Close max=101 -> historical_max=101; current=90 (last daily
    # Close) is well below 101*0.95=95.95
    assert bool(row[sc.PRICE_ATH_FIELD]) is False


def test_compute_universe_drawdown_none_nifty_ref_gives_all_none_rows(monkeypatch):
    monkeypatch.setattr(sc.data_feed, "get_daily", lambda symbol, period=None: None)
    monkeypatch.setattr(sc.data_feed, "get_monthly", lambda symbol, period=None: None)
    result = sc.compute_universe_drawdown(UNIVERSE, None, verbose=False)
    for field in sc.bd.DRAWDOWN_FIELDS:
        assert result[field].isna().all()
    assert result[sc.PRICE_ATH_FIELD].isna().all()


def test_compute_universe_drawdown_fetch_failure_degrades_to_none_not_dropped(monkeypatch):
    def boom(symbol, period=None):
        raise RuntimeError("yfinance hung")

    monkeypatch.setattr(sc.data_feed, "get_daily", boom)
    monkeypatch.setattr(sc.data_feed, "get_monthly", boom)
    result = sc.compute_universe_drawdown(UNIVERSE, _NIFTY_REF, verbose=False)
    assert len(result) == 2  # both symbols still present, just with None fields
    assert result["stock_ath_return_pct"].isna().all()
    assert result[sc.PRICE_ATH_FIELD].isna().all()


def test_compute_universe_drawdown_respects_limit(monkeypatch):
    monkeypatch.setattr(sc.data_feed, "get_daily", lambda symbol, period=None: None)
    monkeypatch.setattr(sc.data_feed, "get_monthly", lambda symbol, period=None: None)
    result = sc.compute_universe_drawdown(UNIVERSE, _NIFTY_REF, limit=1, verbose=False)
    assert len(result) == 1


def test_compute_universe_drawdown_empty_universe_returns_empty_with_schema():
    result = sc.compute_universe_drawdown(pd.DataFrame(columns=["Symbol"]), _NIFTY_REF, verbose=False)
    assert result.empty
    assert list(result.columns) == ["Symbol", sc.PRICE_ATH_FIELD] + list(sc.bd.DRAWDOWN_FIELDS)


# ---------------------------------------------------------------------------
# _compute_ath_price_flag (2026-11-22) -- same formula/threshold as Turtle Strategy's own
# ath_price_flag, fed by the stock's own daily+monthly Close history.
# ---------------------------------------------------------------------------
def test_compute_ath_price_flag_true_within_5_percent():
    daily = pd.DataFrame({"Close": [95.0, 97.0, 100.0]}, index=pd.date_range("2026-11-01", periods=3))
    assert sc._compute_ath_price_flag(daily, _FAKE_MONTHLY) is True  # monthly max 101, 100 >= 101*0.95


def test_compute_ath_price_flag_false_far_from_ath():
    daily = pd.DataFrame({"Close": [95.0, 97.0, 80.0]}, index=pd.date_range("2026-11-01", periods=3))
    assert sc._compute_ath_price_flag(daily, _FAKE_MONTHLY) is False


def test_compute_ath_price_flag_none_when_daily_missing():
    assert sc._compute_ath_price_flag(None, _FAKE_MONTHLY) is None


def test_compute_ath_price_flag_none_when_monthly_missing():
    daily = pd.DataFrame({"Close": [100.0]}, index=pd.date_range("2026-11-01", periods=1))
    assert sc._compute_ath_price_flag(daily, None) is None


def test_compute_ath_price_flag_none_when_monthly_too_short():
    daily = pd.DataFrame({"Close": [100.0]}, index=pd.date_range("2026-11-01", periods=1))
    short_monthly = _FAKE_MONTHLY.iloc[:3]  # below C.MIN_MONTHLY_ROWS_FOR_ATH (12)
    assert sc._compute_ath_price_flag(daily, short_monthly) is None


# ---------------------------------------------------------------------------
# compute_sector_pulse (2026-11-22, per explicit user request) -- pure aggregation over
# already-computed per-stock columns, no network I/O.
# ---------------------------------------------------------------------------
_PULSE_SIGNALS = pd.DataFrame([
    {"Symbol": "BANKA", "Sector": "Financial Services", "ATH_Price_Flag": True,
     "RS_vs_Nifty_ATH": 5.0, "RS_vs_Nifty_52WkLow": -2.0},
    {"Symbol": "BANKB", "Sector": "Financial Services", "ATH_Price_Flag": False,
     "RS_vs_Nifty_ATH": -1.0, "RS_vs_Nifty_52WkLow": 3.0},
    {"Symbol": "AUTOA", "Sector": "Consumer Discretionary", "ATH_Price_Flag": True,
     "RS_vs_Nifty_ATH": 2.0, "RS_vs_Nifty_52WkLow": 2.0},
])
_PULSE_CATEGORIES = {"BANKA": "NIFTY 50,NIFTY BANK", "BANKB": "NIFTY BANK", "AUTOA": "NIFTY AUTO"}


def test_compute_sector_pulse_counts_ath_price_stock():
    pulse = sc.compute_sector_pulse(_PULSE_SIGNALS, _PULSE_CATEGORIES)
    bank_row = pulse.set_index("Sector").loc["NIFTY BANK"]
    assert bank_row["ATH_Price_Stock"] == 1  # only BANKA is True
    assert bank_row["Stock_Count"] == 2


def test_compute_sector_pulse_counts_outperformance():
    pulse = sc.compute_sector_pulse(_PULSE_SIGNALS, _PULSE_CATEGORIES)
    bank_row = pulse.set_index("Sector").loc["NIFTY BANK"]
    assert bank_row["Nifty50_Outperform_ATH"] == 1  # only BANKA > 0
    assert bank_row["Nifty50_Outperform_52WkLow"] == 1  # only BANKB > 0


def test_compute_sector_pulse_includes_screener_sector_rows():
    pulse = sc.compute_sector_pulse(_PULSE_SIGNALS, _PULSE_CATEGORIES)
    fin_row = pulse.set_index("Sector").loc["Financial Services"]
    assert fin_row["Stock_Count"] == 2
    assert fin_row["ATH_Price_Stock"] == 1


def test_compute_sector_pulse_includes_all_curated_index_tags_even_with_zero_members():
    pulse = sc.compute_sector_pulse(_PULSE_SIGNALS, _PULSE_CATEGORIES)
    assert "NIFTY FMCG" in set(pulse["Sector"])
    fmcg_row = pulse.set_index("Sector").loc["NIFTY FMCG"]
    assert fmcg_row["Stock_Count"] == 0
    assert fmcg_row["ATH_Price_Stock"] == 0


def test_compute_sector_pulse_empty_signals_returns_empty_with_schema():
    result = sc.compute_sector_pulse(pd.DataFrame(), {})
    assert result.empty
    assert list(result.columns) == sc.SECTOR_PULSE_COLUMNS
