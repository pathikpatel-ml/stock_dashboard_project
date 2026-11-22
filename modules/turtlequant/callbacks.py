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
from modules.turtlequant import benchmark_drawdown as bd

# 2026-10-02: the dashboard originally showed only 3 aggregate Yes/No columns -- Growth, Red
# Flag, Value -- instead of the 21 individual metrics (still see modules/turtle/quality_flags.py
# for every formula). 2026-10-05 added a derived Buy_Sell_Flag on top of those 3. 2026-11-22
# (per explicit user request): Buy/Sell + the 3 category columns, and their checkbox filters,
# were REMOVED ENTIRELY from both this dashboard and turtlequant_signals_latest -- this tab is
# now solely the Nifty-50-anchored drawdown comparison below. The 21 individual quality/
# valuation metrics are untouched in turtle_fundamentals/Turtle Strategy; only Turtle Quant's
# own 3 derived category columns were dropped (modules/turtlequant/screener.py's QUALITY_COLUMNS
# no longer includes them).
#
# 6 columns for the Nifty-50-anchored ATH/52-week-low drawdown comparison (added 2026-11-22) --
# see modules/turtlequant/benchmark_drawdown.py for the formulas. Nifty_ATH_Return_Pct/
# Nifty_52WkLow_Return_Pct are broadcast onto every row from the single shared
# turtlequant_nifty_benchmark reference (same value for every stock); the other 4 are genuinely
# per-stock, read straight from turtlequant_signals_latest.
_DRAWDOWN_DISPLAY_COLUMNS = [
    "RS_vs_Nifty_ATH", "RS_vs_Nifty_52WkLow",
    "Nifty_ATH_Return_Pct", "Nifty_52WkLow_Return_Pct",
    "Stock_ATH_Return_Pct", "Stock_52WkLow_Return_Pct",
]

# 2026-11-22 (per explicit user request): ATH Profit/Sales -- same computation Turtle Strategy's
# own table uses (modules/turtle/compute.py::ath_profit_flag/ath_sales_flag), from the SAME
# shared turtle_fundamentals data both tabs read; TTM_Net_Profit/TTM_Net_Sales are computed too
# but deliberately not displayed (table-width reduction), same choice Turtle Strategy's own
# dashboard already made for these exact two figures.
_ATH_DISPLAY_COLUMNS = ["ATH_Profit_Flag", "ATH_Sales_Flag"]

_DISPLAY_COLUMNS = [
    "Symbol", "Indices", "Broad_Sector", "Sector", "Industry", "Current_Price",
] + _ATH_DISPLAY_COLUMNS + _DRAWDOWN_DISPLAY_COLUMNS

_EXTRA_DISPLAY_NAMES = {
    "RS_vs_Nifty_ATH": "NiftyATH vs Stock",
    "RS_vs_Nifty_52WkLow": "Nifty52wkLow vs Stock",
    "Nifty_ATH_Return_Pct": "Nifty ATH Return%",
    "Nifty_52WkLow_Return_Pct": "Nifty 52wkLow Return%",
    "Stock_ATH_Return_Pct": "Stock ATH Return%",
    "Stock_52WkLow_Return_Pct": "Stock 52wkLow Return%",
}

# Checkbox filter options (2026-11-22, per explicit user request, replacing the removed
# Growth/Red Flag/Value checkboxes): tick "ATH Performance" to keep only stocks where
# RS_vs_Nifty_ATH > 0 (the stock has outperformed Nifty 50 since Nifty's ATH date); tick
# "52wk Low Performance" for RS_vs_Nifty_52WkLow > 0 (outperformed since Nifty's 52-week-low
# date). Both ticked is an AND filter (must outperform on both measures).
PERFORMANCE_FILTER_OPTIONS = [
    {"label": " ATH Performance", "value": "ath_performance"},
    {"label": " 52wk Low Performance", "value": "low52wk_performance"},
]

