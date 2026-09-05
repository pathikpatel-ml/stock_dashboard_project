"""
Dash callbacks for the Turtle Quant tab.

One render callback: Indices/Sector/Stock filters -> a colour-coded results table, plus a
staleness banner. Fully read-only -- no writes anywhere in this module.
"""
from datetime import datetime

import pandas as pd
from dash import Input, Output, dash_table, html

import data_manager
from modules.turtle.compute import filter_by_index
from . import compute as tq_compute

_DISPLAY_COLUMNS = [
    "Symbol", "Indices", "Sector", "Industry", "Current_Price", "Signal_Date", "Signal",
    "Last_Buy_Date", "Last_Sell_Date",
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
        "The week (Monday-dated) this signal is actually based on -- not the day the batch job "
        "last ran. Stays the same all week until that week's candle closes and a new one starts."
    ),
    "Last_Buy_Date": (
        "The most recent week this stock had a BUY signal, from recorded history. Blank if it "
        "hasn't had one since history started being tracked (2026-09-05)."
    ),
    "Last_Sell_Date": (
        "The most recent week this stock had a SELL signal, from recorded history. Blank if it "
        "hasn't had one since history started being tracked (2026-09-05)."
    ),
    "RS_Long_Term": (
        "52-week relative strength vs NSE:NIFTY: (1 + stock's 52wk return/100) / "
        "(1 + Nifty's 52wk return/100) - 1. Above 0 = outperforming Nifty over the year; "
        "at/below -0.25 triggers SELL."
    ),
    "RS_Short_Term": "Same formula as RS Long Term, over a 13-week window -- recent momentum.",
    "ADX": "Trend strength (13-period DMI smoothing). >= 20 required for BUY.",
    "RSI": "21-period RSI. >= 55 required for BUY; <= 45 alone triggers SELL.",
    "SuperTrend_Direction": "SuperTrend(10, 3) on weekly bars. BEARISH alone triggers SELL.",
    "Volume_Building": "True if the latest week's volume is above its own 13-week average volume.",
    "Price_Above_MA13": "True if the latest weekly close is above its own 13-week moving average.",
    "Signal": (
        "**BUY** — SuperTrend bullish, RS Long & Short Term both positive, ADX >= 20, "
        "volume building, price above its 13w MA, RSI >= 55 — every condition must hold.\n\n"
        "**SELL** — any single weakening signal: SuperTrend bearish, OR RS Long Term <= -0.25, "
        "OR RSI <= 45.\n\n"
        "**HOLD** — everything else (SuperTrend bullish, full BUY confirmation not yet met)."
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
            {"if": {"filter_query": '{Signal} = "HOLD"'}, "backgroundColor": "#fff3cd", "color": "#856404"},
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


def register_turtlequant_callbacks(app):
    """Register all Turtle Quant callbacks on the Dash ``app``."""

    @app.callback(
        [Output("tq-signals-container", "children"),
         Output("tq-staleness-banner", "children")],
        [Input("tq-indices-filter", "value"),
         Input("tq-sector-filter", "value"),
         Input("tq-stock-filter", "value"),
         Input("tq-signal-filter", "value"),
         Input("tq-auto-refresh-interval", "n_intervals")],
        prevent_initial_call=False,
    )
    def render_turtlequant(indices_value, sector_value, stock_value, signal_value, _n_intervals):
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

        last_dates = tq_compute.last_signal_dates(data_manager.turtlequant_history_df)
        if not last_dates.empty:
            df = df.merge(last_dates, on="Symbol", how="left")
        else:
            df["Last_Buy_Date"] = None
            df["Last_Sell_Date"] = None

        if indices_value and indices_value != "All" and categories_map:
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
