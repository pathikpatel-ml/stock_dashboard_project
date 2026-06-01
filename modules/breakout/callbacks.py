"""
Dash callbacks for the Multi-Year Breakout strategy tab.

Wires the six dashboard modules to the data loaded by ``data_manager`` and to the engine:
  * main render (signals / watchlist / positions / in-app alerts / staleness banner),
  * signal-row click  -> trade-plan detail + inline historical backtest,
  * Backtest tab       -> on-demand backtest for any symbol,
  * Delivery Analyzer  -> daily delivery table + colour-coded trend chart.

Read-only: nothing here places or modifies trades.
"""
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dash_table, dcc, html

import data_manager
from . import backtest as bt
from . import constants as C
from . import delivery_data as dd
from . import positions as pos
from . import screener as sc

# Column subsets shown in the two main tables (kept compact; full data is in the CSV).
_SIGNAL_DISPLAY = [
    "Symbol", "CMP", "Entry_Price", "Stop_Loss", "Target_1", "Risk_Reward",
    "Resistance_Age_Years", "Delivery_Pct", "Volume_Spike_x", "Candle_Quality",
    "Supply_Absorption", "Alert_Date",
]
_WATCH_DISPLAY = [
    "Symbol", "CMP", "Resistance", "Distance_to_Breakout_Pct", "Resistance_Age_Years",
    "Support", "Range_Size", "Volume_Trend", "Delivery_Pct", "Priority_Score",
]


def _empty_state(message: str, hint: str = "") -> html.Div:
    return html.Div(
        [html.P(message, style={"margin": 0, "fontWeight": 600}),
         html.P(hint, style={"margin": "4px 0 0 0", "fontSize": "13px", "color": "#6c757d"}) if hint else None],
        className="status-message info",
    )


def _funnel_card(rejections_df, universe_size, loaded_date):
    """Compact 'why nothing passed' card built from the breakout_rejections_<date>.csv funnel."""
    if rejections_df is None or rejections_df.empty:
        return None
    df = rejections_df.copy()
    step_meaning = {
        1: "STEP 1 — Universe (penny / illiquid / listed <5y)",
        2: "STEP 2 — Not within 3% of resistance",
        3: "STEP 3 — ATH downtrend filter / lower-highs",
        4: "STEP 4 — No multi-year resistance (>=2 touches near ATH, age >=5y)",
        5: "STEP 5 — Volume trend declining",
        6: "STEP 6 — Delivery % below threshold",
        7: "STEP 7 — Breakout candle invalid (weak close / wick / low volume)",
        8: "STEP 8 — R:R below 1:2 (oversized breakout candle)",
    }
    by_step = df.groupby("Step")["Count"].sum().sort_index()
    total_rej = int(by_step.sum())
    rows = [html.Tr([html.Td(step_meaning.get(int(s), f"STEP {int(s)}"),
                              style={"padding": "3px 12px 3px 0"}),
                     html.Td(f"{int(c):,}", style={"textAlign": "right", "fontWeight": 600})])
            for s, c in by_step.items()]
    top_reasons = df.sort_values("Count", ascending=False).head(5)
    reason_rows = [html.Tr([html.Td(r["Reason_Prefix"], style={"padding": "2px 12px 2px 0",
                                                                "color": "#475569"}),
                            html.Td(f"{int(r['Count']):,}", style={"textAlign": "right"})])
                   for _, r in top_reasons.iterrows()]
    universe_size = universe_size or (int(df["Universe_Size"].iloc[0])
                                       if "Universe_Size" in df.columns else total_rej)
    return html.Div([
        html.H4(f"📊 Screening funnel — {universe_size:,} stocks scanned, "
                f"0 fresh breakouts today",
                style={"marginTop": 0, "marginBottom": "8px", "color": "#0f172a"}),
        html.P(f"Loaded: {loaded_date or 'n/a'}. Multi-year breakouts are deliberately "
               f"selective (5+ year base + Smart Money confirmation). Use the Backtest tab "
               f"on a documented winner (e.g. SANGHVIMOV) to verify the engine end-to-end.",
               style={"fontSize": "13px", "color": "#475569", "marginBottom": "10px"}),
        html.Div(style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "20px"}, children=[
            html.Div([html.Strong("By step", style={"fontSize": "13px"}),
                      html.Table(rows, style={"fontSize": "13px", "width": "100%"})]),
            html.Div([html.Strong("Top reasons", style={"fontSize": "13px"}),
                      html.Table(reason_rows, style={"fontSize": "13px", "width": "100%"})]),
        ]),
    ], className="status-message", style={"backgroundColor": "#f8fafc",
                                            "border": "1px solid #e2e8f0", "padding": "14px"})


