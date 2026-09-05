"""
Dash callbacks for the Turtle Quant tab.

Two callbacks: the main render (Indices/Sector/Stock/Signal filters -> a colour-coded results
table, plus a staleness banner), and a "My Holdings" add/remove callback that writes only to
the logged-in user's own turtlequant_watchlist rows (via modules.auth.user_store) -- never
touches market-data tables.
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
from . import compute as tq_compute

_DISPLAY_COLUMNS = [
    "Symbol", "Indices", "Sector", "Industry", "Current_Price", "Signal_Date", "Signal",
    "RS_Long_Term", "RS_Short_Term", "ADX", "RSI",
    "SuperTrend_Direction", "Volume_Building", "Price_Above_MA13",
]

_COLUMN_TOOLTIPS = {
    "Symbol": "NSE trading symbol.",
    "Indices": "NSE index/sectoral membership (Nifty 50/100/200, sectoral indices, etc.).",
    "Sector": "Sector classification (Yahoo Finance).",
    "Industry": "More specific industry classification within the sector.",
    "Current_Price": "Latest weekly close price.",
    "Signal_Date": (
        "The date of the validated BUY or SELL event shown in Signal (blank if there is none "
        "yet) -- the week that event actually happened, not the day the batch job last ran."
    ),
    "RS_Long_Term": (
        "52-week relative strength vs NSE:NIFTY: (1 + stock's 52wk return/100) / "
        "(1 + Nifty's 52wk return/100) - 1. Above 0 = outperforming Nifty over the year "
        "(required for BUY); below 0 required for SELL (along with 5 other conditions)."
    ),
    "RS_Short_Term": "Same formula as RS Long Term, over a 13-week window -- recent momentum.",
    "ADX": "Trend strength (13-period DMI smoothing). >= 20 required for BUY; < 20 required for SELL.",
    "RSI": "21-period RSI. >= 55 required for BUY; < 45 required for SELL.",
    "SuperTrend_Direction": "SuperTrend(10, 3) on weekly bars. Bullish required for BUY; bearish required for SELL.",
    "Volume_Building": "True if the latest week's volume is above its own 13-week average volume. BUY-only -- not part of SELL.",
    "Price_Above_MA13": "True if the latest weekly close is above its own 13-week moving average. Below required for SELL.",
    "Signal": (
        "**Blank** — no validated BUY has ever been recorded for this stock yet (tracking "
        "started 2026-09-05) -- even if it's currently technically weak, there's nothing to "
        "'exit' without a prior recorded entry.\n\n"
        "**BUY** — all 7 hold together: SuperTrend bullish, RS Long & Short Term both positive, "
        "ADX >= 20, volume building, price above its 13w MA, RSI >= 55.\n\n"
        "**SELL** — all 6 hold together (volume not included): SuperTrend bearish, RS Long & "
        "Short Term both negative, ADX < 20, price below its 13w MA, RSI < 45 -- and it's the "
        "most recent validated event, coming after a prior validated BUY."
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
    for pct_col in ("RS_Long_Term", "RS_Short_Term"):
        if pct_col in display_df.columns:
            display_df[pct_col] = pd.to_numeric(display_df[pct_col], errors="coerce").round(3)
    for blank_col in ("Signal", "Signal_Date"):
        if blank_col in display_df.columns:
            display_df[blank_col] = display_df[blank_col].where(display_df[blank_col].notna(), None)

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
            {"if": {"filter_query": '{Signal} = "BUY"'}, "backgroundColor": "#d4edda", "color": "#155724"},
            {"if": {"filter_query": '{Signal} = "SELL"'}, "backgroundColor": "#f8d7da", "color": "#721c24"},
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
         Input("tq-signal-filter", "value"),
         Input("tq-auto-refresh-interval", "n_intervals"),
         Input("tq-holdings-tags", "children")],  # re-render immediately on add/remove
        prevent_initial_call=False,
    )
    def render_turtlequant(indices_value, sector_value, stock_value, signal_value, _n_intervals, _holdings_tags):
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

        # Replace the raw weekly classify() Signal/Signal_Date with the VALIDATED state from the
        # transition log -- confirmed with the user 2026-09-05: the displayed Signal must be
        # blank until a symbol has ever had a genuine recorded transition, and must only ever
        # show BUY or SELL, never HOLD. The raw per-week classification still runs and still
        # drives detect_transition() (see generate_turtlequant_signals.py) -- only what's
        # DISPLAYED here changes, not the underlying detection pipeline.
        validated = tq_compute.current_validated_signal(data_manager.turtlequant_transitions_df)
        df = df.drop(columns=["Signal", "Signal_Date"], errors="ignore")
        if not validated.empty:
            df = df.merge(validated, on="Symbol", how="left")
        else:
            df["Signal"] = None
            df["Signal_Date"] = None

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

        if signal_value and signal_value != "All":
            df = df[df["Signal"] == signal_value]

        if df.empty:
            return _empty_state("No stocks match the current filters."), _staleness_banner(loaded_date)

        return _table(df), _staleness_banner(loaded_date)
