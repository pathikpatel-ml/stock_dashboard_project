from pathlib import Path
from types import SimpleNamespace
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_manager
import generate_daily_signals
from modules import screener_callbacks, screener_layout


def test_load_startup_uses_latest_local_files(monkeypatch):
    v20_df = pd.DataFrame(
        [{"Symbol": "TCS", "Buy_Date": "2026-02-10", "Sell_Date": "2026-02-20", "Buy_Price_Low": 100, "Sequence_Gain_Percent": 12.5}]
    )
    ma_df = pd.DataFrame(
        [{"Symbol": "TCS", "Date": "2026-02-10", "Event_Type": "Primary_Buy", "Price": 100, "Company Name": "TCS Ltd", "Type": "Large", "MarketCap": 1000}]
    )
    growth_df = pd.DataFrame(
        [{"Symbol": "TCS", "Company Name": "TCS Ltd", "Net Profit (Cr)": 100, "Latest Quarter Profit (Cr)": 25, "ROCE (%)": 30, "ROE (%)": 28, "Debt to Equity": 0.1, "Public Holding (%)": 20, "Screening Date": "2026-02-10"}]
    )
    full_universe_df = pd.DataFrame(
        [{"Symbol": "TCS", "Company Name": "TCS Ltd", "Sector": "Technology", "Industry": "IT Services", "Market Cap": "Large", "Net Profit (Cr)": 100, "Latest Quarter Profit (Cr)": 25, "ROCE (%)": 30, "ROE (%)": 28, "Debt to Equity": 0.1, "Public Holding (%)": 20, "Screening Date": "2026-02-10"}]
    )

    def fake_read_csv(path, parse_dates=None, *args, **kwargs):
        path = str(path)
        if "stock_candle_signals_from_listing_20260210.csv" in path:
            return v20_df.copy()
        if "ma_signals_20260210.csv" in path:
            return ma_df.copy()
        if "NSE_EQ_All_Stocks_Analysis.csv" in path:
            return full_universe_df.copy()
        if "Master_company_market_trend_analysis.csv" in path:
            return growth_df.copy()
        raise FileNotFoundError(path)

    monkeypatch.setattr(data_manager, "REPO_BASE_PATH", "repo")
    monkeypatch.setattr(data_manager, "ACTIVE_GROWTH_DF_PATH", "repo/Master_company_market_trend_analysis.csv")
    monkeypatch.setattr(data_manager.os, "listdir", lambda _: ["stock_candle_signals_from_listing_20260210.csv", "ma_signals_20260210.csv"])
    monkeypatch.setattr(data_manager.os.path, "exists", lambda path: str(path) in {
        "repo/stock_candle_signals_from_listing_20260210.csv",
        "repo/ma_signals_20260210.csv",
        "repo/NSE_EQ_All_Stocks_Analysis.csv",
        "repo/Master_company_market_trend_analysis.csv",
    })
    monkeypatch.setattr(data_manager.pd, "read_csv", fake_read_csv)
    monkeypatch.setattr(data_manager, "_fetch_remote_matches", lambda prefix: [])
    monkeypatch.setattr(data_manager, "process_v20_signals", lambda df: pd.DataFrame([{"Symbol": "TCS", "Closeness (%)": 1.2}]))

    data_manager.load_and_process_data_on_startup()

    assert not data_manager.v20_signals_df.empty
    assert not data_manager.ma_signals_df.empty
    assert not data_manager.comprehensive_stocks_df.empty
    assert data_manager.LOADED_V20_FILE_DATE == "20260210"
    assert data_manager.LOADED_MA_FILE_DATE == "20260210"
    assert "TCS" in data_manager.all_available_symbols


def test_v20_eligible_symbols_excludes_psu_and_known_psu_symbols():
    growth_df = pd.DataFrame(
        [
            {"Symbol": "TCS", "Is PSU": False},
            {"Symbol": "SBIN", "Is PSU": True},
            {"Symbol": "PFC", "Is PSU": False},
        ]
    )

    symbols = generate_daily_signals.get_v20_eligible_symbols(growth_df)

    assert symbols == ["TCS"]