def _table(df: pd.DataFrame, columns, table_id, selectable=False, conditional=None):
    cols = [c for c in columns if c in df.columns]
    return dash_table.DataTable(
        id=table_id,
        columns=[{"name": c.replace("_", " "), "id": c} for c in cols],
        data=df[cols].to_dict("records"),
        page_size=20,
        sort_action="native",
        filter_action="native",
        row_selectable="single" if selectable else False,
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "center", "fontSize": "13px", "padding": "8px",
                    "fontFamily": "Inter, sans-serif"},
        style_header={"backgroundColor": "#f1f5f9", "fontWeight": "600"},
        style_data_conditional=(conditional or []) + [
            {"if": {"row_index": "odd"}, "backgroundColor": "#f8f9fa"},
        ],
    )


# ---------------------------------------------------------------------------
# In-app alert badges (doc §9.1 Module 6)
# ---------------------------------------------------------------------------
def _badge(text, color, bg):
    return html.Div(text, style={
        "padding": "8px 12px", "marginBottom": "6px", "borderRadius": "6px",
        "backgroundColor": bg, "color": color, "borderLeft": f"4px solid {color}",
        "fontSize": "13px",
    })


def _build_alerts(signals, watchlist, tracked_positions):
    badges = []
    for _, r in signals.head(15).iterrows():
        badges.append(_badge(
            f"🚀 NEW BREAKOUT — {r.get('Symbol')} | Entry ₹{r.get('Entry_Price')} | "
            f"SL ₹{r.get('Stop_Loss')} | T1 ₹{r.get('Target_1')} | R:R 1:{r.get('Risk_Reward')} | "
            f"Delivery {r.get('Delivery_Pct')}%", "#155724", "#d4edda"))
    for _, r in watchlist.head(10).iterrows():
        badges.append(_badge(
            f"👀 NEAR BREAKOUT — {r.get('Symbol')} is {r.get('Distance_to_Breakout_Pct')}% "
            f"below resistance ₹{r.get('Resistance')}", "#856404", "#fff3cd"))
    if tracked_positions is not None and not tracked_positions.empty:
        for _, r in tracked_positions.iterrows():
            sym = r.get("Symbol")
            status = r.get("SL Status")
            if status == "Red":
                badges.append(_badge(f"🛑 SL HIT — {sym} closed at/below stop loss. Exit per plan.",
                                     "#721c24", "#f8d7da"))
            elif status == "Yellow":
                badges.append(_badge(f"⚠️ SL WARNING — {sym} within {C.SL_YELLOW_PROXIMITY_PCT}% of stop loss.",
                                     "#856404", "#fff3cd"))
            if r.get("T1 Status") == "Reached":
                badges.append(_badge(f"🎯 TARGET 1 REACHED — {sym}. Book 50% and arm the 21-EMA trail.",
                                     "#0c5460", "#d1ecf1"))
            if r.get("EMA Exit Signal") == "Yes":
                badges.append(_badge(f"📉 EMA TRAIL EXIT — {sym}: 2 consecutive weekly closes below 21-EMA.",
                                     "#721c24", "#f8d7da"))
    if not badges:
        badges = [_empty_state("No active alerts.", "Alerts appear here as breakouts, near-breakouts, and position events occur.")]
    return badges


def _staleness_banner():
    loaded = data_manager.LOADED_BREAKOUT_FILE_DATE
    if not loaded:
        return None
    try:
        age_days = (datetime.now().date() - datetime.strptime(loaded, "%Y%m%d").date()).days
    except Exception:
        return None
    if age_days > 1:
        return html.Div(
            f"⚠️ Data staleness: breakout signals are {age_days} days old "
            f"(file {loaded}). Run generate_breakout_signals.py to refresh.",
            className="status-message", style={"backgroundColor": "#fff3cd", "color": "#856404",
                                               "border": "1px solid #ffe69c", "margin": "8px 0"},
        )
    return None


