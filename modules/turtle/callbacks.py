"""
Dash callbacks for the Turtle Strategy tab (docs/TURTLE_STRATEGY_PLAN.md).

One main render callback: Indices/Sector/Stock/ATH-only/Yesterday filters -> a colour-coded
results table, plus a staleness banner. Read-only — nothing here places or modifies trades.
"""
from datetime import datetime

from dash import Input, Output, dash_table, html

import data_manager
from . import compute

_DISPLAY_COLUMNS = [
    "Symbol", "Sector", "Industry", "Current_Price", "ATH_Price_Flag", "TTM_Net_Profit",
    "ATH_Profit_Flag", "ATH_Sales", "Above_MA200_Flag", "RS_vs_Sector", "RS_vs_Benchmark",
    "Signal",
]


def _empty_state(message: str, hint: str = "") -> html.Div:
    return html.Div(
        [html.P(message, style={"margin": 0, "fontWeight": 600}),
         html.P(hint, style={"margin": "4px 0 0 0", "fontSize": "13px", "color": "#6c757d"}) if hint else None],
        className="status-message info",
    )


def _table(df):
    cols = [c for c in _DISPLAY_COLUMNS if c in df.columns]
    return dash_table.DataTable(
        id="tt-signals-table",
        columns=[{"name": c.replace("_", " "), "id": c} for c in cols],
        data=df[cols].to_dict("records"),
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "center", "fontSize": "13px", "padding": "8px",
                    "fontFamily": "Inter, sans-serif"},
        style_header={"backgroundColor": "#f1f5f9", "fontWeight": "600"},
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#f8f9fa"},
            {"if": {"filter_query": '{Signal} = "ADD"'}, "backgroundColor": "#d4edda", "color": "#155724"},
            {"if": {"filter_query": '{Signal} = "HOLD"'}, "backgroundColor": "#fff3cd", "color": "#856404"},
            {"if": {"filter_query": '{Signal} = "EXIT"'}, "backgroundColor": "#f8d7da", "color": "#721c24"},
        ],
    )


def _staleness_banner(loaded_date):
    if not loaded_date:
        return None
    try:
        age_days = (datetime.now().date() - datetime.strptime(loaded_date, "%Y%m%d").date()).days
    except Exception:
        return None
    if age_days > 1:
        return html.Div(
            f"⚠️ Data staleness: turtle signals are {age_days} days old "
            f"(file {loaded_date}). Run generate_turtle_signals.py to refresh.",
            className="status-message", style={"backgroundColor": "#fff3cd", "color": "#856404",
                                               "border": "1px solid #ffe69c", "margin": "8px 0"},
        )
    return None


def register_turtle_callbacks(app):
    """Register all Turtle Strategy callbacks on the Dash ``app``."""

    @app.callback(
        [Output("tt-signals-container", "children"),
         Output("tt-staleness-banner", "children")],
        [Input("tt-indices-filter", "value"),
         Input("tt-sector-filter", "value"),
         Input("tt-stock-filter", "value"),
         Input("tt-ath-only-toggle", "value"),
         Input("tt-yesterday-toggle", "value"),
         Input("tt-auto-refresh-interval", "n_intervals")],
        prevent_initial_call=False,
    )
    def render_turtle(indices_value, sector_value, stock_value, ath_only, yesterday, _n_intervals):
        if yesterday and "yesterday" in yesterday:
            df, _filename = data_manager.get_turtle_signals_by_offset(1)
            loaded_date = data_manager._extract_date_from_name(_filename or "", r"(\d{8})")
        else:
            df = data_manager.turtle_signals_df.copy()
            loaded_date = data_manager.LOADED_TURTLE_FILE_DATE

        if df.empty:
            return (
                _empty_state(
                    "No Turtle signals available.",
                    "Run generate_turtle_signals.py to populate turtle_signals_<date>.csv." if not yesterday
                    else "No prior-day turtle signals file was found.",
                ),
                _staleness_banner(loaded_date),
            )

        categories_df = data_manager.nse_categories_df
        if indices_value and indices_value != "All" and not categories_df.empty:
            categories_map = dict(zip(categories_df["Symbol"], categories_df["NSE_Categories"]))
            mask = df["Symbol"].map(
                lambda sym: compute.filter_by_index(categories_map.get(sym), indices_value)
            )
            df = df[mask]

        if sector_value and sector_value != "All":
            df = df[df["Sector"] == sector_value]

        if stock_value and stock_value != "All":
            df = df[df["Symbol"] == stock_value]

        if ath_only and "ath_only" in ath_only:
            df = df[df["ATH_Price_Flag"] == True]  # noqa: E712 (explicit bool compare over a DataFrame column)

        if df.empty:
            return _empty_state("No stocks match the current filters."), _staleness_banner(loaded_date)

        return _table(df), _staleness_banner(loaded_date)
