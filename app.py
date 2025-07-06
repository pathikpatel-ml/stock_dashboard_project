# app.py
import dash
from dash import html, dcc, Output, Input  # Make sure to import Output and Input
from datetime import datetime

# Import project modules
import data_manager
from modules import v20_layout, ma_layout
from modules import v20_callbacks, ma_callbacks
# The individual stock module was removed as per your request

# 1. Initialize the Dash App
app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='assets')
server = app.server
app.title = "Stock Signal Dashboard"

# 2. LOAD AND PROCESS DATA ON STARTUP - THIS IS THE KEY
# This populates the data_manager.v20_signals_df and ma_signals_df
# It also does the initial slow processing for the V20 cache.
data_manager.load_and_process_data_on_startup()

# 3. Define the App Layout
app.layout = html.Div(className="app-container", children=[
    html.H1("Stock Signal Dashboard"),
    
    # This Div is the target for our status callback.
    # It will be empty at first and then populated.
    html.Div(id="app-subtitle"), 
    
    # Assemble layouts from modules
    v20_layout.create_v20_layout(),
    ma_layout.create_ma_layout(),
    
    html.Footer("Stock Signal Dashboard © " + str(datetime.now().year))
])

# 4. Register all callbacks from the modules
v20_callbacks.register_v20_callbacks(app)
ma_callbacks.register_ma_callbacks(app)

# --- START: CORRECTED STATUS DISPLAY CALLBACK ---
# This callback will run after the main tables are rendered, ensuring it
# has the latest status information.
@app.callback(
    Output('app-subtitle', 'children'),
    # It listens for changes in the content of the table containers.
    # When a table is created and placed in the container, this callback fires.
    [Input('v20-signals-table-container', 'children'),
     Input('ma-signals-table-container', 'children')]
)
def update_status_display(_, __):
    # The arguments (_, __) are placeholders; we don't need the table content itself,
    # we just need to know that it was updated.

    # This helper function creates the styled text.
    def get_status_span(prefix_text, df):
        date_str = datetime.now().strftime("%Y%m%d")
        status_text = f"{prefix_text}NotFound"
        status_class = "status-error"
        
        # Check if the dataframe in data_manager is populated
        if not df.empty:
            status_text = f"{prefix_text}{date_str}"
            status_class = "status-loaded"
        
        return html.Span(status_text, className=status_class)

    # Check the dataframes that were loaded at startup.
    v20_span = get_status_span("V20DataLoaded", data_manager.v20_signals_df)
    ma_span = get_status_span("MADataLoaded", data_manager.ma_signals_df)

    return [
        v20_span,
        html.Span(" | ", style={'color': '#6c757d'}),
        ma_span
    ]
# --- END: CORRECTED STATUS DISPLAY CALLBACK ---


# 5. Run the App
if __name__ == '__main__':
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
