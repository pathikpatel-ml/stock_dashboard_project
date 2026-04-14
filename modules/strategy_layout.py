import dash_bootstrap_components as dbc
from dash import dash_table, dcc, html


def _table(table_id, page_size):
    return dash_table.DataTable(
        id=table_id,
        data=[],
        columns=[],
        page_size=page_size,
        sort_action="native",
        filter_action="native",
        style_table={"overflowX": "auto"},
        style_cell={"textAlign": "left", "fontSize": "12px"},
        style_header={"backgroundColor": "#f1f3f5", "fontWeight": "bold"},
    )


def create_strategy_layout():
    return dbc.Container(
        id="strategy-page",
        fluid=True,
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H2("Quant Strategies", className="text-primary mb-2"),
                            html.P(
                                "Run yearly fundamental ranking, quality checks, and value-reversion signals from the historical panel.",
                                className="text-muted mb-0",
                            ),
                        ]
                    )
                ],
                className="mb-4",
            ),
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(html.H5("Controls", className="mb-0")),
                                dbc.CardBody(
                                    [
                                        html.Label("Current Year", className="fw-bold"),
                                        dcc.Dropdown(id="strategy-year-dropdown", clearable=False, className="mb-3"),
                                        html.Label("Sector", className="fw-bold"),
                                        dcc.Dropdown(
                                            id="strategy-sector-dropdown",
                                            clearable=False,
                                            className="mb-3",
                                        ),
                                        dbc.Alert(
                                            id="strategy-data-status",
                                            color="info",
                                            className="mb-0",
                                        ),
                                    ]
                                ),
                            ]
                        ),
                        width=3,
                    ),
                    dbc.Col(
                        [
                            dbc.Card(
                                [
                                    dbc.CardHeader(html.H5("Strategy Summary", className="mb-0")),
                                    dbc.CardBody(html.Div(id="strategy-summary")),
                                ],
                                className="mb-4",
                            ),
                            dbc.Card(
                                [
                                    dbc.CardHeader(html.H5("Module 1: Sector Growth & Value Ranker", className="mb-0")),
                                    dbc.CardBody(_table("strategy-sector-ranker-table", 12)),
                                ],
                                className="mb-4",
                            ),
                            dbc.Card(
                                [
                                    dbc.CardHeader(html.H5("Module 2: Quality Fusion Filter", className="mb-0")),
                                    dbc.CardBody(_table("strategy-quality-table", 12)),
                                ],
                                className="mb-4",
                            ),
                            dbc.Card(
                                [
                                    dbc.CardHeader(html.H5("Module 3: Value Reversion Signals", className="mb-0")),
                                    dbc.CardBody(_table("strategy-value-table", 15)),
                                ]
                            ),
                        ],
                        width=9,
                    ),
                ]
            ),
        ],
    )
