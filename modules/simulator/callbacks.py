"""
Dash callbacks for the Simulator tab. Per strategy panel (v20 / turtle), three independent
callbacks:
  - sync_and_save_{strategy}_config -- populates the config inputs on load and persists them
    when Save is clicked (owns the input fields' `value` props so typing never gets clobbered
    by anything except a deliberate Save/initial-load).
  - reset_{strategy}_simulator -- wipes holdings/trades/decisions on confirmed Reset (shares
    the status-message Output with the save callback via allow_duplicate=True -- see the
    2026-08-24 dash-version-pin fix elsewhere in this repo for exactly why that flag matters).
  - render_{strategy}_display -- read-only summary/holdings/trades/decisions tables, refreshed
    on page load, the 5-min interval, and immediately after Save/Reset.

This tab never writes a trade -- BUY/SELL decisions are made offline by
generate_simulator_decisions.py (GitHub Actions). See modules/simulator/__init__.py.
"""
from datetime import datetime, timezone

import dash
import flask_login
from dash import Input, Output, State, dash_table, html

import data_manager
from modules.simulator import store

_HOLDINGS_COLUMNS = ["Symbol", "Quantity", "Entry Price", "Entry Date", "Current Price",
                      "Unrealized P&L", "Unrealized P&L (%)"]
_TRADES_COLUMNS = ["Date", "Action", "Symbol", "Price", "Quantity", "Realized P&L", "Rationale"]
_DECISIONS_COLUMNS = ["Date", "Symbol", "Decision", "Rationale"]


def _current_user_id():
    if flask_login.current_user.is_authenticated:
        return flask_login.current_user.id
    return None


def _live_price(strategy: str, symbol: str) -> float:
    """Best-effort current price lookup from whatever data_manager already has loaded for that
    strategy's own tab -- never fetches anything new (this tab doesn't own that data). Falls
    back to None (caller shows entry price / 0% instead of crashing) if the symbol isn't found,
    e.g. it dropped out of today's active signal list."""
    try:
        if strategy == "v20":
            df = data_manager.v20_processed_df
            if df is not None and not df.empty and "Symbol" in df.columns:
                row = df[df["Symbol"].astype(str).str.upper() == symbol.upper()]
                if not row.empty:
                    return float(row.iloc[0]["Latest Close Price"])
        else:
            df = data_manager.turtle_signals_df
            if df is not None and not df.empty and "Symbol" in df.columns:
                row = df[df["Symbol"].astype(str).str.upper() == symbol.upper()]
                if not row.empty:
                    return float(row.iloc[0]["Current_Price"])
    except Exception:
        pass
    return None


def _empty_state(message: str) -> html.Div:
    return html.Div(message, className="status-message info")


def _summary_cards(cash: float, holdings_value: float, starting_balance: float) -> html.Div:
    total_value = cash + holdings_value
    total_pnl = total_value - starting_balance
    pct_return = (total_pnl / starting_balance * 100) if starting_balance else 0.0
    pnl_color = "#155724" if total_pnl >= 0 else "#721c24"
    cards = [
        ("Cash", f"₹{cash:,.2f}"),
        ("Holdings Value", f"₹{holdings_value:,.2f}"),
        ("Total Value", f"₹{total_value:,.2f}"),
        ("Total P&L", f"₹{total_pnl:,.2f} ({pct_return:+.2f}%)"),
    ]
    return html.Div(style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "margin": "8px 0"}, children=[
        html.Div(style={
            "flex": "1", "minWidth": "120px", "padding": "10px", "borderRadius": "6px",
            "background": "#f1f5f9", "textAlign": "center",
        }, children=[
            html.Div(label, style={"fontSize": "12px", "color": "#64748b"}),
            html.Div(value, style={
                "fontSize": "16px", "fontWeight": "600",
                "color": pnl_color if label == "Total P&L" else "#0f172a",
            }),
        ])
        for label, value in cards
    ])


def _holdings_table(strategy: str, holdings: list) -> html.Div:
    if not holdings:
        return _empty_state("No open positions.")
    rows = []
    for h in holdings:
        current = _live_price(strategy, h["symbol"])
        entry = float(h["entry_price"])
        qty = float(h["quantity"])
        if current is not None:
            pnl = (current - entry) * qty
            pnl_pct = (current - entry) / entry * 100 if entry else 0.0
        else:
            current, pnl, pnl_pct = entry, 0.0, 0.0
        rows.append({
            "Symbol": h["symbol"], "Quantity": qty, "Entry Price": round(entry, 2),
            "Entry Date": h["entry_date"], "Current Price": round(current, 2),
            "Unrealized P&L": round(pnl, 2), "Unrealized P&L (%)": round(pnl_pct, 2),
        })
    return html.Div(dash_table.DataTable(
        data=rows, columns=[{"name": c, "id": c} for c in _HOLDINGS_COLUMNS],
        style_table={"overflowX": "auto"}, style_cell={"textAlign": "center", "fontSize": "13px", "padding": "6px"},
        style_header={"backgroundColor": "#f1f5f9", "fontWeight": "600"},
        style_data_conditional=[
            {"if": {"filter_query": "{Unrealized P&L} >= 0", "column_id": "Unrealized P&L"}, "color": "#155724"},
            {"if": {"filter_query": "{Unrealized P&L} < 0", "column_id": "Unrealized P&L"}, "color": "#721c24"},
        ],
    ))


