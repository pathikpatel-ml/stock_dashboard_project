# app.py
import dash
from dash import html
from datetime import datetime

# Import project modules
import data_manager
from modules import v20_layout, ma_layout, individual_stock_layout
from modules import v20_callbacks, ma_callbacks, individual_stock_callbacks

# 1. Initialize the Dash App
app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='assets')
server = app.server
app.title = "Stock Analysis Dashboard"

# 2. Load and process data ONCE on startup
data_manager.load_data_for_dashboard_from_repo()

# --- NEW HELPER FUNCTION TO RESTORE UI DISPLAY ---
def create_status_display():
    """
    This function recreates the original UI for displaying file status.
    It reads the filenames from the data_manager configuration.
    """
    today_str = datetime.now().strftime("%Y%m%d")
    
    # Check V20 signals file status
    v20_filename = data_manager.SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str)
    v20_status_text = f"{v20_filename} (Loaded)" if not data_manager.signals_df.empty else f"{v20_filename} (Not Found/Error)"
    
    # Check MA signals file status
    ma_filename = data_manager.MA_SIGNALS_FILENAME_TEMPLATE.format(date_str=today_str)
    ma_status_text = f"{ma_filename} (Loaded)" if not data_manager.ma_signals_df.empty else f"{ma_filename} (Not Found/Error)"

    # Helper to generate styled span
    def get_status_span(full_display_name):
        status_text = "Unavailable"
        status_class = "status-unavailable"
        if "(Not Found/Error)" in full_display_name:
             status_text = "Not Found / Error"
             status_class = "status-error"
        elif "(Loaded)" in full_display_name:
            try: 
                # Extract filename and date for display
                filename_part = full_display_name.split(' ')[0]
                date_part = filename_part.split('_')[-1].split('.')[0]
                datetime.strptime(date_part, "%Y%m%d")
                status_text = f"Loaded ({filename_part})"
                status_class = "status-loaded"
            except: # Fallback if parsing fails
                status_text = "Loaded (Unknown File)"
                status_class = "status-loaded"
        return html.Span(status_text, className=status_class)

    return html.Div(id="app-subtitle", children=[
        html.Span("V20 Signals: "), get_status_span(v20_status_text),
        html.Span("  |  MA Signals: "), get_status_span(ma_status_text)
    ])


# 3. Define the App Layout by assembling modules
app.layout = html.Div(className="app-container", children=[
    html.H1("Stock Analysis Dashboard"),
    
    # Use the new helper function to create the dynamic status display
    create_status_display(),
    
    # Assemble layouts from modules
    v20_layout.create_v20_layout(),
    ma_layout.create_ma_layout(),
    individual_stock_layout.create_individual_stock_layout(),
    
    html.Footer("Stock Analysis Dashboard © " + str(datetime.now().year))
])

# 4. Register all callbacks from the modules
v20_callbacks.register_v20_callbacks(app)
ma_callbacks.register_ma_callbacks(app)
individual_stock_callbacks.register_individual_stock_callbacks(app)

# 5. Run the App
if __name__ == '__main__':
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
