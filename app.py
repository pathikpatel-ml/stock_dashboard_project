# app.py
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, dcc, html

import data_manager
from modules import (
    screener_callbacks,
    screener_layout,
    strategy_callbacks,
    strategy_layout,
    v20_callbacks,
    v20_layout,
)

app = dash.Dash(
    __name__,
    suppress_callback_exceptions=True,
    assets_folder="assets",
    external_stylesheets=[dbc.themes.BOOTSTRAP],
)
server = app.server
app.title = "Stock Signal Dashboard"

app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="stylesheet" href="/assets/enhanced_styles.css?v=3.0">
        <link rel="stylesheet" href="/assets/dashboard.css?v=3.0">
        <link rel="stylesheet" href="/assets/screener_styles.css?v=1.0">
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
"""

app.layout = html.Div(
    className="app-container",
    children=[
        html.H1("Stock Signal Dashboard", className="main-title"),
        dcc.Tabs(
            id="main-tabs",
            value="v20-tab",
            children=[
                dcc.Tab(label="V20 Strategy", value="v20-tab", className="custom-tab"),
                dcc.Tab(label="Stock Screener", value="screener-tab", className="custom-tab"),
                dcc.Tab(label="Quant Strategies", value="strategy-tab", className="custom-tab"),
            ],
            className="custom-tabs",
        ),
        html.Div(id="tab-content"),
        html.Div(id="app-subtitle"),
        html.Footer(f"Stock Signal Dashboard © {datetime.now().year}", className="footer"),
    ],
)

v20_callbacks.register_v20_callbacks(app)
screener_callbacks.register_screener_callbacks(app)
strategy_callbacks.register_strategy_callbacks(app)


@app.callback(Output("tab-content", "children"), [Input("main-tabs", "value")])
def render_tab_content(active_tab):
    if active_tab == "v20-tab":
        return v20_layout.create_v20_layout()
    if active_tab == "screener-tab":
        return screener_layout.create_screener_layout()
    if active_tab == "strategy-tab":
        return strategy_layout.create_strategy_layout()
    return html.Div("Select a tab")


@app.callback(Output("app-subtitle", "children"), [Input("v20-signals-table-container", "children")])
def update_status_display(_):
    loaded_date = data_manager.LOADED_V20_FILE_DATE or datetime.now().strftime("%Y%m%d")
    if data_manager.v20_signals_df.empty:
        return html.Span("V20DataLoadedNotFound", className="status-error")
    return html.Span(f"V20DataLoaded{loaded_date}", className="status-loaded")


data_manager.load_and_process_data_on_startup()


if __name__ == "__main__":
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host="0.0.0.0", port=8050)
