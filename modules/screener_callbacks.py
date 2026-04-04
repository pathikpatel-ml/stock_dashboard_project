"""
Stock Screener callbacks.
"""
import data_manager
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf
from dash import Input, Output, State, callback, ctx


def _table_columns():
    return [
        {"name": "Symbol", "id": "Symbol", "type": "text"},
        {"name": "Company Name", "id": "Company_Name", "type": "text"},
        {"name": "Net Profit (Cr)", "id": "Net_Profit_Cr", "type": "numeric"},
        {"name": "Latest Quarter Profit", "id": "Latest_Quarter_Profit", "type": "numeric"},
        {"name": "ROCE (%)", "id": "ROCE", "type": "numeric"},
        {"name": "ROE (%)", "id": "ROE", "type": "numeric"},
        {"name": "Debt/Equity", "id": "Debt_to_Equity", "type": "numeric"},
        {"name": "Public Holding (%)", "id": "Public_Holding_Percent", "type": "numeric"},
        {"name": "Current Price", "id": "Current_Price", "type": "numeric"},
        {"name": "MA10", "id": "MA10", "type": "numeric"},
        {"name": "MA50", "id": "MA50", "type": "numeric"},
        {"name": "MA100", "id": "MA100", "type": "numeric"},
        {"name": "MA200", "id": "MA200", "type": "numeric"},
        {"name": "NSE Categories", "id": "NSE_Categories", "type": "text"},
    ]


@callback(
    [Output("filtered-stocks-table", "data"), Output("filtered-stocks-table", "columns"), Output("filter-summary", "children")],
    [Input("apply-filters-btn", "n_clicks"), Input("clear-filters-btn", "n_clicks")],
    [
        State("nse-category-dropdown", "value"),
        State("net-profit-slider", "value"),
        State("quarterly-profit-slider", "value"),
        State("roce-slider", "value"),
        State("roe-slider", "value"),
        State("debt-equity-slider", "value"),
        State("public-holding-slider", "value"),
        State("ma10-filter", "value"),
        State("ma50-filter", "value"),
        State("ma100-filter", "value"),
        State("ma200-filter", "value"),
    ],
)
def update_filtered_stocks(
    apply_clicks,
    clear_clicks,
    nse_categories,
    net_profit_range,
    quarterly_profit_range,
    roce_range,
    roe_range,
    debt_equity_range,
    public_holding_range,
    ma10_filter,
    ma50_filter,
    ma100_filter,
    ma200_filter,
):
    df = data_manager.comprehensive_stocks_df.copy()
    columns = _table_columns()

    if df.empty:
        return [], columns, "No data available"

    triggered = ctx.triggered[0]["prop_id"] if ctx.triggered else ""
    if triggered == "clear-filters-btn.n_clicks":
        return df.to_dict("records"), columns, f"Showing all {len(df)} stocks (no filters applied)"

    if triggered == "apply-filters-btn.n_clicks":
        if nse_categories:
            df = df[
                df["NSE_Categories"].apply(
                    lambda value: any(category in str(value) for category in nse_categories) if pd.notna(value) else False
                )
            ]

        if net_profit_range:
            df = df[(df["Net_Profit_Cr"] >= net_profit_range[0]) & (df["Net_Profit_Cr"] <= net_profit_range[1])]
        if quarterly_profit_range:
            df = df[
                (df["Latest_Quarter_Profit"] >= quarterly_profit_range[0])
                & (df["Latest_Quarter_Profit"] <= quarterly_profit_range[1])
            ]
        if roce_range:
            df = df[(df["ROCE"] >= roce_range[0]) & (df["ROCE"] <= roce_range[1])]
        if roe_range:
            df = df[(df["ROE"] >= roe_range[0]) & (df["ROE"] <= roe_range[1])]
        if debt_equity_range:
            df = df[
                (df["Debt_to_Equity"] >= debt_equity_range[0])
                & (df["Debt_to_Equity"] <= debt_equity_range[1])
            ]
        if public_holding_range:
            df = df[
                (df["Public_Holding_Percent"] >= public_holding_range[0])
                & (df["Public_Holding_Percent"] <= public_holding_range[1])
            ]

        for current_filter, column_name in [
            (ma10_filter, "MA10"),
            (ma50_filter, "MA50"),
            (ma100_filter, "MA100"),
            (ma200_filter, "MA200"),
        ]:
            if current_filter == "above":
                df = df[df["Current_Price"] > df[column_name]]
            elif current_filter == "below":
                df = df[df["Current_Price"] < df[column_name]]

        avg_roce = df["ROCE"].mean() if not df.empty else 0
        avg_roe = df["ROE"].mean() if not df.empty else 0
        summary = f"Found {len(df)} stocks | Avg ROCE: {avg_roce:.2f}% | Avg ROE: {avg_roe:.2f}%"
        return df.to_dict("records"), columns, summary

    return df.to_dict("records"), columns, f"Showing all {len(df)} stocks (click Apply Filters to filter)"