# ---------------------------------------------------------------------------
# Detail / backtest rendering
# ---------------------------------------------------------------------------
def _backtest_card(symbol):
    from . import data_feed
    monthly = data_feed.get_monthly(symbol)
    weekly = data_feed.get_weekly(symbol)
    if monthly is None or monthly.empty:
        return _empty_state(f"No price history available for {symbol}.")
    res = bt.backtest_symbol(symbol, monthly, weekly if weekly is not None else pd.DataFrame())
    if not res.found:
        return _empty_state(f"{symbol}: no valid historical multi-year breakout found.",
                            f"reason: {res.reason}")
    color = {"WIN": "#155724", "LOSS": "#721c24", "OPEN": "#0c5460"}.get(res.outcome, "#333")
    rows = [
        ("Breakout date", res.breakout_date), ("Resistance", f"₹{res.resistance}"),
        ("Support", f"₹{res.support}"), ("Resistance age", f"{res.resistance_age_years} yrs"),
        ("Entry", f"₹{res.entry}"), ("Stop loss", f"₹{res.stop_loss}"),
        ("Target 1", f"₹{res.target_1}"), ("Peak after entry", f"₹{res.peak_price}"),
        ("Representative exit", f"₹{res.exit_price}"), ("Holding", f"{res.holding_months} months"),
    ]
    return html.Div([
        html.H4(f"{symbol} — Backtest: ",
                style={"display": "inline"}),
        html.Span(f"{res.outcome}  ({res.return_pct:+.1f}% blended)",
                  style={"color": color, "fontWeight": 700}),
        html.Table([html.Tr([html.Td(k, style={"fontWeight": 600, "padding": "4px 14px 4px 0"}),
                             html.Td(v)]) for k, v in rows],
                   style={"marginTop": "10px"}),
        html.P("Blended return = 50% booked at Target 1 + 50% trailed out on the weekly 21-EMA "
               "(2 consecutive closes below).", style={"fontSize": "12px", "color": "#6c757d"}),
    ], className="status-message", style={"backgroundColor": "#f8fafc", "border": "1px solid #e2e8f0"})


