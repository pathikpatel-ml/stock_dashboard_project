# modules/ma_callbacks.py
from dash import html, dash_table
from dash.dependencies import Input, Output, State
import data_manager
import pandas as pd

def register_ma_callbacks(app):
    
    @app.callback(
        Output('ma-signals-table-container', 'children'),
        # Triggered by the "Refresh MA Data" button
        Input('refresh-ma-data-button', 'n_clicks'),
        # Also needs the state of the dropdown to know which table to show
        State('ma-view-selector-dropdown', 'value'),
        # Run on page load to show the default view
        prevent_initial_call=False 
    )
    def update_ma_signals_table(_n_clicks, selected_view):
        # 1. Get the raw MA data that was loaded on startup. This is FAST.
        raw_ma_df = data_manager.ma_signals_df

        if raw_ma_df.empty:
            return html.Div("MA Signals data not loaded on startup.", className="status-message error")

        # 2. Process the data. This is the slow part (fetches live prices for active signals).
        # This runs on page load and whenever the 'Refresh' button is clicked.
        primary_df, secondary_df = data_manager.process_ma_signals_for_ui(raw_ma_df)
        df_to_display = primary_df if selected_view == 'primary' else secondary_df
        msg = f"No active {selected_view.capitalize()} Buy signals found."

        if df_to_display.empty: return html.Div(msg, className="status-message info")
        
        return dash_table.DataTable(
            data=df_to_display.to_dict('records'),
            columns=[{'name': i, 'id': i} for i in df_to_display.columns],
            page_size=20, sort_action="native", filter_action="native",
            style_table={'overflowX': 'auto', 'minWidth': '100%'},
            style_data_conditional=[
                {'if': {'filter_query': '{Difference (%)} < 0'}, 'color': '#dc3545', 'fontWeight': 'bold'},
                {'if': {'filter_query': '{Difference (%)} >= 0'}, 'color': '#28a745', 'fontWeight': 'bold'}
            ]
        )
