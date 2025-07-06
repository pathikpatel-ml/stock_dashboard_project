# # app.py
# import dash
# from dash import html, dcc, Output, Input # Import specific components
# from datetime import datetime

# # Import project modules
# import data_manager
# from modules import v20_layout, ma_layout
# from modules import v20_callbacks, ma_callbacks

# # 1. Initialize the Dash App
# app = dash.Dash(__name__, suppress_callback_exceptions=True, assets_folder='assets')
# server = app.server
# app.title = "Stock Analysis Dashboard"

# # --- HELPER FUNCTION FOR UI DISPLAY (MODIFIED) ---
# def create_status_display():
#     """
#     This function will now be a layout component with an interval timer
#     to periodically refresh the status display without user interaction.
#     """
#     return html.Div([
#         dcc.Interval(
#             id='interval-component',
#             interval=300 * 1000, # every 5 minutes in milliseconds
#             n_intervals=0
#         ),
#         html.Div(id="app-subtitle") # The actual content will be populated by the callback below
#     ])

# # # 3. Define the App Layout by assembling modules
# # app.layout = html.Div(className="app-container", children=[
# #     html.H1("Stock Analysis Dashboard"),
# #     create_status_display(), # Use the new layout component
    
# #     # Assemble layouts from modules
# #     v20_layout.create_v20_layout(),
# #     ma_layout.create_ma_layout(),
    
# #     html.Footer("Stock Analysis Dashboard © " + str(datetime.now().year))
# # ])

# # In app.py - REPLACE your existing app.layout block

# # --- HELPER FUNCTION TO RESTORE UI DISPLAY ---
# def create_status_display():
#     return html.Div([
#         dcc.Interval(id='interval-component', interval=300 * 1000, n_intervals=0),
#         html.Div(id="app-subtitle")
#     ])

# # 3. Define the App Layout by assembling modules
# app.layout = html.Div(className="app-container", children=[
#     html.H1("Stock Signal Dashboard"),
#     create_status_display(), # Use the new helper function
#     v20_layout.create_v20_layout(),
#     ma_layout.create_ma_layout(),
#     html.Footer("Stock Signal Dashboard © " + str(datetime.now().year))
# ])

# # 4. Register all callbacks from the modules
# v20_callbacks.register_v20_callbacks(app)
# ma_callbacks.register_ma_callbacks(app)

# # # --- NEW CALLBACK TO DYNAMICALLY UPDATE THE STATUS DISPLAY ---
# # @app.callback(
# #     Output('app-subtitle', 'children'),
# #     Input('interval-component', 'n_intervals')
# # )
# # def update_status_display(_):
# #     """Periodically checks the loaded data date and updates the subtitle."""
    
# #     def get_status_span(prefix_text, loaded_date):
# #         today_date = datetime.now().date()
# #         status_text = f"{prefix_text}NotFound"
# #         status_class = "status-error"
# #         if loaded_date:
# #             status_text = f"{prefix_text}{loaded_date.strftime('%Y%m%d')}"
# #             if loaded_date == today_date:
# #                 status_class = "status-loaded"
# #             else:
# #                 # If data is for a previous day
# #                 status_class = "status-unavailable" # Use yellow for stale data
# #                 status_text += " (Stale)"
# #         return html.Span(status_text, className=status_class)

# #     # Note: We now read the loaded date from the data_manager global variables
# #     v20_span = get_status_span("V20DataLoaded", data_manager.LOADED_V20_FILE_DATE)
# #     ma_span = get_status_span("MADataLoaded", data_manager.LOADED_MA_FILE_DATE)

# #     return [
# #         v20_span,
# #         html.Span("  |  ", style={'color': '#6c757d'}),
# #         ma_span
# #     ]

# # In app.py - ADD THIS NEW CALLBACK

# @app.callback(
#     Output('app-subtitle', 'children'),
#     [Input('v20-signals-table-container', 'children'),
#      Input('ma-signals-table-container', 'children')]
# )
# def update_status_display(_, __):
    
#     def get_status_span(prefix_text, loaded_date):
#         today_date = datetime.now().date()
#         status_text = f"{prefix_text}NotFound"
#         status_class = "status-error"
#         if loaded_date:
#             status_text = f"{prefix_text}{loaded_date.strftime('%Y%m%d')}"
#             status_class = "status-loaded" if loaded_date == today_date else "status-unavailable"
#             if loaded_date != today_date:
#                 status_text += " (Stale)"
#         return html.Span(status_text, className=status_class)

#     v20_span = get_status_span("V20DataLoaded", data_manager.V20_CACHE_DATE)
#     ma_span = get_status_span("MADataLoaded", data_manager.MA_CACHE_DATE)

#     return [v20_span, html.Span(" | ", style={'color': '#6c757d'}), ma_span]

# # 5. Run the App
# if __name__ == '__main__':
#     # Initial load before starting the server
#     print("DASH APP: Application ready. Starting server...")
#     app.run_server(debug=True, host='0.0.0.0', port=8050)



# app.py
import dash
from dash import html, dcc, Output, Input
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

data_manager.load_data()

# 2. Define the App Layout
# The layout is static. The dynamic parts are handled by callbacks.
app.layout = html.Div(className="app-container", children=[
    html.H1("Stock Signal Dashboard"),
    
    # This Div will be populated with the data loading status by its own callback
    html.Div(id="app-subtitle"), 
    
    # Assemble layouts from the imported modules
    v20_layout.create_v20_layout(),
    ma_layout.create_ma_layout(),
    
    html.Footer("Stock Signal Dashboard © " + str(datetime.now().year))
])

# 3. Register all callbacks from the modules
v20_callbacks.register_v20_callbacks(app)
ma_callbacks.register_ma_callbacks(app)

# 4. Callback to update the Status Display
# This callback is triggered *after* one of the main tables tries to render,
# ensuring it reflects the most recent data load attempt.
@app.callback(
    Output('app-subtitle', 'children'),
    [Input('v20-signals-table-container', 'children'),
     Input('ma-signals-table-container', 'children')]
)
def update_status_display(_, __):
    
    def get_status_span(prefix_text, loaded_date):
        today_date = datetime.now().date()
        status_text = f"{prefix_text}NotFound"
        status_class = "status-error"
        if loaded_date:
            status_text = f"{prefix_text}{loaded_date.strftime('%Y%m%d')}"
            status_class = "status-loaded" if loaded_date == today_date else "status-unavailable"
            if loaded_date != today_date:
                status_text += " (Stale)"
        return html.Span(status_text, className=status_class)

    v20_span = get_status_span("V20DataLoaded", data_manager.V20_CACHE_DATE)
    ma_span = get_status_span("MADataLoaded", data_manager.MA_CACHE_DATE)

    return [v20_span, html.Span(" | ", style={'color': '#6c757d'}), ma_span]

# 5. Run the App
if __name__ == '__main__':
    # We do NOT load data on startup. Loading is handled on-demand by the callbacks.
    print("DASH APP: Application ready. Starting server...")
    app.run_server(debug=True, host='0.0.0.0', port=8050)