# 2026-11-22, per explicit user request: two more checkboxes -- tick "TTM Profit Flag" to keep
# only stocks where ATH_Profit_Flag is True, tick "TTM Sales Flag" for ATH_Sales_Flag == True.
# Both ticked is an AND filter, same convention as PERFORMANCE_FILTER_OPTIONS above.
FUNDAMENTAL_FILTER_OPTIONS = [
    {"label": " TTM Profit Flag", "value": "ttm_profit_flag"},
    {"label": " TTM Sales Flag", "value": "ttm_sales_flag"},
]

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
    "ATH_Profit_Flag": (
        "True if consolidated TTM Net Profit is at/above the highest annual Net Profit on "
        "record (any year, including the latest) -- same computation as the Turtle Strategy "
        "tab's own ATH_Profit_Flag, from the same shared turtle_fundamentals data.\n\n"
        "`ATH_Profit_Flag = TTM_Net_Profit ≥ max(all annual Net Profit years)`"
    ),
    "ATH_Sales_Flag": (
        "True if consolidated TTM Net Sales is at/above the highest annual sales on record "
        "(any year, including the latest) -- same shape as ATH_Profit_Flag.\n\n"
        "`ATH_Sales_Flag = TTM_Net_Sales ≥ max(all annual Net Sales years)`"
    ),
    "NiftyATH vs Stock": (
        "Stock ATH Return% minus Nifty ATH Return% (percentage points). Positive = this stock "
        "has outperformed Nifty 50 since Nifty's all-time-high date; negative = underperformed."
    ),
    "Nifty52wkLow vs Stock": (
        "Stock 52wkLow Return% minus Nifty 52wkLow Return% (percentage points). Positive = this "
        "stock has outperformed Nifty 50 since Nifty's 52-week-low date; negative = underperformed."
    ),
    "Nifty ATH Return%": (
        "Nifty 50's own % change from its all-time-high (intraday High) to today's close -- "
        "same value on every row, shown here for direct comparison with Stock ATH Return%."
    ),
    "Nifty 52wkLow Return%": (
        "Nifty 50's own % change from its 52-week low (intraday Low) to today's close -- "
        "same value on every row, shown here for direct comparison with Stock 52wkLow Return%."
    ),
    "Stock ATH Return%": (
        "This stock's own % change from its closing price ON THE SAME DATE as Nifty 50's "
        "all-time-high, to today's close."
    ),
    "Stock 52wkLow Return%": (
        "This stock's own % change from its closing price ON THE SAME DATE as Nifty 50's "
        "52-week low, to today's close."
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
    for drawdown_col in _DRAWDOWN_DISPLAY_COLUMNS:
        if drawdown_col in display_df.columns:
            display_df[drawdown_col] = pd.to_numeric(display_df[drawdown_col], errors="coerce").round(2)
    display_df = display_df.rename(columns=_EXTRA_DISPLAY_NAMES)
    cols = [_EXTRA_DISPLAY_NAMES.get(c, c) for c in cols]

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
            # NiftyATH vs Stock / Nifty52wkLow vs Stock (2026-11-22): positive = this stock has
            # outperformed Nifty 50 since that reference date, negative = underperformed.
            {"if": {"filter_query": f"{{{col}}} > 0", "column_id": col},
             "color": "#155724", "fontWeight": "600"}
            for col in ("NiftyATH vs Stock", "Nifty52wkLow vs Stock")
        ] + [
            {"if": {"filter_query": f"{{{col}}} < 0", "column_id": col},
             "color": "#721c24", "fontWeight": "600"}
            for col in ("NiftyATH vs Stock", "Nifty52wkLow vs Stock")
        ],
    )


def _format_age(age: pd.Timedelta) -> str:
    total_minutes = age.total_seconds() / 60
    if total_minutes < 60:
        return f"{int(total_minutes)} min ago"
    if age.days == 0:
        return f"{age.total_seconds() / 3600:.1f} hours ago"
    return f"{age.days}d {int(age.seconds // 3600)}h ago"


