"""
Dash callbacks for the Turtle Strategy tab (docs/TURTLE_STRATEGY_PLAN.md).

One main render callback: Indices/Sector/Stock/ATH-only/Yesterday filters -> a colour-coded
results table, plus a staleness banner. Read-only — nothing here places or modifies trades.
"""
from datetime import datetime

import pandas as pd
from dash import Input, Output, dash_table, html

import data_manager
from . import compute

_DISPLAY_COLUMNS = [
    "Symbol", "Sector", "Industry", "Current_Price", "ATH_Price_Flag", "TTM_Net_Profit",
    "ATH_Profit_Flag", "TTM_Net_Sales", "ATH_Sales", "ATH_Sales_Flag", "Above_MA212_Flag",
    "RS_vs_Sector", "RS_vs_Benchmark", "Signal",
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
        "Standalone trailing-twelve-month net profit (₹ Cr), from screener.in's own "
        "pre-computed TTM column (standalone basis, not consolidated)."
    ),
    "ATH_Profit_Flag": (
        "True if standalone TTM Net Profit is at/above the highest annual Net Profit on "
        "record (any year, including the latest). TTM and the historical max both come from "
        "the same screener.in table — same ₹ Cr units, same standalone basis — so this is a "
        "direct comparison, no EPS/shares-outstanding conversion needed.\n\n"
        "`ATH_Profit_Flag = TTM_Net_Profit ≥ max(all annual Net Profit years)`"
    ),
    "TTM_Net_Sales": (
        "Standalone trailing-twelve-month net sales/revenue (₹ Cr), from screener.in's own "
        "pre-computed TTM column (standalone basis, not consolidated)."
    ),
    "ATH_Sales": "Highest annual sales (₹ Cr) on record, any year (screener.in). Purely informational.",
    "ATH_Sales_Flag": (
        "True if standalone TTM Net Sales is at/above the highest annual sales on record "
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
    "RS_vs_Sector": (
        "Stock's 365-day return minus its sector's *leave-one-out* average 365-day return "
        "(every other stock in the same sector, excluding itself).\n\n"
        "`stock_RS − sector_RS`   (positive = beating its sector)"
    ),
    "RS_vs_Benchmark": (
        "Stock's 365-day return minus the benchmark's 365-day return — Nifty 500, standing "
        "in for BSE 500 (not on yfinance).\n\n"
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
    return dash_table.DataTable(
        id="tt-signals-table",
        columns=[{"name": c.replace("_", " "), "id": c} for c in cols],
        data=df[cols].to_dict("records"),
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
