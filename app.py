# app.py
import dash
from dash import html, dcc, Output, Input  # Make sure to import Output and Input
from datetime import datetime

# Import project modules
import data_manager
from modules import v20_layout
from modules import v20_callbacks

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

# 2. LOAD AND PROCESS DATA ON STARTUP - THIS IS THE KEY
# This populates the data_manager.v20_signals_df and ma_signals_df
# It also does the initial slow processing for the V20 cache.
data_manager.load_and_process_data_on_startup()

# 3. Define the App Layout
app.layout = html.Div(className="app-container", children=[
    html.H1("Stock Signal Dashboard - V20 Strategy"),
    
    # This Div is the target for our status callback.
    html.Div(id="app-subtitle"), 
    
    # V20 layout only
    v20_layout.create_v20_layout(),
    
    html.Footer("Stock Signal Dashboard © " + str(datetime.now().year))
])

# 4. Register callbacks
v20_callbacks.register_v20_callbacks(app)

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


# 5. Run the App
if __name__ == '__main__':
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
