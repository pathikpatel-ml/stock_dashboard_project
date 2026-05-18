# app.py
from datetime import datetime

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, html

import data_manager
from modules import v20_callbacks, v20_layout

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
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
        <link rel="stylesheet" href="/assets/enhanced_styles.css?v=4.0">
        <link rel="stylesheet" href="/assets/dashboard.css?v=4.0">
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
        v20_layout.create_v20_layout(),
        html.Div(id="app-subtitle"),
        html.Footer(f"Stock Signal Dashboard © {datetime.now().year}", className="footer"),
    ],
)

v20_callbacks.register_v20_callbacks(app)


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
