"""
Dash callbacks for the Turtle Quant tab.

Two callbacks: the main render (Indices/Sector/Stock filters -> a results table, plus a
staleness banner), and a "My Holdings" add/remove callback that writes only to the logged-in
user's own turtlequant_watchlist rows (via modules.auth.user_store) -- never touches
market-data tables.
"""
import json
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import flask_login
import pandas as pd
from dash import ALL, Input, Output, State, dash_table, html

import data_manager
from modules.auth import user_store
from modules.turtle.compute import filter_by_index

# 2026-10-02 redesign (per explicit user request): the dashboard shows only 3 aggregate
# Yes/No columns -- Growth, Red Flag, Value -- instead of the 21 individual metrics. The
# individual values still flow through the full pipeline (turtle_fundamentals,
# turtlequant_signals_latest) for debugging/export, just not displayed here anymore.
# See modules/turtle/quality_flags.py for every formula.
_DISPLAY_COLUMNS = [
    "Symbol", "Indices", "Broad_Sector", "Sector", "Industry", "Current_Price",
    "Growth_Category_Flag", "Red_Flag_Category_Flag", "Value_Category_Flag",
]

# The 3 category columns get short display names/ids on the table itself (the underlying
# dataframe column stays the full name everywhere else in the pipeline).
_CATEGORY_DISPLAY_NAMES = {
    "Growth_Category_Flag": "Growth",
    "Red_Flag_Category_Flag": "Red Flag",
    "Value_Category_Flag": "Value",
}

_COLUMN_TOOLTIPS = {
    "Symbol": "NSE trading symbol.",
    "Indices": "NSE index/sectoral membership (Nifty 50/100/200, sectoral indices, etc.).",
    "Broad_Sector": (
        "Top-level macro sector (screener.in's own classification, 12 total), e.g. Energy, "
        "Financial Services, Healthcare. Blank if screener.in has no listing for this stock."
    ),
    "Sector": (
        "Sector classification -- screener.in's own 22-value hierarchy when available "
        "(e.g. Oil Gas & Consumable Fuels, Banks), else Yahoo Finance's cruder 12-value tag "
        "as a fallback for stocks screener.in has no listing for."
    ),
    "Industry": "More specific industry classification within the sector (Yahoo Finance).",
    "Current_Price": "Latest daily close price.",
    "Growth": (
        "Yes only if ALL 5 hold: Book Value/EPS/Sales growth > 10% in EVERY individual year "
        "(not just the overall average), ROE > 10% in EVERY individual year, and promoter "
        "holding hasn't decreased over screener.in's real ~3-year window. A single weak year "
        "in any metric, or missing data, makes this No."
    ),
    "Red Flag": (
        "Yes only if ALL 3 hold: Promoter Pledge < 1% of promoter holding (sourced from NSE's "
        "own regulatory pledge disclosure, not screener.in), Quality of Turnover (Other Income "
        "/ Total Revenue) < 10%, and Interest Coverage > 5 (or zero debt)."
    ),
    "Value": (
        "Yes only if ALL 3 hold: current Price-to-Book, Price-to-Sales, and Price-to-Cash-Flow "
        "are each cheaper than their own 5-year average -- i.e. the stock is cheap relative to "
        "its own recent valuation history on all three measures."
    ),
}


def _empty_state(message: str, hint: str = "") -> html.Div:
    return html.Div(
        [html.P(message, style={"margin": 0, "fontWeight": 600}),
         html.P(hint, style={"margin": "4px 0 0 0", "fontSize": "13px", "color": "#6c757d"}) if hint else None],
        className="status-message info",
    )


def _table(df):
    cols = [c for c in _DISPLAY_COLUMNS if c in df.columns]
    display_df = df[cols].copy()
    if "Current_Price" in display_df.columns:
        display_df["Current_Price"] = pd.to_numeric(
            display_df["Current_Price"], errors="coerce"
        ).round(0).astype("Int64")
    for cat_col in _CATEGORY_DISPLAY_NAMES:
        if cat_col in display_df.columns:
            display_df[cat_col] = display_df[cat_col].map({True: "Yes", False: "No"}).fillna("No")
    display_df = display_df.rename(columns=_CATEGORY_DISPLAY_NAMES)
    cols = [_CATEGORY_DISPLAY_NAMES.get(c, c) for c in cols]

    return dash_table.DataTable(
        id="tq-signals-table",
        columns=[{"name": c.replace("_", " "), "id": c} for c in cols],
        data=display_df.to_dict("records"),
        tooltip_header={
            c: {"value": _COLUMN_TOOLTIPS[c], "type": "markdown"}
            for c in cols if c in _COLUMN_TOOLTIPS
        },
        tooltip_delay=0,
        tooltip_duration=None,
        css=[{"selector": ".dash-table-tooltip", "rule": "max-width: 320px; white-space: normal;"}],
        page_size=20,
        sort_action="native",
        filter_action="native",
        export_format="xlsx",
        export_headers="display",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "center", "fontSize": "13px", "padding": "8px",
                    "fontFamily": "Inter, sans-serif"},
        style_header={"backgroundColor": "#f1f5f9", "fontWeight": "600"},
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#f8f9fa"},
        ] + [
            {"if": {"filter_query": f'{{{col}}} = "Yes"', "column_id": col},
             "backgroundColor": "#d4edda", "color": "#155724"}
            for col in _CATEGORY_DISPLAY_NAMES.values()
        ] + [
            {"if": {"filter_query": f'{{{col}}} = "No"', "column_id": col},
             "backgroundColor": "#f8d7da", "color": "#721c24"}
            for col in _CATEGORY_DISPLAY_NAMES.values()
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
            f"⚠️ Data staleness: Turtle Quant signals are {age_days} days old "
            f"(file {loaded_date}). Run generate_turtlequant_signals.py to refresh.",
            className="status-message", style={"backgroundColor": "#fff3cd", "color": "#856404",
                                               "border": "1px solid #ffe69c", "margin": "8px 0"},
        )
    return None


