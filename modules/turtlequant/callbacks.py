"""
Dash callbacks for the Turtle Quant tab.

Four callbacks: the main render (Indices/Sector/Stock/Signal filters -> a colour-coded results
table, plus a staleness banner), a "My Holdings" add/remove callback that writes only to the
logged-in user's own turtlequant_watchlist rows (via modules.auth.user_store) -- never touches
market-data tables -- and the admin-only per-stock "Analyze" deep-research feature (select one
row -> kick off 3 sequential LLM research calls in a background thread -> poll until done; see
modules/turtlequant/stock_analysis.py and analysis_store.py).
"""
import json
import threading
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
import flask_login
import pandas as pd
from dash import ALL, Input, Output, State, dash_table, dcc, html

import data_manager
from modules.auth import user_store
from modules.turtle.compute import filter_by_index
from . import analysis_store, compute as tq_compute, screener as sc, stock_analysis

_DISPLAY_COLUMNS = [
    "Symbol", "Indices", "Broad_Sector", "Sector", "Industry", "Current_Price", "Signal_Date", "Signal",
    "RS_Long_Term", "RS_Short_Term", "ADX", "RSI",
    "SuperTrend_Direction", "Volume_Building", "Price_Above_MA13",
] + sc.QUALITY_COLUMNS

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
    # 2026-10-01: fundamental quality/valuation flags, from screener.in's Balance Sheet/Ratios/
    # Cash Flows/Profit & Loss history (10 years where available) plus historical stock prices.
    # See modules/turtle/quality_flags.py for every exact formula.
    "Book_Value_CAGR_10Y": "10-year CAGR (%) of (Equity Capital + Reserves) -- total book value growth.",
    "Book_Value_Growth_Flag": "True if Book Value CAGR (10Y) > 10%. Blank if fewer than 5 years of data exist.",
    "EPS_CAGR_10Y": "10-year CAGR (%) of EPS (Rs).",
    "EPS_Growth_Flag": "True if EPS CAGR (10Y) > 10%. Blank if fewer than 5 years of data exist.",
    "ROCE_Avg_10Y": "Plain average of ROCE% over the last 10 years (not a per-year minimum).",
    "ROCE_Flag": "True if ROCE Avg (10Y) > 10%. Blank if fewer than 5 years of data exist.",
    "Sales_CAGR_10Y": "10-year CAGR (%) of Sales/Revenue.",
    "Sales_Growth_Flag": "True if Sales CAGR (10Y) > 10%. Blank if fewer than 5 years of data exist.",
    "Promoter_Holding_Change_3Y": (
        "Percentage-point change in promoter holding over screener.in's real available window "
        "(~3 years / 12 quarters -- NOT 10 years, no free 10-year promoter-holding source exists)."
    ),
    "Promoter_Holding_Flag": "True if promoter holding is the same or higher than ~3 years ago.",
    "Interest_Coverage": (
        "Latest year's (Profit before tax + Interest) / Interest. Blank if the company has zero "
        "interest expense (see the flag -- a debt-free company passes automatically)."
    ),
    "Interest_Coverage_Flag": (
        "True if Interest Coverage > 5, OR the company has zero interest expense (no debt to "
        "service -- treated as an automatic pass, not insufficient data)."
    ),
    "PB_Current": "Current Price-to-Book, computed the same derivation method as every historical year below (for a fair comparison).",
    "PB_5Y_Avg": "Average Price-to-Book over the last 5 fiscal years.",
    "PB_Flag": "True if the 5-year average P/B is higher than the current P/B -- i.e. the stock is cheaper than its own recent history.",
    "PS_Current": "Current Price-to-Sales, same derivation method as the 5-year average.",
    "PS_5Y_Avg": "Average Price-to-Sales over the last 5 fiscal years.",
    "PS_Flag": "True if the 5-year average P/S is higher than the current P/S.",
    "PCF_Current": "Current Price-to-(Operating)-Cash-Flow, same derivation method as the 5-year average.",
    "PCF_5Y_Avg": "Average Price-to-Cash-Flow over the last 5 fiscal years.",
    "PCF_Flag": "True if the 5-year average P/CF is higher than the current P/CF.",
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
    _quality_numeric_cols = [c for c in sc.QUALITY_COLUMNS if not c.endswith("_Flag")]
    for num_col in _quality_numeric_cols:
        if num_col in display_df.columns:
            display_df[num_col] = pd.to_numeric(display_df[num_col], errors="coerce").round(2)
    for blank_col in ("Signal", "Signal_Date"):
        if blank_col in display_df.columns:
            display_df[blank_col] = display_df[blank_col].where(display_df[blank_col].notna(), None)

    return dash_table.DataTable(
        id="tq-signals-table",
        columns=[{"name": c.replace("_", " "), "id": c} for c in cols],
        data=display_df.to_dict("records"),
        row_selectable="single",
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


def _is_admin(app) -> bool:
    """Same inline pattern used elsewhere in this app (app.py's _is_admin, modules/admin/
    callbacks.py:128-130) -- no shared helper module exists yet, so this mirrors it exactly
    rather than introducing a new one just for this feature."""
    user = flask_login.current_user
    return bool(
        user.is_authenticated and getattr(user, "email", None)
        == app.server.config.get("ADMIN_EMAIL", "pathikc129@gmail.com")
    )


def _citations_block(citations_json):
    if not citations_json:
        return None
    try:
        urls = json.loads(citations_json)
    except (TypeError, ValueError):
        return None
    if not urls:
        return None
    return html.Div([
        html.P("Sources:", style={"fontWeight": 600, "fontSize": "12px", "margin": "8px 0 2px 0"}),
        html.Ul([html.Li(html.A(u, href=u, target="_blank")) for u in urls],
                style={"fontSize": "12px"}),
    ])


def _report_section(title, report_text, citations_json):
    if not report_text:
        return None
    return html.Div([
        html.H5(title, style={"marginTop": "16px"}),
        dcc.Markdown(report_text, style={"fontSize": "14px"}),
        _citations_block(citations_json),
    ])


# Model name substrings known to actually do real, cited web search grounding (Perplexity's
# Sonar family, or any model routed through OpenRouter's ":online" web-search plugin). Anything
# else -- including "openrouter/free" -- gets the fabrication-risk warning below, since a real,
# live test on LICI confirmed a free-tier model will confidently invent an entire fictional
# business, executive, and financial history rather than writing "NOT FOUND" as instructed.
_GROUNDED_MODEL_MARKERS = ("perplexity/sonar", ":online")


def _report_may_be_fabricated(model: str) -> bool:
    if not model:
        return True  # unknown model (e.g. a row from before this column existed) -- assume the worst
    model_lower = model.lower()
    return not any(marker in model_lower for marker in _GROUNDED_MODEL_MARKERS)


def _fabrication_warning_banner(model: str):
    return html.Div([
        html.Strong("⚠️ Unverified AI research -- do not trust without checking. "),
        html.Span(
            f"Generated by \"{model or 'an unrecorded model'}\", which has no real web search "
            "and is confirmed (live-tested on a real stock) to invent plausible-sounding but "
            "entirely FICTIONAL company facts, executives, and financials rather than admitting "
            "it doesn't know. Treat every claim, name, and number below as unverified until you "
            "independently confirm it against the actual company's real filings."
        ),
    ], style={"backgroundColor": "#f8d7da", "color": "#721c24", "border": "2px solid #dc3545",
              "borderRadius": "6px", "padding": "12px", "marginBottom": "12px", "fontSize": "13px"})


def _render_analysis_panel(row):
    """Renders whatever stages of a turtlequant_stock_analysis row are available so far --
    called both right after a fresh 'Analyze' click and on every poll tick, so the panel fills
    in progressively as each of the 3 sequential reports completes."""
    if row is None:
        return html.Div()

    status = row.get("status")
    children = []

    if status in ("running", "done") and _report_may_be_fabricated(row.get("model")):
        children.append(_fabrication_warning_banner(row.get("model")))

    if status == "error":
        children.append(html.Div(
            f"Analysis failed: {row.get('error_message') or 'unknown error'}",
            className="status-message error", style={"backgroundColor": "#f8d7da", "color": "#721c24"},
        ))
    elif analysis_store.is_stale(row):
        children.append(html.Div(
            "This analysis seems to have stalled (no progress in the last few minutes) -- "
            "the background process may have been restarted mid-run. Click 'Analyze Selected "
            "Stock' again to retry.",
            className="status-message", style={"backgroundColor": "#fff3cd", "color": "#856404"},
        ))
    elif status == "running":
        children.append(html.Div(
            "Analysis in progress -- this takes a few minutes (3 sequential research calls). "
            "This panel updates automatically as each report completes.",
            className="status-message info",
        ))

    for title, field, citations_field in [
        ("1. Management Quality", "management_report", "management_citations"),
        ("2. Business Quality", "business_report", "business_citations"),
        ("3. Price & Final Decision", "price_report", "price_citations"),
    ]:
        section = _report_section(title, row.get(field), row.get(citations_field))
        if section is not None:
            children.append(section)

    if status == "done":
        children.append(html.P(
            f"Completed {row.get('completed_at', '')}", style={"fontSize": "12px", "color": "#6c757d"}
        ))

    return html.Div(children)


def _build_selection_panel(app, symbol, company, row):
    """Header (stock name) + admin-only Analyze/Re-analyze button + whatever analysis content
    exists so far. Shown to EVERY user on row selection (so a non-admin can still see a
    previously-completed analysis -- this is read access, not the expensive trigger), but only
    an admin ever sees the button that actually spends OpenRouter credit.
    """
    children = [html.H4(f"{company} ({symbol})")]

    if _is_admin(app):
        already_running = bool(row and row.get("status") == "running" and not analysis_store.is_stale(row))
        label = "Analyze Selected Stock"
        if row and row.get("status") in ("done", "error"):
            label = "Re-analyze"
        children.append(dbc.Button(
            label, id={"type": "tq-analyze-btn", "index": 0},
            color="primary", outline=True, disabled=already_running, className="mb-2", n_clicks=0,
        ))

    if row:
        children.append(_render_analysis_panel(row))
    elif not _is_admin(app):
        children.append(html.P("No AI research available for this stock yet.",
                                style={"color": "#6c757d", "fontSize": "13px"}))

    return html.Div(children)


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

    @app.callback(
        Output("tq-analysis-panel", "children"),
        Output("tq-analysis-panel", "style"),
        Output("tq-analysis-selected-symbol", "data"),
        Output("tq-analysis-selected-company", "data"),
        Output("tq-analysis-poll-interval", "disabled"),
        Input("tq-signals-table", "selected_rows"),
        Input("tq-signals-table", "derived_virtual_data"),
        Input("tq-analysis-poll-interval", "n_intervals"),
        Input({"type": "tq-analyze-btn", "index": ALL}, "n_clicks"),
        State("tq-analysis-selected-symbol", "data"),
        State("tq-analysis-selected-company", "data"),
        prevent_initial_call=False,
    )
    def manage_stock_analysis(selected_rows, table_data, _n_intervals, start_clicks,
                               stored_symbol, stored_company):
        """One combined callback for select / poll / start-analyze -- Dash callbacks can only
        target a given Output from one callback, and tq-analysis-panel needs updating from all
        three triggers, so they're merged here rather than fighting over the same Output.
        """
        hidden = {"display": "none"}
        visible = {"display": "block", "marginTop": "16px", "padding": "16px",
                   "border": "1px solid #dee2e6", "borderRadius": "8px"}

        ctx = dash.callback_context
        triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""

        if "tq-signals-table" in triggered or not ctx.triggered:
            if not selected_rows or not table_data:
                return html.Div(), hidden, None, None, True
            row = table_data[selected_rows[0]]
            symbol = str(row.get("Symbol", "")).upper().strip()
            company = str(row.get("Company", symbol))
            if not symbol:
                return html.Div(), hidden, None, None, True

            existing = analysis_store.get_analysis(symbol)
            panel = _build_selection_panel(app, symbol, company, existing)
            poll_disabled = not (existing and existing.get("status") == "running")
            return panel, visible, symbol, company, poll_disabled

        # Poll tick or Analyze-button click -- both need the currently-selected symbol/company.
        symbol, company = stored_symbol, stored_company
        if not symbol:
            raise dash.exceptions.PreventUpdate

        if "tq-analyze-btn" in triggered and any(start_clicks):
            if not _is_admin(app):
                raise dash.exceptions.PreventUpdate
            existing = analysis_store.get_analysis(symbol)
            if existing and existing.get("status") == "running" and not analysis_store.is_stale(existing):
                # Already in flight -- don't double-spend on a double click.
                panel = _build_selection_panel(app, symbol, company, existing)
                return panel, visible, symbol, company, False

            admin_email = flask_login.current_user.email
            analysis_store.start_analysis(symbol, company, admin_email, stock_analysis.current_model())
            threading.Thread(
                target=stock_analysis.run_full_analysis, args=(symbol, company), daemon=True,
            ).start()
            row = analysis_store.get_analysis(symbol)
            panel = _build_selection_panel(app, symbol, company, row)
            return panel, visible, symbol, company, False

        # Poll tick.
        row = analysis_store.get_analysis(symbol)
        panel = _build_selection_panel(app, symbol, company, row)
        still_running = bool(row and row.get("status") == "running" and not analysis_store.is_stale(row))
        return panel, visible, symbol, company, not still_running