def _staleness_banner(loaded_date, updated_at=None):
    """2026-10-11: always-visible "last updated" signal (not just a warning-when-stale one),
    so a cron delay/skip is visible on the dashboard itself -- see
    modules/turtle/callbacks.py::_staleness_banner for the full reasoning. ``updated_at`` is
    touched by EITHER of turtlequant_signals_latest's two writers -- the weekly fundamentals
    job (generate_turtlequant_signals.py) or the daily drawdown job
    (generate_turtlequant_benchmark_drawdown.py) -- so the threshold is scaled to the weekly
    job's cadence (the looser of the two) rather than claiming a single fixed schedule.
    """
    if updated_at is not None and not pd.isna(updated_at):
        now_utc = pd.Timestamp.now(tz="UTC")
        age = now_utc - updated_at
        age_hours = age.total_seconds() / 3600
        ist = updated_at.tz_convert("Asia/Kolkata")
        if age_hours < 24 * 8:       # within a week + a day of slack
            bg, fg, border = "#e7f3ff", "#0c5488", "#b6e0fe"
        elif age_hours < 24 * 10:
            bg, fg, border = "#fff3cd", "#856404", "#ffe69c"
        else:
            bg, fg, border = "#f8d7da", "#721c24", "#f5c6cb"
        return html.Div(
            f"🕐 Turtle Quant data last updated: {ist.strftime('%Y-%m-%d %H:%M')} IST "
            f"({updated_at.strftime('%H:%M')} UTC) — {_format_age(age)} "
            f"(drawdown comparison refreshes daily; Sector/Industry refresh weekly, Sunday).",
            className="status-message",
            style={"backgroundColor": bg, "color": fg, "border": f"1px solid {border}", "margin": "8px 0"},
        )

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


def _nifty_reference_caption(nifty_ref: dict):
    """2026-11-22: a small info line showing the shared Nifty 50 ATH/52-week-low/today
    reference every row's drawdown-comparison columns are anchored to -- without this, the
    dates/prices behind "NiftyATH vs Stock" etc. would be invisible on the dashboard itself.
    None if the reference hasn't been computed yet (table not migrated, or the batch job
    hasn't run)."""
    if not nifty_ref or nifty_ref.get("ath_price") is None:
        return None
    ath_return = bd.pct_return(nifty_ref.get("ath_price"), nifty_ref.get("today_price"))
    low_return = bd.pct_return(nifty_ref.get("low_52wk_price"), nifty_ref.get("today_price"))
    return html.Div(
        f"📍 Nifty 50 reference — ATH: {nifty_ref['ath_price']:,.2f} on {nifty_ref['ath_date']} "
        f"({ath_return:+.2f}% to today) · 52wk Low: {nifty_ref['low_52wk_price']:,.2f} on "
        f"{nifty_ref['low_52wk_date']} ({low_return:+.2f}% to today) · "
        f"Today: {nifty_ref['today_price']:,.2f} on {nifty_ref['today_date']}",
        className="status-message",
        style={"backgroundColor": "#eef2ff", "color": "#3730a3", "border": "1px solid #c7d2fe", "margin": "8px 0"},
    )


