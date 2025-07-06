# modules/v20_callbacks.py
from dash import html, dash_table
from dash.dependencies import Input, Output, State
import data_manager

def register_v20_callbacks(app):
    @app.callback(
        Output('v20-signals-table-container', 'children'),
        [Input('apply-v20-filter-button', 'n_clicks'),
         Input('refresh-v20-live-data-button', 'n_clicks')],
        State('v20-proximity-filter-input', 'value'),
    )
    def refresh_v20_live_data(n_clicks):
        print("V20 CALLBACK: Refresh button clicked. Checking for stale data...")
        # *** THIS IS THE KEY CHANGE ***
        # Ensure the data file for today is loaded before processing
        data_manager.load_data_if_stale()
        print("V20 CALLBACK: Refreshing live data...")
        data_manager.v20_processed_df = data_manager.process_v20_signals(data_manager.signals_df)
        count = len(data_manager.v20_processed_df)
        print(f"V20 CALLBACK: Refresh complete. Processed {count} signals.")
        return html.Div(f"Live prices refreshed. {count} signals processed.", className="status-message info")

    @app.callback(
        Output('v20-signals-table-container', 'children'),
        [Input('apply-v20-filter-button', 'n_clicks'),
         Input('refresh-v20-live-data-button', 'n_clicks')],
        State('v20-proximity-filter-input', 'value'),
    )
    def update_v20_table(_apply_clicks, _refresh_clicks, proximity_value):
        # *** THIS IS THE KEY CHANGE ***
        # Ensure the data file for today is loaded before processing
        # --- START: MODIFIED LOADING LOGIC ---
        print("V20 CALLBACK: Loading latest data from GitHub...")
        
        # Call the new helper function from data_manager
        signals_df = data_manager.load_data_from_github(data_manager.SIGNALS_FILENAME_TEMPLATE)
        
        if signals_df.empty:
            return html.Div("V20 signals file could not be loaded from GitHub for today.", className="status-message error")
        # --- END: MODIFIED LOADING LOGIC ---
        
        # --- The rest of the function remains exactly the same ---
        processed_df = data_manager.process_v20_signals(signals_df)
        
        if processed_df.empty:
            return html.Div("No active V20 signals found after processing.", className="status-message info")
        
        try: proximity_threshold = float(proximity_value if proximity_value is not None else 20)
        except: proximity_threshold = 20.0
        
        filtered_df = processed_df[processed_df['Closeness (%)'] <= proximity_threshold].copy()
        if filtered_df.empty:
            return html.Div(f"No V20 signals within {proximity_threshold}% of buy price.", className="status-message info")
        
        display_columns = [col for col in filtered_df.columns if col != 'Closeness (%)']
        return dash_table.DataTable(
            data=filtered_df.to_dict('records'),
            columns=[{'name': i, 'id': i} for i in display_columns],
            page_size=15, sort_action="native", filter_action="native",
            style_table={'overflowX': 'auto', 'minWidth': '100%'}
        )
