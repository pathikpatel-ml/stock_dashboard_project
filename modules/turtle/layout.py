"""
Dash layout for the Turtle Strategy tab (docs/TURTLE_STRATEGY_PLAN.md).

A single ``create_turtle_layout()`` returns the strategy section: Indices/Sector/Stock-Name
filters + ATH-only/Yesterday toggles, and the results table. Component IDs are prefixed
``tt-`` to stay clear of the V20 (``v20-``) and Breakout (``bo-``) namespaces. Dropdown
options are populated once, at layout-build time, from whatever ``data_manager`` loaded at
app startup (same refresh model as the rest of the app — new data appears on the next
restart/redeploy, matching how the daily-cron CSVs are already surfaced elsewhere).
"""
from dash import dcc, html

import data_manager

# Fallback only -- used if nse_categories_df hasn't loaded yet (e.g. very first cold start).
# The real option list is built dynamically from whatever index tags actually exist in
# nse_categories.csv (NIFTY 50/100/200 plus sectoral indices like NIFTY BANK, NIFTY IT,
# NIFTY PHARMA, etc.) -- compute.filter_by_index already matches any of these generically,
# this dropdown was just hardcoded to show a subset of what's actually filterable.
INDEX_OPTIONS = ["All", "NIFTY 50", "NIFTY 100", "NIFTY 200"]


def _dropdown_options(series, extra_first="All"):
    values = sorted(v for v in series.dropna().astype(str).unique() if v.strip())
    options = ([extra_first] if extra_first else []) + values
    return [{"label": v, "value": v} for v in options]


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


def create_turtle_layout():
    df = data_manager.turtle_signals_df
    sector_options = _dropdown_options(df["Sector"]) if not df.empty and "Sector" in df.columns else [{"label": "All", "value": "All"}]
    stock_options = _dropdown_options(df["Symbol"]) if not df.empty and "Symbol" in df.columns else [{"label": "All", "value": "All"}]
    index_options = _index_options()

    return html.Div(className="section-container", children=[
        html.H3("🐢 Turtle Strategy — ADD / HOLD / EXIT"),
        html.P(
            "Turtle Wealth's Quant Process: ATH price + ATH profit (consolidated TTM vs. "
            "historical max, screener.in) + 52-week outperformance vs sector and BSE 500 "
            "(Nifty 500 proxy), with a 212-day moving average as the exit-price proxy.",
            className="module-help",
        ),
        html.Div(id="tt-staleness-banner"),

        dcc.Interval(id="tt-auto-refresh-interval", interval=300000, n_intervals=0),  # 5 min

        html.Div(className="control-bar", children=[
            html.Div(className="filter-group", children=[
                html.Label("Indices:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="tt-indices-filter",
                    options=index_options,
                    value="All",
                    clearable=False,
                    style={"width": "200px"},
                ),
            ]),
            html.Div(className="filter-group", children=[
                html.Label("Sector:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="tt-sector-filter",
                    options=sector_options,
                    value="All",
                    clearable=False,
                    style={"width": "200px"},
                ),
            ]),
            html.Div(className="filter-group", children=[
                html.Label("Stock:", style={"fontWeight": "500", "fontSize": "13px"}),
                dcc.Dropdown(
                    id="tt-stock-filter",
                    options=stock_options,
                    value="All",
                    clearable=False,
                    style={"width": "160px"},
                ),
            ]),
            html.Div(className="filter-group", children=[
                dcc.Checklist(
                    id="tt-ath-only-toggle",
                    options=[{"label": " ATH only", "value": "ath_only"}],
                    value=[],
                    style={"fontSize": "13px"},
                ),
            ]),
            html.Div(className="filter-group", children=[
                dcc.Checklist(
                    id="tt-yesterday-toggle",
                    options=[{"label": " Yesterday", "value": "yesterday"}],
                    value=[],
                    style={"fontSize": "13px"},
                ),
            ]),
        ]),

        dcc.Loading(type="circle", children=[
            html.Div(id="tt-sector-pulse-container")
        ]),

        dcc.Loading(type="circle", children=[
            html.Div(id="tt-signals-container", className="dash-table-container")
        ]),
    ])
