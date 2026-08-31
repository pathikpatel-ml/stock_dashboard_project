"""
Dash callbacks for the Turtle Strategy tab (docs/TURTLE_STRATEGY_PLAN.md).

One main render callback: Indices/Sector/Stock/ATH-only/Yesterday filters -> a colour-coded
results table, plus a staleness banner. Read-only — nothing here places or modifies trades
EXCEPT the watchlist add/remove callback, which writes only to the logged-in user's own
turtle_watchlist rows (via modules.auth.user_store) -- never touches market-data tables.
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
from . import compute

_DISPLAY_COLUMNS = [
    # TTM_Net_Profit, TTM_Net_Sales, ATH_Sales deliberately omitted (2026-08-20, requested) --
    # display-only, table-width reduction. The flags they support (ATH_Profit_Flag,
    # ATH_Sales_Flag) still render; the raw ₹Cr figures stay in the underlying CSV, just not
    # shown here. No calculation/formula/Signal logic touched.
    "Symbol", "Sector", "Industry", "Current_Price", "Signal", "ATH_Price_Flag",
    "ATH_Profit_Flag", "ATH_Sales_Flag",
    "Above_MA212_Flag", "RS_Peer_Group", "RS_vs_Sector", "RS_vs_Benchmark",
]

# Shown on hover over each column header (docs/TURTLE_STRATEGY_PLAN.md) so the table is
# self-explanatory without needing to cross-reference the plan doc or ask what a column means.
_COLUMN_TOOLTIPS = {
    "Symbol": "NSE trading symbol.",
    "Sector": "Sector classification (Yahoo Finance), e.g. Financial Services, Technology.",
    "Industry": "More specific industry classification within the sector.",
    "Current_Price": (
        "Live daily close price, refreshed intraday (~every 2-3h on market days). "
        "Falls back to the weekly-cron snapshot only if no live data is available."
    ),
    "ATH_Price_Flag": (
        "True if the price is at or within 5% of the stock's all-time-high close.\n\n"
        "`current_price ≥ historical_max_close × 0.95`"
    ),
    "TTM_Net_Profit": (
        "Consolidated trailing-twelve-month net profit (₹ Cr), from screener.in's own "
        "pre-computed TTM column (consolidated basis, includes subsidiaries)."
    ),
    "ATH_Profit_Flag": (
        "True if consolidated TTM Net Profit is at/above the highest annual Net Profit on "
        "record (any year, including the latest). TTM and the historical max both come from "
        "the same screener.in table — same ₹ Cr units, same consolidated basis — so this is a "
        "direct comparison, no EPS/shares-outstanding conversion needed.\n\n"
        "`ATH_Profit_Flag = TTM_Net_Profit ≥ max(all annual Net Profit years)`"
    ),
    "TTM_Net_Sales": (
        "Consolidated trailing-twelve-month net sales/revenue (₹ Cr), from screener.in's own "
        "pre-computed TTM column (consolidated basis, includes subsidiaries)."
    ),
    "ATH_Sales": "Highest annual sales (₹ Cr) on record, any year (screener.in). Purely informational.",
    "ATH_Sales_Flag": (
        "True if consolidated TTM Net Sales is at/above the highest annual sales on record "
        "(any year, including the latest) — same shape as ATH_Profit_Flag, same screener.in "
        "table. Informational only — not used in Signal.\n\n"
        "`ATH_Sales_Flag = TTM_Net_Sales ≥ max(all annual Net Sales years)`"
    ),
    "Above_MA212_Flag": (
        "True if price is above the live 212-day moving average of daily closes "
        "(Turtle's exit-price proxy). Falls back to the weekly-cron CSV's MA200 if fewer "
        "than 212 days of live price history exist (no MA212 column exists in that file).\n\n"
        "`current_price > MA212`"
    ),
    "RS_Peer_Group": (
        "The peer basket used to compute RS vs Sector. If the stock belongs to an NSE "
        "sectoral index (NIFTY BANK, NIFTY PHARMA, NIFTY IT, etc.), that index's other "
        "members are used — a real, market-curated peer set. Only falls back to the broad "
        "Sector column (e.g. \"Sector: Healthcare\") for stocks not in any sectoral index, "
        "since sectoral indices only cover large/established names. The broad Sector tag can "
        "lump unrelated sub-industries together (e.g. pharma manufacturers with hospitals), "
        "so the sectoral-index basket is preferred whenever one is available."
    ),
    "RS_vs_Sector": (
        "Stock's 52-week return (each week's highest daily close vs. 52 weeks earlier) "
        "minus its RS-peer-group's *leave-one-out* average 52-week return (every other "
        "member of the RS_Peer_Group basket, excluding itself).\n\n"
        "`stock_RS − peer_group_RS`   (positive = beating its peer group)"
    ),
    "RS_vs_Benchmark": (
        "Stock's 52-week return (weekly high-close basis) minus the benchmark's 52-week "
        "return — Nifty 500, standing in for BSE 500 (not on yfinance).\n\n"
        "`stock_RS − benchmark_RS`   (positive = beating the market)"
    ),
    "Signal": (
        "**ADD** — ATH Price + ATH Profit + Outperformance all true.\n\n"
        "**HOLD** — at least 2 of {ATH Profit, Above MA212, Outperformance} true.\n\n"
        "**EXIT** — everything else.\n\n"
        "Outperformance = RS vs Sector > 0 **and** RS vs Benchmark > 0 (must beat both). "
        "ATH Sales is not part of this — display-only."
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
        # Whole-rupee display (182.02158 -> 182) -- Int64 (nullable) so a missing price stays
        # blank instead of forcing every row to a float just to accommodate the rare NaN.
        display_df["Current_Price"] = pd.to_numeric(
            display_df["Current_Price"], errors="coerce"
        ).round(0).astype("Int64")
    return dash_table.DataTable(
        id="tt-signals-table",
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
            {"if": {"filter_query": '{Signal} = "ADD"'}, "backgroundColor": "#d4edda", "color": "#155724"},
            {"if": {"filter_query": '{Signal} = "HOLD"'}, "backgroundColor": "#fff3cd", "color": "#856404"},
            {"if": {"filter_query": '{Signal} = "EXIT"'}, "backgroundColor": "#f8d7da", "color": "#721c24"},
        ],
    )


def _sector_pulse_table(df):
    """Sector Pulse: one row per sectoral index (not per stock) -- ATH_Price_Flag and
    RS_vs_Nifty50, both computed directly on the index's own price series (see
    screener.fetch_sector_pulse_table). Laid out as two side-by-side 3-column halves (Sector
    Name / ATH Price Flag / RS vs Nifty50), as requested, rather than one long list or a card
    grid -- 10 real indices split 5-and-5.
    """
    if df is None or df.empty:
        return None

    display = df.copy()
    display["ATH_Price_Flag"] = display["ATH_Price_Flag"].map({True: "Yes", False: "No"})

    half = (len(display) + 1) // 2
    left = display.iloc[:half].reset_index(drop=True)
    right = display.iloc[half:].reset_index(drop=True)
    while len(right) < len(left):
        right.loc[len(right)] = {"Sector": "", "ATH_Price_Flag": "", "RS_vs_Nifty50": None}

    combined = pd.DataFrame({
        "Sector_1": left["Sector"], "ATH_1": left["ATH_Price_Flag"], "RS_1": left["RS_vs_Nifty50"],
        "Sector_2": right["Sector"], "ATH_2": right["ATH_Price_Flag"], "RS_2": right["RS_vs_Nifty50"],
    })

    return html.Div([
        html.H5("Sector Pulse", style={"margin": "16px 0 8px 0", "fontSize": "15px"}),
        dash_table.DataTable(
            id="tt-sector-pulse-table",
            columns=[
                {"name": "Sector Name", "id": "Sector_1"},
                {"name": "ATH Price Flag", "id": "ATH_1"},
                {"name": "RS vs Nifty50", "id": "RS_1"},
                {"name": "Sector Name", "id": "Sector_2"},
                {"name": "ATH Price Flag", "id": "ATH_2"},
                {"name": "RS vs Nifty50", "id": "RS_2"},
            ],
            data=combined.to_dict("records"),
            export_format="xlsx",
            export_headers="display",
            style_table={"overflowX": "auto"},
            style_cell={"textAlign": "center", "fontSize": "13px", "padding": "8px",
                        "fontFamily": "Inter, sans-serif"},
            style_header={"backgroundColor": "#f1f5f9", "fontWeight": "600"},
            style_data_conditional=[
                {"if": {"column_id": "ATH_1", "filter_query": '{ATH_1} = "Yes"'},
                 "backgroundColor": "#d4edda", "color": "#155724"},
                {"if": {"column_id": "ATH_2", "filter_query": '{ATH_2} = "Yes"'},
                 "backgroundColor": "#d4edda", "color": "#155724"},
            ],
        ),
    ])


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


def _live_price_freshness_note(live_prices_df):
    """generate_turtle_live_prices.py refreshes Current_Price several times a day,
    independent of the once-daily ADD/HOLD/EXIT recompute -- surface when that last
    happened so it isn't confused with the (once-daily) staleness banner above.
    """
    if live_prices_df is None or live_prices_df.empty or "Price_As_Of" not in live_prices_df.columns:
        return None
    try:
        latest = pd.to_datetime(live_prices_df["Price_As_Of"], errors="coerce", utc=True).max()
    except Exception:
        return None
    if pd.isna(latest):
        return None
    return html.Div(
        f"💹 Prices refreshed intraday — last update {latest.strftime('%Y-%m-%d %H:%M UTC')} "
        f"(ADD/HOLD/EXIT signals still recompute once daily).",
        className="status-message", style={"backgroundColor": "#e7f3ff", "color": "#0c5488",
                                           "border": "1px solid #b6e0fe", "margin": "8px 0",
                                           "fontSize": "12px"},
    )


def _banners(loaded_date, live_prices_df):
    parts = [b for b in (_staleness_banner(loaded_date), _live_price_freshness_note(live_prices_df)) if b]
    return html.Div(parts) if parts else None


def _current_user_id():
    if flask_login.current_user.is_authenticated:
        return flask_login.current_user.id
    return None


def register_turtle_callbacks(app):
    """Register all Turtle Strategy callbacks on the Dash ``app``."""

    @app.callback(
        Output("tt-sector-pulse-container", "children"),
        Input("tt-auto-refresh-interval", "n_intervals"),
        prevent_initial_call=False,
    )
    def render_sector_pulse(_n_intervals):
        # Self-contained reload (same reasoning as render_turtle below) -- independent of the
        # Indices/Sector/Stock/ATH-only/Yesterday filters, since this panel is index-level,
        # not stock-level, so those filters don't apply to it at all.
        data_manager.load_turtle_data_on_startup()
        return _sector_pulse_table(data_manager.turtle_sector_pulse_df)

    @app.callback(
        Output("tt-watchlist-tags", "children"),
        Output("tt-watchlist-add-dropdown", "value"),
        Input("tt-watchlist-add-btn", "n_clicks"),
        Input({"type": "del-watchlist", "symbol": ALL}, "n_clicks"),
        State("tt-watchlist-add-dropdown", "value"),
        prevent_initial_call=False,
    )
    def manage_watchlist(_add_clicks, del_clicks, new_symbol):
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        ctx = dash.callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
        if "tt-watchlist-add-btn" in triggered and new_symbol:
            user_store.add_to_watchlist(user_id, new_symbol)
        elif "del-watchlist" in triggered and any(del_clicks):
            id_dict = json.loads(triggered.split(".")[0])
            user_store.remove_from_watchlist(user_id, id_dict["symbol"])

        symbols = user_store.get_watchlist(user_id)
        tags = [
            dbc.Badge(
                [sym, html.Span(" ×", id={"type": "del-watchlist", "symbol": sym},
                                 style={"cursor": "pointer", "marginLeft": "4px"}, n_clicks=0)],
                color="secondary", className="me-1 mb-1 p-2", style={"fontSize": "0.8rem"},
            )
            for sym in symbols
        ]
        return tags, None

    @app.callback(
        [Output("tt-signals-container", "children"),
         Output("tt-staleness-banner", "children")],
        [Input("tt-indices-filter", "value"),
         Input("tt-sector-filter", "value"),
         Input("tt-stock-filter", "value"),
         Input("tt-ath-only-toggle", "value"),
         Input("tt-yesterday-toggle", "value"),
         Input("tt-auto-refresh-interval", "n_intervals"),
         Input("tt-watchlist-tags", "children")],  # re-render immediately on add/remove, so
         # "Indices: My Watchlist" reflects the change without waiting for the next 5-min tick
        prevent_initial_call=False,
    )
    def render_turtle(indices_value, sector_value, stock_value, ath_only, yesterday, _n_intervals, _watchlist_tags):
        # Re-sync from disk/GitHub on every render, not just at process boot. Without this,
        # a long-lived running instance would only ever see whatever turtle_signals_<date>.csv
        # / turtle_live_prices.csv / nse_categories.csv existed when the process last started --
        # daily/intraday cron updates would need a full redeploy to ever show up. This reuses
        # the exact same local -> GitHub-raw fallback (data_manager._read_csv_with_candidates)
        # the startup loader already uses, so a plain HTTPS fetch of a small CSV is all this
        # costs; it's the same mechanism V20/Breakout data loading already has, just invoked
        # repeatedly instead of once.
        data_manager.load_turtle_data_on_startup()

        if yesterday and "yesterday" in yesterday:
            df, _filename = data_manager.get_turtle_signals_by_offset(1)
            loaded_date = data_manager._extract_date_from_name(_filename or "", r"(\d{8})")
            live_prices_df = None  # the intraday cache only ever reflects "today"
        else:
            df = data_manager.turtle_signals_df.copy()
            loaded_date = data_manager.LOADED_TURTLE_FILE_DATE
            live_prices_df = data_manager.turtle_live_prices_df

        if df.empty:
            return (
                _empty_state(
                    "No Turtle signals available.",
                    "Run generate_turtle_signals.py to populate turtle_signals_<date>.csv." if not yesterday
                    else "No prior-day turtle signals file was found.",
                ),
                _banners(loaded_date, live_prices_df),
            )

        if live_prices_df is not None and not live_prices_df.empty:
            df = compute.merge_live_prices(df, live_prices_df)

        if indices_value == "My Watchlist":
            # Not a real NSE index -- filter to the logged-in user's own turtle_watchlist rows
            # instead of the NSE-category membership check below.
            user_id = _current_user_id()
            watchlist_symbols = set(user_store.get_watchlist(user_id)) if user_id else set()
            df = df[df["Symbol"].isin(watchlist_symbols)]
        else:
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
            return _empty_state("No stocks match the current filters."), _banners(loaded_date, live_prices_df)

        return _table(df), _banners(loaded_date, live_prices_df)
