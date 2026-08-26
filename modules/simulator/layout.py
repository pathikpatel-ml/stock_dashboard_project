"""
Dash layout for the Simulator tab -- two side-by-side panels (V20 | Turtle), each showing that
strategy's virtual portfolio. Component IDs are prefixed ``sim-{strategy}-`` (e.g.
``sim-v20-balance-input``, ``sim-turtle-holdings-container``) to stay clear of every other
tab's namespace and to keep the two panels' callbacks independent of each other.

This tab is read-only except for config (starting balance / max position % / active toggle /
reset) -- the actual BUY/SELL decisions are made by generate_simulator_decisions.py running
offline under GitHub Actions, never inline here. See modules/simulator/__init__.py for the
full architecture note.
"""
import dash_bootstrap_components as dbc
from dash import dcc, html

STRATEGIES = [("v20", "V20 Strategy"), ("turtle", "Turtle Strategy")]


def _strategy_panel(strategy: str, label: str) -> html.Div:
    p = f"sim-{strategy}"
    return html.Div(className="section-container", style={"flex": "1", "minWidth": "420px"}, children=[
        html.H4(label),

        html.Div(id=f"{p}-config-status", className="mb-2"),

        html.Div(className="control-bar", children=[
            html.Div(className="filter-group", children=[
                html.Label("Starting Balance (₹):", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Input(id=f"{p}-balance-input", type="number", min=1000, step=1000,
                          value=100000, style={"width": "120px"}),
            ]),
            html.Div(className="filter-group", children=[
                html.Label("Max Position %:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Input(id=f"{p}-maxpct-input", type="number", min=1, max=100, step=1,
                          value=12, style={"width": "70px"}),
            ]),
            html.Div(className="filter-group", children=[
                html.Label("Active:", style={"fontWeight": "500", "fontSize": "13px"}),
                dbc.Switch(id=f"{p}-active-toggle", value=False, className="mb-0"),
            ]),
            dbc.Button("Save", id=f"{p}-save-btn", color="primary", size="sm", n_clicks=0),
            dcc.ConfirmDialogProvider(
                dbc.Button("Reset", color="danger", outline=True, size="sm"),
                id=f"{p}-reset-confirm",
                message=(
                    "This permanently deletes this simulator's holdings, trade history, and "
                    "decision log, and restores cash to the starting balance. This cannot be "
                    "undone -- continue?"
                ),
            ),
        ]),

        html.P(
            "Runs once daily via an offline agent -- nothing here uses real money or places "
            "real broker orders. Changes to Starting Balance only take effect on the next "
            "Reset.",
            className="module-help",
        ),

        dcc.Interval(id=f"{p}-refresh-interval", interval=300000, n_intervals=0),  # 5 min

        dcc.Loading(type="circle", children=[html.Div(id=f"{p}-summary-container")]),
        html.H6("Holdings", style={"marginTop": "16px"}),
        dcc.Loading(type="circle", children=[
            html.Div(id=f"{p}-holdings-container", className="dash-table-container")
        ]),
        html.H6("Trade History", style={"marginTop": "16px"}),
        dcc.Loading(type="circle", children=[
            html.Div(id=f"{p}-trades-container", className="dash-table-container")
        ]),
        html.Details(style={"marginTop": "16px"}, children=[
            html.Summary("Decision Log (every candidate reviewed, including skips)"),
            dcc.Loading(type="circle", children=[
                html.Div(id=f"{p}-decisions-container", className="dash-table-container")
            ]),
        ]),
    ])


def create_simulator_layout() -> html.Div:
    return html.Div(className="section-container", children=[
        html.H3("🤖 Trading Simulator"),
        html.P(
            "An LLM agent (LangGraph, via OpenRouter) paper-trades using this app's real V20 "
            "and Turtle signals against a virtual balance you set, reasoning about each "
            "candidate (with optional web search) before deciding to buy, sell, or skip. Two "
            "independent portfolios so you can compare which strategy performs better.",
            className="module-help",
        ),
        html.Div(
            style={"display": "flex", "gap": "16px", "flexWrap": "wrap"},
            children=[_strategy_panel(strategy, label) for strategy, label in STRATEGIES],
        ),
    ])