def _trades_table(trades: list) -> html.Div:
    if not trades:
        return _empty_state("No trades yet.")
    rows = [{
        "Date": t["trade_date"], "Action": t["action"], "Symbol": t["symbol"],
        "Price": round(float(t["price"]), 2), "Quantity": t["quantity"],
        "Realized P&L": round(float(t["realized_pnl"]), 2) if t.get("realized_pnl") is not None else "",
        "Rationale": (t.get("rationale") or "")[:200],
    } for t in trades]
    return html.Div(dash_table.DataTable(
        data=rows, columns=[{"name": c, "id": c} for c in _TRADES_COLUMNS],
        style_table={"overflowX": "auto"}, style_cell={"textAlign": "center", "fontSize": "13px", "padding": "6px"},
        style_header={"backgroundColor": "#f1f5f9", "fontWeight": "600"},
        style_cell_conditional=[{"if": {"column_id": "Rationale"}, "textAlign": "left", "maxWidth": "320px"}],
    ))


def _decisions_table(decisions: list) -> html.Div:
    if not decisions:
        return _empty_state("No decisions logged yet.")
    rows = [{
        "Date": d["run_date"], "Symbol": d["symbol"], "Decision": d["decision"],
        "Rationale": (d.get("rationale") or "")[:300],
    } for d in decisions]
    return html.Div(dash_table.DataTable(
        data=rows, columns=[{"name": c, "id": c} for c in _DECISIONS_COLUMNS],
        style_table={"overflowX": "auto"}, style_cell={"textAlign": "center", "fontSize": "13px", "padding": "6px"},
        style_header={"backgroundColor": "#f1f5f9", "fontWeight": "600"}, page_size=10,
        style_cell_conditional=[{"if": {"column_id": "Rationale"}, "textAlign": "left", "maxWidth": "400px"}],
    ))


def register_simulator_callbacks(app):
    """Register the 3 callbacks (config sync/save, reset, display) for both strategy panels."""
    for strategy in ("v20", "turtle"):
        p = f"sim-{strategy}"
        _register_panel_callbacks(app, strategy, p)


def _register_panel_callbacks(app, strategy: str, p: str):

    @app.callback(
        Output(f"{p}-balance-input", "value"),
        Output(f"{p}-maxpct-input", "value"),
        Output(f"{p}-active-toggle", "value"),
        Output(f"{p}-config-status", "children"),
        Input(f"{p}-save-btn", "n_clicks"),
        State(f"{p}-balance-input", "value"),
        State(f"{p}-maxpct-input", "value"),
        State(f"{p}-active-toggle", "value"),
        prevent_initial_call=False,
    )
    def sync_and_save_config(n_clicks, balance_val, maxpct_val, active_val,
                              _strategy=strategy):
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        status = ""
        if n_clicks:
            balance = float(balance_val) if balance_val else 100000.0
            maxpct = float(maxpct_val) if maxpct_val else 12.0
            store.save_config(user_id, _strategy, balance, maxpct, bool(active_val))
            status = html.Div("Saved.", className="status-message success")

        config = store.get_config(user_id, _strategy)
        if config is None:
            return 100000, 12, False, status
        return (
            float(config["starting_balance"]), float(config["max_position_pct"]),
            bool(config["is_active"]), status,
        )

    @app.callback(
        Output(f"{p}-config-status", "children", allow_duplicate=True),
        Input(f"{p}-reset-confirm", "submit_n_clicks"),
        prevent_initial_call=True,
    )
    def reset_simulator(submit_n_clicks, _strategy=strategy):
        user_id = _current_user_id()
        if not user_id or not submit_n_clicks:
            raise dash.exceptions.PreventUpdate
        store.reset_simulator(user_id, _strategy)
        return html.Div("Reset complete -- holdings, trades, and decisions cleared.",
                         className="status-message success")

    @app.callback(
        Output(f"{p}-summary-container", "children"),
        Output(f"{p}-holdings-container", "children"),
        Output(f"{p}-trades-container", "children"),
        Output(f"{p}-decisions-container", "children"),
        Input(f"{p}-refresh-interval", "n_intervals"),
        Input(f"{p}-save-btn", "n_clicks"),
        Input(f"{p}-reset-confirm", "submit_n_clicks"),
        prevent_initial_call=False,
    )
    def render_display(_n_intervals, _save_clicks, _reset_clicks, _strategy=strategy):
        user_id = _current_user_id()
        if not user_id:
            raise dash.exceptions.PreventUpdate

        config = store.get_config(user_id, _strategy)
        if config is None:
            msg = _empty_state("Not configured yet -- set a starting balance above and click Save.")
            return msg, msg, msg, msg

        # Re-sync the underlying strategy's own signal/live-price data so _live_price() reads
        # fresh values -- same "re-sync on every render" reasoning already used by the V20/
        # Turtle tabs themselves.
        try:
            if _strategy == "v20":
                data_manager.load_v20_data_on_startup()
            else:
                data_manager.load_turtle_data_on_startup()
        except Exception:
            pass  # best-effort freshness; stale cached data is still shown below rather than nothing

        portfolio = store.get_portfolio(user_id, _strategy)
        cash = float(portfolio["cash_balance"]) if portfolio else float(config["starting_balance"])
        holdings = store.get_holdings(user_id, _strategy)
        holdings_value = 0.0
        for h in holdings:
            current = _live_price(_strategy, h["symbol"])
            price = current if current is not None else float(h["entry_price"])
            holdings_value += price * float(h["quantity"])

        summary = _summary_cards(cash, holdings_value, float(config["starting_balance"]))
        holdings_ui = _holdings_table(_strategy, holdings)
        trades_ui = _trades_table(store.get_trade_history(user_id, _strategy))
        decisions_ui = _decisions_table(store.get_decision_log(user_id, _strategy))
        return summary, holdings_ui, trades_ui, decisions_ui
