# app.py
import dash
from dash import html, dcc, Output, Input  # Make sure to import Output and Input
from datetime import datetime

# Import project modules
import data_manager
from modules import v20_layout
from modules import v20_callbacks
from modules import screener_layout
from modules import screener_callbacks

# 1. Initialize the Dash App
app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='assets')
server = app.server
app.title = "Stock Signal Dashboard"

# Force CSS cache refresh by adding external stylesheets
app.index_string = '''
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
'''

# 2. Define the App Layout with Tabs
app.layout = html.Div(className="app-container", children=[
    html.H1("Stock Signal Dashboard", className="main-title"),
    
    # Navigation Tabs
    dcc.Tabs(id="main-tabs", value="v20-tab", children=[
        dcc.Tab(label="V20 Strategy", value="v20-tab", className="custom-tab"),
        dcc.Tab(label="Stock Screener", value="screener-tab", className="custom-tab")
    ], className="custom-tabs"),
    
    # Tab Content
    html.Div(id="tab-content"),
    
    # Status Display
    html.Div(id="app-subtitle"), 
    
    html.Footer("Stock Signal Dashboard © " + str(datetime.now().year), className="footer")
])

# 3. Register callbacks
v20_callbacks.register_v20_callbacks(app)
screener_callbacks.register_screener_callbacks(app)

# Tab switching callback
@app.callback(
    Output('tab-content', 'children'),
    [Input('main-tabs', 'value')]
)
def render_tab_content(active_tab):
    if active_tab == 'v20-tab':
        return v20_layout.create_v20_layout()
    elif active_tab == 'screener-tab':
        return screener_layout.create_screener_layout()
    return html.Div("Select a tab")

# --- START: CORRECTED STATUS DISPLAY CALLBACK ---
# This callback will run after the main tables are rendered, ensuring it
# has the latest status information.
@app.callback(
    Output('app-subtitle', 'children'),
    [Input('v20-signals-table-container', 'children')]
)
def update_status_display(_):
    def get_status_span(prefix_text, df):
        date_str = datetime.now().strftime("%Y%m%d")
        status_text = f"{prefix_text}NotFound"
        status_class = "status-error"
        
        if not df.empty:
            status_text = f"{prefix_text}{date_str}"
            status_class = "status-loaded"
        
        return html.Span(status_text, className=status_class)

    v20_span = get_status_span("V20DataLoaded", data_manager.v20_signals_df)
    return v20_span
# --- END: CORRECTED STATUS DISPLAY CALLBACK ---


# 4. Run the App
if __name__ == '__main__':
    # Load data before starting the server
    data_manager.load_and_process_data_on_startup()
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
