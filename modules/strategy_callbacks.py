import pandas as pd
from dash import Input, Output, State, callback, html

import data_manager
from modules.strategy_engine import (
    quality_filter,
    quality_filter_diagnostics,
    sector_ranker,
    value_reversion_signals,
)


def _columns_from_df(df):
    if df.empty:
        return []
    columns = []
    for column in df.columns:
        if pd.api.types.is_bool_dtype(df[column]):
            column_type = "text"
        elif pd.api.types.is_numeric_dtype(df[column]):
            column_type = "numeric"
        else:
            column_type = "text"
        columns.append({"name": column.replace("_", " "), "id": column, "type": column_type})
    return columns


@callback(
    Output("strategy-year-dropdown", "options"),
    Output("strategy-year-dropdown", "value"),
    Output("strategy-data-status", "children"),
    Input("strategy-page", "id"),
)
def load_strategy_years(_):
    df = data_manager.fundamentals_yearly_df
    if df.empty:
        return (
            [],
            None,
            "Historical fundamentals file not loaded yet. Add stock_fundamentals_yearly.csv (or output/stock_fundamentals_yearly*.csv) to enable these modules.",
        )

    years = sorted(pd.to_numeric(df["year"], errors="coerce").dropna().astype(int).unique().tolist(), reverse=True)
    options = [{"label": str(year), "value": year} for year in years]
    return options, (years[0] if years else None), f"Loaded {len(df)} yearly rows across {len(years)} years."


@callback(
    Output("strategy-sector-dropdown", "options"),
    Output("strategy-sector-dropdown", "value"),
    Input("strategy-year-dropdown", "value"),
    State("strategy-sector-dropdown", "value"),
)
def load_strategy_sectors(current_year, current_sector):
    df = data_manager.fundamentals_yearly_df
    if df.empty or current_year is None:
        return [{"label": "All Sectors", "value": "__ALL__"}], "__ALL__"

    year_df = df[pd.to_numeric(df["year"], errors="coerce").astype("Int64") == int(current_year)].copy()
    sectors = sorted(year_df["sector"].fillna("Unknown").astype(str).str.strip().replace("", "Unknown").unique().tolist())
    options = [{"label": "All Sectors", "value": "__ALL__"}] + [
        {"label": sector, "value": sector} for sector in sectors if sector
    ]
    valid_values = {option["value"] for option in options}
    value = current_sector if current_sector in valid_values else "__ALL__"
    return options, value


@callback(
    Output("strategy-summary", "children"),
    Output("strategy-sector-ranker-table", "data"),
    Output("strategy-sector-ranker-table", "columns"),
    Output("strategy-quality-table", "data"),
    Output("strategy-quality-table", "columns"),
    Output("strategy-value-table", "data"),
    Output("strategy-value-table", "columns"),
    Input("strategy-year-dropdown", "value"),
    Input("strategy-sector-dropdown", "value"),
)
def update_strategy_views(current_year, selected_sector):
    df = data_manager.fundamentals_yearly_df
    if df.empty or current_year is None:
        empty = []
        return (
            "Historical fundamentals data is required for these modules.",
            empty,
            empty,
            empty,
            empty,
            empty,
            empty,
        )

    def filter_by_sector(input_df):
        if input_df.empty or not selected_sector or selected_sector == "__ALL__":
            return input_df
        if "sector" not in input_df.columns:
            return input_df
        return input_df[input_df["sector"] == selected_sector].copy()

    ranked = sector_ranker(df, current_year=current_year, top_n=3)
    ranked = filter_by_sector(ranked)
    quality = quality_filter(ranked, current_year=current_year, df=df)
    quality_diagnostics = quality_filter_diagnostics(ranked, current_year=current_year, df=df)
    value = value_reversion_signals(df, current_year=current_year)
    value = value[(value["Buy_Signal"]) | (value["Sell_Signal"])].copy()
    value = filter_by_sector(value)

    sector_label = selected_sector if selected_sector and selected_sector != "__ALL__" else "All Sectors"

    summary = html.Div(
        [
            html.P(f"Current year: {current_year}", className="mb-1"),
            html.P(f"Selected sector: {sector_label}", className="mb-1"),
            html.P(f"Module 1 shortlisted stocks: {len(ranked)}", className="mb-1"),
            html.P(f"Module 2 quality-approved stocks: {len(quality)}", className="mb-1"),
            html.P(
                f"Module 2 shortlisted diagnostics rows: {len(quality_diagnostics)}",
                className="mb-1",
            ),
            html.P(f"Module 3 active buy/sell signals: {len(value)}", className="mb-0"),
        ]
    )
    return (
        summary,
        ranked.to_dict("records"),
        _columns_from_df(ranked),
        quality_diagnostics.to_dict("records"),
        _columns_from_df(quality_diagnostics),
        value.to_dict("records"),
        _columns_from_df(value),
    )


def register_strategy_callbacks(app):
    return app
