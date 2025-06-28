# app.py
import dash
from dash import html
import data_manager
from modules import v20_layout, ma_layout, individual_stock_layout
from modules import v20_callbacks, ma_callbacks, individual_stock_callbacks

# 1. Initialize the Dash App
app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='assets')
server = app.server
app.title = "Stock Analysis Dashboard"

# 2. Load and process data ONCE on startup
data_manager.load_data_for_dashboard_from_repo()

# 3. Define the App Layout by assembling modules
app.layout = html.Div(className="app-container", children=[
    html.H1("Stock Analysis Dashboard"),
    html.Div(id="app-subtitle", children=[
        # A small callback could update this status, or it could be static
        html.Span(f"V20 Signals: {len(data_manager.v20_processed_df)} active"),
        html.Span("  |  MA Signals: Loaded"),
    ]),
    
    v20_layout.create_v20_layout(),
    ma_layout.create_ma_layout(),
    individual_stock_layout.create_individual_stock_layout(),
    
    html.Footer("Stock Analysis Dashboard © 2024")
])

# 4. Register all callbacks from the modules
v20_callbacks.register_v20_callbacks(app)
ma_callbacks.register_ma_callbacks(app)
individual_stock_callbacks.register_individual_stock_callbacks(app)

# 5. Run the App
if __name__ == '__main__':
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
