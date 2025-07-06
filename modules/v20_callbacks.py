# modules/v20_callbacks.py
import dash # <<< THIS IS THE MISSING IMPORT
from dash import html, dash_table
from dash.dependencies import Input, Output, State
import data_manager

def register_v20_callbacks(app):
    @app.callback(
        Output('v20-signals-table-container', 'children'),
        [Input('apply-v20-filter-button', 'n_clicks'),
         Input('refresh-v20-live-data-button', 'n_clicks')],
        State('v20-proximity-filter-input', 'value'),
        prevent_initial_call=False # Run on startup to show initial cached data
    )
    def update_v20_table(_apply_clicks, _refresh_clicks, proximity_value):
        
        # Check which button was clicked to trigger the callback
        ctx = dash.callback_context
        # If the refresh button was clicked, re-run the slow processing and update the cache
        if ctx.triggered and 'refresh-v20-live-data-button' in ctx.triggered[0]['prop_id']:
            print("V20 REFRESH: Re-processing with new live prices...")
            data_manager.v20_processed_df = data_manager.process_v20_signals(data_manager.v20_signals_df)
        
        # Always use the (potentially updated) cached data for display. This is FAST.
        processed_df = data_manager.v20_processed_df
        
        if processed_df.empty:
            return html.Div("No active V20 signals found.", className="status-message info")
        
        # Apply the proximity filter (fast, in-memory operation)
        try:
            proximity_threshold = float(proximity_value if proximity_value is not None else 100)
        except:
            proximity_threshold = 100.0
            
        filtered_df = processed_df[processed_df['Closeness (%)'] <= proximity_threshold]
        
        if filtered_df.empty:
            return html.Div(f"No active V20 signals within {proximity_threshold}% of buy price.", className="status-message info")
            
        return dash_table.DataTable(
            data=filtered_df.to_dict('records'),
            columns=[{'name': i, 'id': i} for i in filtered_df.columns if i not in ['Closeness (%)', 'Sell_Price_High']],
            page_size=15, sort_action="native", filter_action="native",
            style_table={'overflowX': 'auto', 'minWidth': '100%'}
        )
