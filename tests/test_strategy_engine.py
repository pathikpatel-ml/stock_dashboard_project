from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import data_manager
from modules import strategy_callbacks, strategy_layout
from modules.strategy_engine import (
    calculate_derived_metrics,
    quality_filter,
    sector_ranker,
    value_reversion_signals,
)


def _build_strategy_panel():
    rows = []
    configs = {
        "ALPHA": {"sector": "Tech", "market_cap": 500, "sales_base": 12, "roce_base": 14, "pb_base": 4.5, "ps_base": 4.0, "pcf_base": 8.0, "promoter_start": 50, "quality_turnover": 6, "pledging": 0, "interest": 10},
        "BETA": {"sector": "Tech", "market_cap": 450, "sales_base": 18, "roce_base": 20, "pb_base": 2.5, "ps_base": 2.2, "pcf_base": 5.2, "promoter_start": 45, "quality_turnover": 5, "pledging": 0, "interest": 9},
        "GAMMA": {"sector": "Tech", "market_cap": 300, "sales_base": 9, "roce_base": 11, "pb_base": 1.8, "ps_base": 1.6, "pcf_base": 4.6, "promoter_start": 47, "quality_turnover": 7, "pledging": 12, "interest": 4},
        "DELTA": {"sector": "Banks", "market_cap": 600, "sales_base": 15, "roce_base": 17, "pb_base": 2.0, "ps_base": 2.4, "pcf_base": 4.8, "promoter_start": 52, "quality_turnover": 8, "pledging": 1, "interest": 8},
        "EPSILON": {"sector": "Banks", "market_cap": 190, "sales_base": 21, "roce_base": 22, "pb_base": 1.7, "ps_base": 2.0, "pcf_base": 4.2, "promoter_start": 55, "quality_turnover": 3, "pledging": 0, "interest": 11},
    }
    for ticker, config in configs.items():
        for year in range(2017, 2027):
            offset = year - 2017
            rows.append(
                {
                    "ticker": ticker,
                    "year": year,
                    "sales_growth_pct": config["sales_base"] + (offset % 3),
                    "roce_pct": config["roce_base"] + (offset % 2),
                    "pb_ratio": config["pb_base"] + (0.1 * offset),
                    "book_value_growth_pct": config["sales_base"] + 1,
                    "eps_growth_pct": config["sales_base"] + 2,
                    "promoter_holding_pct": config["promoter_start"] + offset,
                    "ps_ratio": config["ps_base"] + (0.1 * offset),
                    "pcf_ratio": config["pcf_base"] + (0.15 * offset),
                    "promoter_pledging_pct": config["pledging"],
                    "quality_turnover_pct": config["quality_turnover"],
                    "interest_coverage_ratio": config["interest"],
                    "sector": config["sector"],
                    "market_cap": config["market_cap"],
                }
            )
    panel = pd.DataFrame(rows)

    current_mask = panel["year"] == 2026
    panel.loc[current_mask & panel["ticker"].eq("BETA"), ["pb_ratio", "ps_ratio", "pcf_ratio"]] = [2.0, 1.8, 4.8]
    panel.loc[current_mask & panel["ticker"].eq("ALPHA"), ["pb_ratio", "ps_ratio", "pcf_ratio"]] = [6.5, 5.4, 9.8]
    panel.loc[current_mask & panel["ticker"].eq("GAMMA"), "promoter_holding_pct"] = 40
    return panel.set_index(["ticker", "year"])


def test_calculate_derived_metrics_builds_requested_windows():
    features = calculate_derived_metrics(_build_strategy_panel()).reset_index(drop=True)
    beta_2026 = features[(features["ticker"] == "BETA") & (features["year"] == 2026)].iloc[0]

    assert round(beta_2026["3yr_avg_sales_growth"], 2) == round((18 + 19 + 20) / 3, 2)
    assert round(beta_2026["3yr_avg_roce"], 2) == round((21 + 20 + 21) / 3, 2)
    assert round(beta_2026["10yr_change_promoter_holding"], 2) == 9
    assert beta_2026["5yr_avg_pb"] > 0
    assert beta_2026["5yr_avg_ps"] > 0
    assert beta_2026["5yr_avg_pcf"] > 0


def test_sector_ranker_filters_market_cap_and_returns_top_n_per_sector():
    ranked = sector_ranker(_build_strategy_panel(), current_year=2026, top_n=2)

    assert "EPSILON" not in ranked["ticker"].tolist()
    assert ranked.groupby("sector").size().to_dict() == {"Banks": 1, "Tech": 2}
    tech_rows = ranked[ranked["sector"] == "Tech"].sort_values("sector_position")
    assert tech_rows.iloc[0]["ticker"] == "BETA"


def test_quality_filter_requires_all_quality_rules():
    shortlist = pd.DataFrame({"ticker": ["ALPHA", "BETA", "GAMMA", "DELTA"]})
    filtered = quality_filter(shortlist, current_year=2026, df=_build_strategy_panel())

    assert set(filtered["ticker"]) == {"ALPHA", "BETA", "DELTA"}
    assert "GAMMA" not in filtered["ticker"].tolist()


def test_value_reversion_signals_marks_buy_and_sell_conditions():
    signaled = value_reversion_signals(_build_strategy_panel(), current_year=2026)
    beta_row = signaled[signaled["ticker"] == "BETA"].iloc[0]
    alpha_row = signaled[signaled["ticker"] == "ALPHA"].iloc[0]

    assert bool(beta_row["Buy_Signal"]) is True
    assert bool(beta_row["Sell_Signal"]) is False
    assert bool(alpha_row["Sell_Signal"]) is True


def test_strategy_layout_contains_strategy_controls():
    layout = strategy_layout.create_strategy_layout()
    layout_str = str(layout)
    assert "Quant Strategies" in layout_str
    assert "strategy-year-dropdown" in layout_str


def test_strategy_callbacks_return_empty_state_without_historical_data():
    data_manager.fundamentals_yearly_df = pd.DataFrame()
    options, value, status = strategy_callbacks.load_strategy_years("strategy-page")

    assert options == []
    assert value is None
    assert "not loaded" in status.lower()


def test_normalize_fundamentals_yearly_columns_supports_symbol_aliases():
    source = pd.DataFrame(
        [
            {
                "Symbol": "infy",
                "Year": 2025,
                "sales_growth_pct": 15,
                "roce_pct": 20,
                "pb_ratio": 4,
                "book_value_growth_pct": 14,
                "eps_growth_pct": 16,
                "promoter_holding_pct": 12,
                "ps_ratio": 5,
                "pcf_ratio": 7,
                "promoter_pledging_pct": 0,
                "quality_turnover_pct": 3,
                "interest_coverage_ratio": 10,
                "Sector": "Technology",
                "Market Cap": 1000,
            }
        ]
    )

    normalized = data_manager._normalize_fundamentals_yearly_columns(source)

    assert normalized.loc[0, "ticker"] == "INFY"
    assert normalized.loc[0, "year"] == 2025
    assert normalized.loc[0, "sector"] == "Technology"