def register_breakout_callbacks(app):
    """Register all Multi-Year Breakout callbacks on the Dash ``app``."""

    @app.callback(
        [Output("bo-signals-container", "children"),
         Output("bo-watchlist-container", "children"),
         Output("bo-positions-container", "children"),
         Output("bo-alerts-container", "children"),
         Output("bo-signals-meta", "children"),
         Output("bo-staleness-banner", "children")],
        [Input("refresh-breakout-button", "n_clicks"),
         Input("bo-auto-refresh-interval", "n_intervals")],
        prevent_initial_call=False,
    )
    def render_breakout(_n_clicks, _n_intervals):
        signals = data_manager.breakout_signals_df.copy()
        watchlist = data_manager.breakout_watchlist_df.copy()
        rejections = data_manager.breakout_rejections_df.copy()
        loaded_date = data_manager.LOADED_BREAKOUT_FILE_DATE

        universe_size = (int(rejections["Universe_Size"].iloc[0])
                         if (not rejections.empty and "Universe_Size" in rejections.columns)
                         else None)
        funnel = _funnel_card(rejections, universe_size, loaded_date)

        # ---- Signals (Module 1) ----
        if signals.empty:
            uni_txt = f"{universe_size:,}" if universe_size else "the screened"
            no_sig = _empty_state(
                f"No fresh breakouts today — {uni_txt} NSE stocks scanned, 0 cleared all 9 filters.",
                "This is the strategy being deliberately selective (5+ year base + Smart Money). "
                "See the funnel below for the rejection breakdown; open the Backtest tab to "
                "validate the engine on a documented winner (e.g. SANGHVIMOV).")
            signals_view = html.Div([no_sig, funnel]) if funnel else no_sig
        else:
            cond = [{"if": {"filter_query": '{Candle_Quality} = "VALID"'},
                     "backgroundColor": "#d4edda", "color": "#155724"}]
            signals_view = _table(signals, _SIGNAL_DISPLAY, "bo-signals-table",
                                  selectable=True, conditional=cond)

        # ---- Watchlist (Module 2) ----
        if watchlist.empty:
            watch_view = _empty_state(
                "Watchlist empty — no NSE stocks are currently within 3% of a valid "
                "multi-year resistance.",
                "Watchlist candidates need a >= 5-year, >= 2-touch horizontal base near ATH. "
                "When stocks approach such a level they'll appear here ranked by Priority Score.")
        else:
            watch_view = _table(watchlist, _WATCH_DISPLAY, "bo-watchlist-table")

        # ---- Positions (Module 3) ----
        tracked = pd.DataFrame()
        try:
            tracked = pos.track_positions(data_manager.breakout_positions_df)
        except Exception as exc:
            tracked = pd.DataFrame()
        if tracked is None or tracked.empty:
            positions_view = _empty_state(
                "No open positions.",
                "Record trades you take in breakout_positions.csv to track them here.")
        else:
            pcond = [
                {"if": {"filter_query": '{SL Status} = "Red"'}, "backgroundColor": "#f8d7da", "color": "#721c24"},
                {"if": {"filter_query": '{SL Status} = "Yellow"'}, "backgroundColor": "#fff3cd", "color": "#856404"},
                {"if": {"filter_query": '{SL Status} = "Green"'}, "backgroundColor": "#d4edda", "color": "#155724"},
            ]
            positions_view = _table(tracked, list(tracked.columns), "bo-positions-table", conditional=pcond)

        alerts = _build_alerts(signals, watchlist, tracked)
        meta = (f"{len(signals)} signals · {len(watchlist)} watchlist · "
                f"loaded {data_manager.LOADED_BREAKOUT_FILE_DATE or 'n/a'}")
        return signals_view, watch_view, positions_view, alerts, meta, _staleness_banner()

    @app.callback(
        [Output("bo-signal-detail-panel", "children"),
         Output("bo-signal-detail-panel", "style")],
        [Input("bo-signals-table", "selected_rows"),
         Input("bo-signals-table", "derived_virtual_data")],
        prevent_initial_call=True,
    )
    def show_signal_detail(selected_rows, table_data):
        if not selected_rows or not table_data:
            return None, {"display": "none"}
        row = table_data[selected_rows[0]]
        symbol = str(row.get("Symbol", "")).upper()
        if not symbol:
            return None, {"display": "none"}
        return _backtest_card(symbol), {"display": "block", "marginTop": "16px"}

    @app.callback(
        Output("bo-backtest-result", "children"),
        Input("bo-backtest-run-button", "n_clicks"),
        State("bo-backtest-symbol-input", "value"),
        prevent_initial_call=True,
    )
    def run_backtest(_n, symbol):
        if not symbol:
            return _empty_state("Enter a symbol and click Run Backtest.")
        return _backtest_card(str(symbol).upper().strip())

    @app.callback(
        [Output("bo-delivery-chart", "figure"),
         Output("bo-delivery-table", "children")],
        Input("bo-delivery-run-button", "n_clicks"),
        State("bo-delivery-symbol-input", "value"),
        prevent_initial_call=True,
    )
    def run_delivery(_n, symbol):
        empty_fig = go.Figure().update_layout(
            template="plotly_white", height=320,
            annotations=[dict(text="Enter a symbol to view delivery-volume trend",
                              showarrow=False, font=dict(size=14, color="#6c757d"))])
        if not symbol:
            return empty_fig, None
        symbol = str(symbol).upper().strip()

        daily = dd.load_all_daily()
        if daily.empty:
            return empty_fig, _empty_state(
                "No delivery data stored yet.",
                "Run download_delivery_data.py --backfill-days 120 to populate data/delivery/.")
        sym_daily = daily[daily["Symbol"].astype(str).str.upper() == symbol].sort_values("Date")
        if sym_daily.empty:
            return empty_fig, _empty_state(f"No delivery records for {symbol}.")

        last3m = sym_daily[sym_daily["Date"] >= (sym_daily["Date"].max() - pd.Timedelta(days=92))]
        colors = ["#16a34a" if p > C.DELIVERY_STRONG_PCT else
                  "#dc2626" if p < C.DELIVERY_WEAK_REJECT_PCT else "#64748b"
                  for p in last3m["DeliveryPct"].fillna(0)]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=last3m["Date"], y=last3m["DeliveryPct"], mode="lines+markers",
                                 line=dict(color="#2563eb"), marker=dict(color=colors, size=6),
                                 name="Delivery %"))
        fig.add_hline(y=C.DELIVERY_MIN_PCT, line_dash="dash", line_color="#94a3b8",
                      annotation_text="50% min")
        fig.update_layout(template="plotly_white", height=340, margin=dict(l=40, r=20, t=30, b=30),
                          yaxis_title="Delivery %", title=f"{symbol} — Delivery Volume %")

        monthly = dd.aggregate_monthly(sym_daily).tail(6)
        table_df = last3m.tail(60).copy()
        table_df["Date"] = table_df["Date"].dt.strftime("%Y-%m-%d")
        table_df = table_df.rename(columns={"TotalVolume": "Total Volume", "DeliveryQty": "Delivery Qty",
                                            "DeliveryPct": "Delivery %"})[["Date", "Total Volume", "Delivery Qty", "Delivery %"]]
        monthly_note = html.P(
            "Monthly avg (last 6): " + ", ".join(
                f"{m.Month}: {m.DeliveryPct}%" for m in monthly.itertuples()),
            style={"fontSize": "13px", "color": "#334155", "marginTop": "8px"})
        table = _table(table_df.iloc[::-1], list(table_df.columns), "bo-delivery-daily-table")
        return fig, html.Div([monthly_note, table])