def _banner(loaded_date, updated_at, nifty_ref):
    """Combines the existing staleness banner with the new Nifty 50 reference caption into one
    children list for the "tq-staleness-banner" Output -- either piece may be None (e.g. no
    data loaded yet) without breaking the other."""
    pieces = [p for p in (_staleness_banner(loaded_date, updated_at), _nifty_reference_caption(nifty_ref)) if p]
    return pieces or None


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
         Input("tq-performance-filter", "value"),
         Input("tq-fundamental-filter", "value"),
         Input("tq-auto-refresh-interval", "n_intervals"),
         Input("tq-holdings-tags", "children")],  # re-render immediately on add/remove
        prevent_initial_call=False,
    )
    def render_turtlequant(indices_value, sector_value, stock_value, performance_filter_values,
                            fundamental_filter_values, _n_intervals, _holdings_tags):
        # Re-sync on every render, not just at process boot -- same reasoning as
        # modules/turtle/callbacks.py::render_turtle.
        data_manager.load_turtlequant_data_on_startup()

        df = data_manager.turtlequant_signals_df.copy()
        loaded_date = data_manager.LOADED_TURTLEQUANT_FILE_DATE
        updated_at = data_manager.LOADED_TURTLEQUANT_UPDATED_AT
        nifty_ref = data_manager.turtlequant_nifty_benchmark

        if df.empty:
            return (
                _empty_state(
                    "No Turtle Quant signals available.",
                    "Run generate_turtlequant_signals.py to populate turtlequant_signals_<date>.csv.",
                ),
                _banner(loaded_date, updated_at, nifty_ref),
            )

        # Nifty_ATH_Return_Pct/Nifty_52WkLow_Return_Pct (2026-11-22): the SAME value on every
        # row (Nifty 50's own return, not a per-stock figure) -- broadcast from the single
        # shared reference rather than stored per symbol. None on every row if the reference
        # hasn't been computed yet.
        nifty_ath_return = bd.pct_return(nifty_ref.get("ath_price"), nifty_ref.get("today_price")) if nifty_ref else None
        nifty_low_return = bd.pct_return(nifty_ref.get("low_52wk_price"), nifty_ref.get("today_price")) if nifty_ref else None
        df["Nifty_ATH_Return_Pct"] = round(nifty_ath_return, 2) if nifty_ath_return is not None else None
        df["Nifty_52WkLow_Return_Pct"] = round(nifty_low_return, 2) if nifty_low_return is not None else None

        categories_df = data_manager.nse_categories_df
        categories_map = (
            dict(zip(categories_df["Symbol"], categories_df["NSE_Categories"]))
            if not categories_df.empty else {}
        )
        df["Indices"] = df["Symbol"].map(categories_map)

        # 2026-11-22, per explicit user request: "ATH Performance"/"52wk Low Performance"
        # checkboxes keep only stocks that OUTPERFORMED Nifty 50 since that reference date --
        # RS_vs_Nifty_ATH/RS_vs_Nifty_52WkLow are each (stock's own return - Nifty's own return)
        # over that span, so > 0 means the stock beat Nifty. Missing values (None/NaN, e.g. a
        # recently-listed stock with no price history back to the reference date) are excluded
        # by a ticked filter, same "missing data doesn't pass" convention used elsewhere.
        performance_filter_values = performance_filter_values or []
        if "ath_performance" in performance_filter_values and "RS_vs_Nifty_ATH" in df.columns:
            df = df[df["RS_vs_Nifty_ATH"] > 0]
        if "low52wk_performance" in performance_filter_values and "RS_vs_Nifty_52WkLow" in df.columns:
            df = df[df["RS_vs_Nifty_52WkLow"] > 0]

        # 2026-11-22, per explicit user request: "TTM Profit Flag"/"TTM Sales Flag" checkboxes
        # keep only stocks where that flag is True. Missing values (None/NaN) are excluded by a
        # ticked filter, same "missing data doesn't pass" convention used above.
        fundamental_filter_values = fundamental_filter_values or []
        if "ttm_profit_flag" in fundamental_filter_values and "ATH_Profit_Flag" in df.columns:
            df = df[df["ATH_Profit_Flag"] == True]  # noqa: E712 (explicit True, not truthy, to exclude NaN)
        if "ttm_sales_flag" in fundamental_filter_values and "ATH_Sales_Flag" in df.columns:
            df = df[df["ATH_Sales_Flag"] == True]  # noqa: E712

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
            return _empty_state("No stocks match the current filters."), _banner(loaded_date, updated_at, nifty_ref)

        return _table(df), _banner(loaded_date, updated_at, nifty_ref)
