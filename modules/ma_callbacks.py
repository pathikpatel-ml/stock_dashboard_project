# modules/ma_callbacks.py
from dash import html, dash_table
from dash.dependencies import Input, Output, State
import data_manager
import pandas as pd

def register_ma_callbacks(app):
    @app.callback(
        Output('ma-signals-table-container', 'children'),
        Input('refresh-ma-data-button', 'n_clicks'),
        State('ma-view-selector-dropdown', 'value'),
        prevent_initial_call=False
    )
    def update_ma_signals_table(_n_clicks, selected_view):
        if data_manager.ma_signals_df.empty:
            return html.Div("MA Signals data unavailable.", className="status-message error")
        
        primary_df, secondary_df = data_manager.process_ma_signals_for_ui(data_manager.ma_signals_df)
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