@callback(
    [
        Output("selected-stock-detail", "children"),
        Output("v20-signals-table", "data"),
        Output("v20-signals-table", "columns"),
        Output("ma-chart", "figure"),
    ],
    [Input("filtered-stocks-table", "active_cell")],
    [State("filtered-stocks-table", "data")],
)
def update_stock_detail(active_cell, table_data):
    if not active_cell or not table_data:
        return "Select a stock from the table to view details", [], [], {}

    row_index = active_cell["row"]
    selected_stock = table_data[row_index]
    symbol = selected_stock["Symbol"]

    v20_data = []
    v20_columns = []
    if not data_manager.v20_signals_df.empty:
        stock_v20 = data_manager.v20_signals_df[
            data_manager.v20_signals_df["Symbol"].astype(str).str.upper() == symbol.upper()
        ]
        if not stock_v20.empty:
            v20_data = stock_v20.to_dict("records")
            v20_columns = [
                {"name": "Buy Date", "id": "Buy_Date", "type": "datetime"},
                {"name": "Buy Price Low", "id": "Buy_Price_Low", "type": "numeric"},
                {"name": "Sell Date", "id": "Sell_Date", "type": "datetime"},
                {"name": "Sell Price High", "id": "Sell_Price_High", "type": "numeric"},
                {"name": "Gain %", "id": "Sequence_Gain_Percent", "type": "numeric"},
            ]

    detail_text = (
        f"**Selected Stock: {symbol}**\n\n"
        f"**Company:** {selected_stock.get('Company_Name', 'N/A')}\n\n"
        f"**Net Profit:** {selected_stock.get('Net_Profit_Cr', 0):.2f} Cr\n\n"
        f"**Latest Quarter Profit:** {selected_stock.get('Latest_Quarter_Profit', 0):.2f} Cr\n\n"
        f"**ROCE:** {selected_stock.get('ROCE', 0):.2f}%\n\n"
        f"**ROE:** {selected_stock.get('ROE', 0):.2f}%\n\n"
        f"**Debt/Equity:** {selected_stock.get('Debt_to_Equity', 0):.2f}\n\n"
        f"**Public Holding:** {selected_stock.get('Public_Holding_Percent', 0):.2f}%\n\n"
        f"**NSE Categories:** {selected_stock.get('NSE_Categories', 'N/A')}"
    )

    return detail_text, v20_data, v20_columns, create_ma_chart(symbol)


def create_ma_chart(symbol):
    try:
        history = yf.Ticker(f"{symbol}.NS").history(period="1y")
        if history.empty:
            return go.Figure()

        history["MA10"] = history["Close"].rolling(window=10).mean()
        history["MA50"] = history["Close"].rolling(window=50).mean()
        history["MA100"] = history["Close"].rolling(window=100).mean()
        history["MA200"] = history["Close"].rolling(window=200).mean()

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=history.index, y=history["Close"], mode="lines", name="Close Price"))
        fig.add_trace(go.Scatter(x=history.index, y=history["MA10"], mode="lines", name="MA10"))
        fig.add_trace(go.Scatter(x=history.index, y=history["MA50"], mode="lines", name="MA50"))
        fig.add_trace(go.Scatter(x=history.index, y=history["MA100"], mode="lines", name="MA100"))
        fig.add_trace(go.Scatter(x=history.index, y=history["MA200"], mode="lines", name="MA200"))
        fig.update_layout(title=f"{symbol} - Price & Moving Averages", xaxis_title="Date", yaxis_title="Price")
        return fig
    except Exception as e:
        print(f"Error creating MA chart for {symbol}: {e}")
        return go.Figure()


@callback(Output("nse-category-dropdown", "options"), Input("screener-page", "id"))
def update_category_options(_):
    if data_manager.comprehensive_stocks_df.empty:
        return []

    all_categories = set()
    for categories_str in data_manager.comprehensive_stocks_df["NSE_Categories"].dropna():
        if isinstance(categories_str, str):
            all_categories.update(category.strip() for category in categories_str.split(",") if category.strip())

    return [{"label": category, "value": category} for category in sorted(all_categories)]


def register_screener_callbacks(app):
    return app