def _current_user_id():
    if flask_login.current_user.is_authenticated:
        return flask_login.current_user.id
    return None


def register_turtlequant_callbacks(app):
    """Register all Turtle Quant callbacks on the Dash ``app``."""

    @app.callback(
        Output("tq-holdings-tags", "children"),
        Output("tq-holdings-add-dropdown", "value"),
        Input("tq-holdings-add-btn", "n_clicks"),
        Input({"type": "del-tq-holding", "symbol": ALL}, "n_clicks"),
        State("tq-holdings-add-dropdown", "value"),
        prevent_initial_call=False,
    )
    def manage_turtlequant_watchlist(_add_clicks, del_clicks, new_symbol):
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        ctx = dash.callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
        if "tq-holdings-add-btn" in triggered and new_symbol:
            user_store.add_to_turtlequant_watchlist(user_id, new_symbol)
        elif "del-tq-holding" in triggered and any(del_clicks):
            id_dict = json.loads(triggered.split(".")[0])
            user_store.remove_from_turtlequant_watchlist(user_id, id_dict["symbol"])

        symbols = user_store.get_turtlequant_watchlist(user_id)
        tags = [
            dbc.Badge(
                [sym, html.Span(" ×", id={"type": "del-tq-holding", "symbol": sym},
                                 style={"cursor": "pointer", "marginLeft": "4px"}, n_clicks=0)],
                color="secondary", className="me-1 mb-1 p-2", style={"fontSize": "0.8rem"},
            )
            for sym in symbols
        ]
        return tags, None

    @app.callback(
        [Output("tq-signals-container", "children"),
         Output("tq-staleness-banner", "children")],
        [Input("tq-indices-filter", "value"),
         Input("tq-sector-filter", "value"),
         Input("tq-stock-filter", "value"),
         Input("tq-auto-refresh-interval", "n_intervals"),
         Input("tq-holdings-tags", "children")],  # re-render immediately on add/remove
        prevent_initial_call=False,
    )
    def render_turtlequant(indices_value, sector_value, stock_value, _n_intervals, _holdings_tags):
        # Re-sync on every render, not just at process boot -- same reasoning as
        # modules/turtle/callbacks.py::render_turtle.
        data_manager.load_turtlequant_data_on_startup()

        df = data_manager.turtlequant_signals_df.copy()
        loaded_date = data_manager.LOADED_TURTLEQUANT_FILE_DATE

        if df.empty:
            return (
                _empty_state(
                    "No Turtle Quant signals available.",
                    "Run generate_turtlequant_signals.py to populate turtlequant_signals_<date>.csv.",
                ),
                _staleness_banner(loaded_date),
            )

        categories_df = data_manager.nse_categories_df
        categories_map = (
            dict(zip(categories_df["Symbol"], categories_df["NSE_Categories"]))
            if not categories_df.empty else {}
        )
        df["Indices"] = df["Symbol"].map(categories_map)

        if indices_value == "My Holdings":
            user_id = _current_user_id()
            holdings_symbols = set(user_store.get_turtlequant_watchlist(user_id)) if user_id else set()
            df = df[df["Symbol"].isin(holdings_symbols)]
        elif indices_value and indices_value != "All" and categories_map:
            mask = df["Symbol"].map(lambda sym: filter_by_index(categories_map.get(sym), indices_value))
            df = df[mask]

        if sector_value and sector_value != "All":
            df = df[df["Sector"] == sector_value]

        if stock_value and stock_value != "All":
            df = df[df["Symbol"] == stock_value]

        if df.empty:
            return _empty_state("No stocks match the current filters."), _staleness_banner(loaded_date)

        return _table(df), _staleness_banner(loaded_date)
