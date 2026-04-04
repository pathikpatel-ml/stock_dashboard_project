import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table


def create_screener_layout():
    return dbc.Container(
        id="screener-page",
        fluid=True,
        children=[
            dbc.Row(
                [
                    dbc.Col(
                        [
                            html.H2("Stock Screener", className="text-primary mb-2"),
                            html.P(
                                "Filter stocks and inspect V20 signals with a live detail panel.",
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
                                dbc.CardHeader(html.H5("Filters", className="mb-0")),
                                dbc.CardBody(
                                    [
                                        html.Label("NSE Categories", className="fw-bold"),
                                        dcc.Dropdown(id="nse-category-dropdown", multi=True, className="mb-3"),
                                        html.Label("Net Profit (Cr)", className="fw-bold"),
                                        dcc.RangeSlider(
                                            id="net-profit-slider",
                                            min=-1000,
                                            max=10000,
                                            step=100,
                                            value=[-1000, 10000],
                                            marks={0: "0", 5000: "5000", 10000: "10000"},
                                        ),
                                        html.Label("Latest Quarter Profit (Cr)", className="fw-bold mt-4"),
                                        dcc.RangeSlider(
                                            id="quarterly-profit-slider",
                                            min=-500,
                                            max=5000,
                                            step=50,
                                            value=[-500, 5000],
                                            marks={0: "0", 2500: "2500", 5000: "5000"},
                                        ),
                                        html.Label("ROCE (%)", className="fw-bold mt-4"),
                                        dcc.RangeSlider(
                                            id="roce-slider",
                                            min=-50,
                                            max=100,
                                            step=5,
                                            value=[-50, 100],
                                            marks={0: "0", 50: "50", 100: "100"},
                                        ),
                                        html.Label("ROE (%)", className="fw-bold mt-4"),
                                        dcc.RangeSlider(
                                            id="roe-slider",
                                            min=-50,
                                            max=100,
                                            step=5,
                                            value=[-50, 100],
                                            marks={0: "0", 50: "50", 100: "100"},
                                        ),
                                        html.Label("Debt / Equity", className="fw-bold mt-4"),
                                        dcc.RangeSlider(
                                            id="debt-equity-slider",
                                            min=0,
                                            max=5,
                                            step=0.1,
                                            value=[0, 5],
                                            marks={0: "0", 2: "2", 5: "5"},
                                        ),
                                        html.Label("Public Holding (%)", className="fw-bold mt-4"),
                                        dcc.RangeSlider(
                                            id="public-holding-slider",
                                            min=0,
                                            max=100,
                                            step=5,
                                            value=[0, 100],
                                            marks={0: "0", 50: "50", 100: "100"},
                                        ),
                                        html.Hr(),
                                        html.Label("MA10", className="fw-bold"),
                                        dcc.Dropdown(
                                            id="ma10-filter",
                                            options=[
                                                {"label": "All", "value": "all"},
                                                {"label": "Above MA10", "value": "above"},
                                                {"label": "Below MA10", "value": "below"},
                                            ],
                                            value="all",
                                            className="mb-2",
                                        ),
                                        html.Label("MA50", className="fw-bold"),
                                        dcc.Dropdown(
                                            id="ma50-filter",
                                            options=[
                                                {"label": "All", "value": "all"},
                                                {"label": "Above MA50", "value": "above"},
                                                {"label": "Below MA50", "value": "below"},
                                            ],
                                            value="all",
                                            className="mb-2",
                                        ),
                                        html.Label("MA100", className="fw-bold"),
                                        dcc.Dropdown(
                                            id="ma100-filter",
                                            options=[
                                                {"label": "All", "value": "all"},
                                                {"label": "Above MA100", "value": "above"},
                                                {"label": "Below MA100", "value": "below"},
                                            ],
                                            value="all",
                                            className="mb-2",
                                        ),
                                        html.Label("MA200", className="fw-bold"),
                                        dcc.Dropdown(
                                            id="ma200-filter",
                                            options=[
                                                {"label": "All", "value": "all"},
                                                {"label": "Above MA200", "value": "above"},
                                                {"label": "Below MA200", "value": "below"},
                                            ],
                                            value="all",
                                            className="mb-3",
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    dbc.Button(
                                                        "Apply Filters",
                                                        id="apply-filters-btn",
                                                        color="primary",
                                                        className="w-100",
                                                    )
                                                ),
                                                dbc.Col(
                                                    dbc.Button(
                                                        "Clear All",
                                                        id="clear-filters-btn",
                                                        color="secondary",
                                                        className="w-100",
                                                    )
                                                ),
                                            ]
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
                                    dbc.CardHeader(html.H5("Results", className="mb-0")),
                                    dbc.CardBody(
                                        [
                                            html.Div(
                                                id="filter-summary",
                                                className="text-muted mb-3",
                                                children="Loading stocks...",
                                            ),
                                            dash_table.DataTable(
                                                id="filtered-stocks-table",
                                                data=[],
                                                columns=[],
                                                page_size=15,
                                                sort_action="native",
                                                filter_action="native",
                                                style_table={"overflowX": "auto"},
                                                style_cell={"textAlign": "left", "fontSize": "12px"},
                                                style_header={
                                                    "backgroundColor": "#f1f3f5",
                                                    "fontWeight": "bold",
                                                },
                                            ),
                                        ]
                                    ),
                                ],
                                className="mb-4",
                            ),
                            dbc.Card(
                                [
                                    dbc.CardHeader(html.H5("Selected Stock", className="mb-0")),
                                    dbc.CardBody(
                                        [
                                            dcc.Markdown(
                                                id="selected-stock-detail",
                                                children="Select a stock from the table to view details",
                                            ),
                                            html.Hr(),
                                            html.H6("V20 Signals"),
                                            dash_table.DataTable(
                                                id="v20-signals-table",
                                                data=[],
                                                columns=[],
                                                page_size=8,
                                                style_table={"overflowX": "auto"},
                                                style_cell={"textAlign": "left", "fontSize": "12px"},
                                            ),
                                            html.Hr(),
                                            dcc.Graph(id="ma-chart", figure={}),
                                        ]
                                    ),
                                ]
                            ),
                        ],
                        width=9,
                    ),
                ]
            ),
        ],
    )