def test_load_comprehensive_stock_data_prefers_full_universe_file(monkeypatch):
    full_universe_df = pd.DataFrame(
        [
            {
                "Symbol": "INFY",
                "Company Name": "Infosys",
                "Sector": "Technology",
                "Industry": "IT Services",
                "Market Cap": "Large",
                "Net Profit (Cr)": 200,
                "Latest Quarter Profit (Cr)": 50,
                "ROCE (%)": 35,
                "ROE (%)": 30,
                "Debt to Equity": 0.0,
                "Public Holding (%)": 40,
            }
        ]
    )

    def fake_read_csv(path, *args, **kwargs):
        path = str(path)
        if "NSE_EQ_All_Stocks_Analysis.csv" in path:
            return full_universe_df.copy()
        raise FileNotFoundError(path)

    monkeypatch.setattr(data_manager, "REPO_BASE_PATH", "repo")
    monkeypatch.setattr(data_manager.os.path, "exists", lambda path: str(path) == "repo/NSE_EQ_All_Stocks_Analysis.csv")
    monkeypatch.setattr(data_manager.pd, "read_csv", fake_read_csv)
    monkeypatch.setattr(data_manager, "_sorted_local_matches", lambda pattern: [])
    monkeypatch.setattr(data_manager, "_fetch_remote_matches", lambda prefix: [])

    data_manager.load_comprehensive_stock_data()

    assert len(data_manager.comprehensive_stocks_df) == 1
    assert data_manager.comprehensive_stocks_df.iloc[0]["Symbol"] == "INFY"


def test_screener_callback_uses_live_data_manager_dataframe(monkeypatch):
    data_manager.comprehensive_stocks_df = pd.DataFrame(
        [
            {
                "Symbol": "TCS",
                "Company_Name": "TCS Ltd",
                "Net_Profit_Cr": 100,
                "Latest_Quarter_Profit": 25,
                "ROCE": 30,
                "ROE": 28,
                "Debt_to_Equity": 0.1,
                "Public_Holding_Percent": 20,
                "Current_Price": 3500,
                "MA10": 3400,
                "MA50": 3300,
                "MA100": 3200,
                "MA200": 3100,
                "NSE_Categories": "NIFTY50",
            }
        ]
    )

    monkeypatch.setattr(
        screener_callbacks,
        "ctx",
        SimpleNamespace(triggered=[{"prop_id": "apply-filters-btn.n_clicks"}]),
    )

    records, columns, summary = screener_callbacks.update_filtered_stocks(
        1,
        0,
        ["NIFTY50"],
        [0, 200],
        [0, 50],
        [0, 40],
        [0, 40],
        [0, 1],
        [0, 30],
        "above",
        "all",
        "all",
        "all",
    )

    assert len(records) == 1
    assert columns[0]["id"] == "Symbol"
    assert "Found 1 stocks" in summary


def test_category_options_are_built_from_current_dataframe():
    data_manager.comprehensive_stocks_df = pd.DataFrame(
        [{"Symbol": "TCS", "NSE_Categories": "NIFTY50, IT"}, {"Symbol": "INFY", "NSE_Categories": "NIFTY50"}]
    )

    options = screener_callbacks.update_category_options("screener-page")

    assert {"label": "IT", "value": "IT"} in options
    assert {"label": "NIFTY50", "value": "NIFTY50"} in options


def test_normalize_comprehensive_columns_generates_fallback_categories():
    source_df = pd.DataFrame(
        [
            {
                "Symbol": "tcs",
                "Company Name": "TCS Ltd",
                "Sector": "Technology",
                "Industry": "Information Technology Services",
                "Market Cap": "Large",
                "Net Profit (Cr)": 100,
                "Latest Quarter Profit (Cr)": 25,
                "ROCE (%)": 30,
                "ROE (%)": 28,
                "Debt to Equity": 0.1,
                "Public Holding (%)": 20,
                "Is PSU": "No",
                "Is Bank/Finance": "No",
            }
        ]
    )

    normalized = data_manager._normalize_comprehensive_columns(source_df)

    assert normalized.loc[0, "Symbol"] == "TCS"
    assert "Sector: Technology" in normalized.loc[0, "NSE_Categories"]
    assert "Industry: Information Technology Services" in normalized.loc[0, "NSE_Categories"]


def test_screener_layout_sliders_have_tooltips():
    layout = screener_layout.create_screener_layout()
    left_card_body = layout.children[1].children[0].children.children[1]
    slider_ids = {
        "net-profit-slider",
        "quarterly-profit-slider",
        "roce-slider",
        "roe-slider",
        "debt-equity-slider",
        "public-holding-slider",
    }

    found = {}
    for component in left_card_body.children:
        component_id = getattr(component, "id", None)
        if component_id in slider_ids:
            found[component_id] = getattr(component, "tooltip", None)

    assert set(found.keys()) == slider_ids
    assert all(tooltip == {"placement": "bottom", "always_visible": False} for tooltip in found.values())
