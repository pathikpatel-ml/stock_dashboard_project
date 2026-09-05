"""
Dash layout for the Turtle Quant tab.

A single ``create_turtlequant_layout()`` returns the strategy section: Indices/Sector/Stock-Name
filters and the results table. Component IDs are prefixed ``tq-`` to stay clear of the existing
Turtle Strategy (``tt-``), V20 (``v20-``), and Simulator (``sim-``) namespaces. No watchlist or
Sector Pulse panel here (v1 scope) -- just the filtered signals table, matching what was asked
for. Dropdown options are populated once, at layout-build time, from whatever ``data_manager``
loaded at app startup, same refresh model as every other tab.
"""
from dash import dcc, html

import data_manager

INDEX_OPTIONS = ["All", "NIFTY 50", "NIFTY 100", "NIFTY 200"]


def _dropdown_options(series, extra_first="All"):
    values = sorted(v for v in series.dropna().astype(str).unique() if v.strip())
    options = ([extra_first] if extra_first else []) + values
    return [{"label": v, "value": v} for v in options]


def _stock_dropdown_options(df, extra_first="All"):
    """Label = "Company Name (SYMBOL)", value = Symbol -- matches the Turtle Strategy tab's
    convention (modules/turtle/layout.py::_stock_dropdown_options)."""
    if df.empty or "Symbol" not in df.columns or "Company" not in df.columns:
        return [{"label": extra_first, "value": extra_first}] if extra_first else []

    sub = df[["Symbol", "Company"]].dropna(subset=["Symbol"]).copy()
    sub["Symbol"] = sub["Symbol"].astype(str)
    sub["Company"] = sub["Company"].fillna(sub["Symbol"]).astype(str)
    sub = sub.drop_duplicates(subset=["Symbol"]).sort_values("Company")

    options = [{"label": extra_first, "value": extra_first}] if extra_first else []
    options += [{"label": f"{row.Company} ({row.Symbol})", "value": row.Symbol} for row in sub.itertuples()]
    return options


def _index_options():
    df = data_manager.nse_categories_df
    if df.empty or "NSE_Categories" not in df.columns:
        return [{"label": v, "value": v} for v in INDEX_OPTIONS]
    tags = set()
    for value in df["NSE_Categories"].dropna():
        for tag in str(value).split(","):
            tag = tag.strip()
            if tag:
                tags.add(tag)
    return [{"label": v, "value": v} for v in ["All"] + sorted(tags)]


def create_turtlequant_layout():
    df = data_manager.turtlequant_signals_df
    sector_options = _dropdown_options(df["Sector"]) if not df.empty and "Sector" in df.columns else [{"label": "All", "value": "All"}]
    stock_options = _stock_dropdown_options(df)
    index_options = _index_options()

    return html.Div(className="section-container", children=[
        html.H3("⚡ Turtle Quant — BUY / HOLD / SELL"),
        html.P(
            "Weekly relative strength (52-week & 13-week) vs NSE:NIFTY, confirmed by SuperTrend, "
            "ADX/DMI trend strength, RSI, and price/volume moving-average build-up. BUY needs "
            "every condition to align; SELL fires on any single weakening signal.",
            className="module-help",
        ),
        html.Div(id="tq-staleness-banner"),

        dcc.Interval(id="tq-auto-refresh-interval", interval=300000, n_intervals=0),  # 5 min

        html.Div(className="control-bar", children=[
            html.Div(className="filter-group", children=[
                html.Label("Indices:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="tq-indices-filter",
                    options=index_options,
                    value="All",
                    clearable=False,
                    style={"width": "200px"},
                ),
            ]),
            html.Div(className="filter-group", children=[
                html.Label("Sector:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="tq-sector-filter",
                    options=sector_options,
                    value="All",
                    clearable=False,
                    style={"width": "200px"},
                ),
            ]),
            html.Div(className="filter-group", children=[
                html.Label("Stock:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="tq-stock-filter",
                    options=stock_options,
                    value="All",
                    clearable=False,
                    style={"width": "160px"},
                ),
            ]),
            html.Div(className="filter-group", children=[
                html.Label("This week:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="tq-signal-filter",
                    options=[
                        {"label": "All", "value": "All"},
                        {"label": "BUY only", "value": "BUY"},
                        {"label": "SELL only", "value": "SELL"},
                        {"label": "HOLD only", "value": "HOLD"},
                    ],
                    value="All",
                    clearable=False,
                    style={"width": "160px"},
                ),
            ]),
        ]),

        dcc.Loading(type="circle", children=[
            html.Div(id="tq-signals-container", className="dash-table-container")
        ]),
    ])
