# modules/v20_callbacks.py
import dash
from dash import html, dcc, dash_table
import plotly.graph_objects as go
from dash.dependencies import Input, Output, State
import data_manager
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from src.indicators import AdvancedIndicatorCalculator, identify_signals
from modules.notification_engine import get_notification_engine, AlertType, NotificationPriority
from modules.stock_name_resolver import stock_resolver

def register_v20_callbacks(app):
    # Initialize components
    indicator_calc = AdvancedIndicatorCalculator(cache_enabled=True)
    notification_engine = get_notification_engine()
    
    @app.callback(
        Output('startup-data-poll', 'disabled'),
        Input('startup-data-poll', 'n_intervals'),
    )
    def stop_startup_poll(_):
        return data_manager.is_ready()

    @app.callback(
        [
            Output('v20-signals-table-container', 'children'),
            Output('v20-sentiment-score', 'children'),
            Output('v20-sentiment-label', 'children'),
            Output('v20-indicators-grid', 'children'),
            Output('v20-notifications-container', 'children')
        ],
        [
            Input('apply-v20-filter-button', 'n_clicks'),
            Input('refresh-v20-live-data-button', 'n_clicks'),
            Input('refresh-v20-indicators-button', 'n_clicks'),
            Input('v20-auto-refresh-interval', 'n_intervals'),
            Input('startup-data-poll', 'n_intervals'),
        ],
        State('v20-proximity-filter-input', 'value'),
        prevent_initial_call=False
    )
    def update_v20_comprehensive(_apply_clicks, _refresh_clicks, _indicator_clicks, _intervals, _startup_n, proximity_value):
        # Show loading spinner while background startup is in progress
        if data_manager.is_loading():
            loading_msg = html.Div([
                html.I(className="fas fa-spinner fa-spin me-2"),
                "Fetching live prices for all signals — this takes about 60–90 seconds on first load...",
            ], className="status-message info", style={"padding": "1.5rem", "color": "#64748b"})
            return loading_msg, "Loading...", "", html.Div(), html.Div()

        try:
            ctx = dash.callback_context

            # Check which button was clicked
            if ctx.triggered and 'refresh-v20-live-data-button' in ctx.triggered[0]['prop_id']:
                print("V20 REFRESH: Re-processing with new live prices...")
                data_manager.v20_processed_df = data_manager.process_v20_signals(data_manager.v20_signals_df)
            
            # Get processed data
            processed_df = data_manager.v20_processed_df
            
            if processed_df.empty:
                return (
                    html.Div("No active V20 signals found.", className="status-message info"),
                    "N/A", "", 
                    html.Div("No data available for indicators"),
                    html.Div("No notifications")
                )
            
            # Apply proximity filter
            try:
                proximity_threshold = float(proximity_value if proximity_value is not None else 100)
            except:
                proximity_threshold = 100.0
            
            filtered_df = processed_df[processed_df['Closeness (%)'] <= proximity_threshold]
            
            if filtered_df.empty:
                return (
                    html.Div(f"No active V20 signals within {proximity_threshold}% of buy price.", className="status-message info"),
                    "N/A", "",
                    html.Div("No data available for indicators"),
                    html.Div("No notifications")
                )
            
            # Calculate market sentiment
            sentiment_score, sentiment_label, sentiment_color = calculate_market_sentiment(filtered_df)
            
            # Create enhanced table with indicators FIRST
            enhanced_df = add_technical_indicators_to_df(filtered_df, indicator_calc)
            
            # Calculate technical indicators for top stocks using enhanced_df
            indicators_grid = create_indicators_grid(enhanced_df, indicator_calc)
            
            # Generate notifications using enhanced dataframe with signal strength
            notifications = generate_v20_notifications(enhanced_df, notification_engine)
            
            # Add sell trigger based on proximity to V20 sell target
            enhanced_df = add_sell_trigger_to_df(enhanced_df)
            
            table = dash_table.DataTable(
                id='v20-main-table',
                data=enhanced_df.to_dict('records'),
                row_selectable='single',
                columns=[
                    {'name': col, 'id': col, 'type': 'numeric' if col in ['Current Price', 'Buy Price', 'Target Sell Price', 'Closeness (%)', 'Potential Gain (%)'] else 'text'}
                    for col in enhanced_df.columns if col not in ['Closeness (%)', 'RSI', 'MACD Signal', 'Suggested Sell Price', 'Profit Strategy']
                ],
                page_size=15,
                sort_action="native",
                filter_action="native",
                style_table={
                    'overflowX': 'auto',
                    'minWidth': '100%',
                },
                style_cell={
                    'minWidth': '80px',
                    'maxWidth': '160px',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                    'whiteSpace': 'normal',
                    'padding': '10px 12px',
                    'fontSize': '13px',
                    'fontFamily': 'Inter, Segoe UI, sans-serif',
                    'textAlign': 'center',
                    'border': '1px solid #e9ecef',
                },
                style_header={
                    'backgroundColor': '#2c3e50',
                    'color': 'white',
                    'fontWeight': '600',
                    'textAlign': 'center',
                    'padding': '12px',
                    'fontSize': '12px',
                    'border': '1px solid #34495e',
                    'whiteSpace': 'normal',
                    'height': 'auto',
                },
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': '#f8f9fa'},
                    {'if': {'state': 'active'}, 'backgroundColor': '#e3f2fd', 'border': '1px solid #2196f3'},
                    {'if': {'filter_query': '{Signal Strength} = "STRONG BUY"'}, 'backgroundColor': '#d4edda', 'color': '#155724'},
                    {'if': {'filter_query': '{Signal Strength} = "BUY NOW"'}, 'backgroundColor': '#d1ecf1', 'color': '#0c5460'},
                    {'if': {'filter_query': '{Signal Strength} = "OVERBOUGHT"'}, 'backgroundColor': '#f8d7da', 'color': '#721c24'},
                    {'if': {'filter_query': '{Sell Trigger} = "SELL NOW"'}, 'backgroundColor': '#f8d7da', 'color': '#721c24'},
                    {'if': {'filter_query': '{Sell Trigger} = "SELL SOON"'}, 'backgroundColor': '#ffe8cc', 'color': '#8a4a00'},
                ],
                fixed_rows={'headers': True},
                tooltip_data=[
                    {
                        'Suggested Sell Price': {
                            'value': 'Sell Price = Buy Price + 20% | Target 30% gains but hold longer if STRONG HOLD signal appears',
                            'type': 'markdown'
                        }
                    } for _ in range(len(enhanced_df))
                ],
                tooltip_duration=None
            )
            
            return (
                table,
                sentiment_score,
                html.Span(sentiment_label, style={'color': sentiment_color, 'fontWeight': 'bold'}),
                indicators_grid,
                notifications
            )
        except Exception as e:
            print(f"V20 callback error: {e}")
            return (
                html.Div(f"Error loading V20 data: {str(e)}", style={'color': 'red'}),
                "Error",
                html.Span("Error", style={'color': 'red'}),
                html.Div("Error loading indicators"),
                html.Div("Error loading notifications")
            )

    @app.callback(
        [Output('v20-stock-history-panel', 'children'),
         Output('v20-stock-history-panel', 'style')],
        [Input('v20-main-table', 'selected_rows'),
         Input('v20-main-table', 'derived_virtual_data')],
        prevent_initial_call=True
    )
    def show_stock_history(selected_rows, table_data):
        hidden = {'display': 'none'}
        visible = {
            'display': 'block',
            'marginTop': '24px',
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6',
            'borderRadius': '8px',
            'padding': '20px',
        }
        if not selected_rows or not table_data:
            return html.Div(), hidden

        row = table_data[selected_rows[0]]
        symbol = str(row.get('Symbol', '')).upper().strip()
        signal_strength = row.get('Signal Strength', '')

        if signal_strength not in ('STRONG BUY', 'BUY NOW', 'BUY'):
            return html.Div([
                html.Div(f'Historical panel only available for BUY signals. '
                         f'{symbol} is currently {signal_strength}.',
                         style={'color': '#6c757d', 'fontStyle': 'italic', 'padding': '12px'})
            ]), visible

        all_signals = data_manager.v20_signals_df
        if all_signals.empty or 'Symbol' not in all_signals.columns:
            return html.Div('No historical data loaded.', style={'color': '#6c757d'}), visible

        symbol_signals = all_signals[
            all_signals['Symbol'].astype(str).str.upper() == symbol
        ].copy().reset_index(drop=True)

        # Fetch actual market price history and determine each signal's outcome
        price_history = _fetch_price_history_for_backtesting(symbol)
        outcomes = _analyze_all_signal_outcomes(symbol_signals, price_history)

        panel_content = build_stock_history_panel(symbol, row, outcomes)
        return panel_content, visible

def calculate_market_sentiment(df):
    """Calculate clear, actionable market sentiment"""
    try:
        if 'Closeness (%)' not in df.columns or df.empty:
            return "N/A", "No data available", "#6c757d"
        
        closeness_values = df['Closeness (%)'].dropna()
        if len(closeness_values) == 0:
            return "N/A", "No data available", "#6c757d"
        
        # Count stocks by proximity to buy targets
        very_close = len(closeness_values[closeness_values <= 2])  # Within 2%
        close = len(closeness_values[closeness_values <= 5])  # Within 5%
        total = len(closeness_values)
        
        # Create clear, actionable sentiment for individual stock decisions
        if very_close >= 3:
            return f"{very_close} Ready", f"🟢 BUY NOW - {very_close} stocks at target prices", "#28a745"
        elif close >= 2:
            return f"{close} Ready", f"🔵 BUY SOON - {close} stocks near targets", "#17a2b8"
        elif close >= 1:
            return f"{close} Ready", f"🟡 WATCH - {close} stock approaching target", "#ffc107"
        else:
            avg_distance = closeness_values.mean()
            return "0 Ready", f"🔴 WAIT - No stocks ready (avg {avg_distance:.1f}% away)", "#dc3545"
    
    except Exception as e:
        print(f"Sentiment calculation error: {e}")
        return "Error", "Calculation failed", "#dc3545"

def create_indicators_grid(df, indicator_calc):
    """Create a grid showing technical indicators for top stocks"""
    try:
        # Get top 6 stocks by some criteria
        top_stocks = df.head(6) if len(df) >= 6 else df
        
        indicator_cards = []
        
        for _, stock in top_stocks.iterrows():
            symbol = stock.get('Symbol', 'N/A')
            
            # Use the RSI and MACD values already calculated in the dataframe
            rsi_val = stock.get('RSI', np.nan)
            macd_line = stock.get('MACD Signal', np.nan)
            signal_strength = stock.get('Signal Strength', 'N/A')
            
            # Determine signal color based on signal strength
            if signal_strength == "STRONG BUY":
                signal_color = "#28a745"
            elif signal_strength == "BUY NOW":
                signal_color = "#28a745"
            elif signal_strength == "BUY":
                signal_color = "#17a2b8"
            elif signal_strength == "WAIT (Bearish)":
                signal_color = "#ffc107"
            elif signal_strength == "OVERBOUGHT":
                signal_color = "#dc3545"
            else:
                signal_color = "#6c757d"
            
            card = html.Div([
                html.H6(symbol, style={'margin': '0 0 10px 0', 'color': '#007bff', 'fontWeight': 'bold'}),
                html.Div([
                    html.Span(f"RSI: {rsi_val:.1f}" if not pd.isna(rsi_val) else "RSI: N/A", 
                             style={'display': 'block', 'fontSize': '12px'}),
                    html.Span("📊 RSI: Oversold<30 (Buy), >70 (Sell)", 
                             style={'display': 'block', 'fontSize': '10px', 'color': '#6c757d', 'fontStyle': 'italic'}),
                    html.Span(f"MACD: {macd_line:.3f}" if not pd.isna(macd_line) else "MACD: N/A", 
                             style={'display': 'block', 'fontSize': '12px'}),
                    html.Span("📈 MACD: >0 (Bullish), <0 (Bearish)", 
                             style={'display': 'block', 'fontSize': '10px', 'color': '#6c757d', 'fontStyle': 'italic'}),
                    html.Span("BB: Within Bands", style={'display': 'block', 'fontSize': '12px'}),
                    html.Span(signal_strength, style={
                        'display': 'block', 
                        'fontSize': '11px', 
                        'fontWeight': 'bold',
                        'color': signal_color,
                        'marginTop': '5px'
                    })
                ])
            ], style={
                'border': '1px solid #dee2e6',
                'borderRadius': '5px',
                'padding': '10px',
                'margin': '5px',
                'backgroundColor': '#ffffff',
                'minWidth': '150px',
                'textAlign': 'center'
            })
            
            indicator_cards.append(card)
        
        return html.Div(indicator_cards, style={
            'display': 'flex',
            'flexWrap': 'wrap',
            'justifyContent': 'space-around'
        })
    
    except Exception as e:
        print(f"Error creating indicators grid: {e}")
        return html.Div("Error loading indicators", style={'color': '#dc3545'})

def add_technical_indicators_to_df(df, indicator_calc):
    """Add technical indicator columns to the dataframe"""
    try:
        enhanced_df = df.copy()
        
        rsi_values = []
        macd_signals = []
        signal_strengths = []
        
        for _, row in df.iterrows():
            symbol = str(row.get('Symbol', '')).upper().strip()
            try:
                rsi_val, macd_line = calculate_eod_rsi_macd(symbol, indicator_calc)
                
                # Determine signal strength based on all technical factors
                closeness = row.get('Closeness (%)', 100)
                
                # Technical conditions
                rsi_bullish = not np.isnan(rsi_val) and rsi_val < 70
                macd_bullish = not np.isnan(macd_line) and macd_line > 0
                rsi_oversold = not np.isnan(rsi_val) and rsi_val < 30
                
                if closeness <= 2 and rsi_oversold and macd_bullish:
                    signal_strength = "STRONG BUY"
                elif closeness <= 2 and rsi_bullish and macd_bullish:
                    signal_strength = "BUY NOW"
                elif closeness <= 5 and rsi_bullish and macd_bullish:
                    signal_strength = "BUY"
                elif closeness <= 2 and not macd_bullish:
                    signal_strength = "WAIT (Bearish)"
                elif not np.isnan(rsi_val) and rsi_val > 70:
                    signal_strength = "OVERBOUGHT"
                else:
                    signal_strength = "WATCH"
                
                rsi_values.append(rsi_val if not np.isnan(rsi_val) else None)
                macd_signals.append(macd_line if not np.isnan(macd_line) else None)
                signal_strengths.append(signal_strength)
                
            except Exception as e:
                print(f"Error calculating indicators: {e}")
                rsi_values.append(None)
                macd_signals.append(None)
                signal_strengths.append("N/A")
        
        enhanced_df['RSI'] = rsi_values
        enhanced_df['MACD Signal'] = macd_signals
        enhanced_df['Signal Strength'] = signal_strengths
        
        return enhanced_df
    
    except Exception as e:
        print(f"Error enhancing dataframe: {e}")
        return df


def calculate_eod_rsi_macd(symbol, indicator_calc):
    """Calculate RSI and MACD using only completed daily candles."""
    if not symbol:
        return np.nan, np.nan

    history = yf.Ticker(f"{symbol}.NS").history(period="6mo", interval="1d", auto_adjust=False)
    if history is None or history.empty or 'Close' not in history.columns:
        return np.nan, np.nan

    close_series = pd.to_numeric(history['Close'], errors='coerce').dropna()
    if close_series.empty:
        return np.nan, np.nan

    today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if len(close_series) >= 2 and close_series.index[-1].date() >= today_ist:
        close_series = close_series.iloc[:-1]

    if len(close_series) < 35:
        return np.nan, np.nan

    indicators = indicator_calc.calculate_all(close_series.to_numpy(dtype=float))
    rsi_values = indicators.get('rsi')
    macd_line_values = indicators.get('macd_line')

    rsi_val = rsi_values[-1] if rsi_values is not None and len(rsi_values) else np.nan
    macd_line = macd_line_values[-1] if macd_line_values is not None and len(macd_line_values) else np.nan

    return (
        float(rsi_val) if not pd.isna(rsi_val) else np.nan,
        float(macd_line) if not pd.isna(macd_line) else np.nan,
    )

def add_sell_price_guidance(df):
    """Add sell price suggestions based on market research"""
    try:
        enhanced_df = df.copy()
        
        # Calculate suggested sell price (20% above buy price)
        if 'Buy Price' in enhanced_df.columns:
            enhanced_df['Suggested Sell Price'] = enhanced_df['Buy Price'] * 1.20
            
            # Add profit guidance column
            profit_guidance = []
            for _, row in enhanced_df.iterrows():
                signal_strength = row.get('Signal Strength', 'N/A')
                
                if signal_strength in ['STRONG BUY', 'BUY NOW']:
                    guidance = "🎯 Target 30% gains, but hold longer if momentum continues"
                elif signal_strength == 'BUY':
                    guidance = "📈 Take 20-25% profits, watch for reversal signals"
                elif signal_strength == 'OVERBOUGHT':
                    guidance = "⚠️ Consider selling - stock may be overvalued"
                else:
                    guidance = "📊 Monitor technical indicators for exit timing"
                
                profit_guidance.append(guidance)
            
            enhanced_df['Profit Strategy'] = profit_guidance
        
        return enhanced_df
    
    except Exception as e:
        print(f"Error adding sell price guidance: {e}")
        return df

def add_sell_trigger_to_df(df):
    """Add Sell Trigger column based on proximity to V20 Sell_Price_High target"""
    sell_triggers = []
    for _, row in df.iterrows():
        current = row.get('Latest Close Price')
        sell_target = row.get('Target Sell Price')
        if pd.isna(current) or pd.isna(sell_target) or sell_target == 0:
            sell_triggers.append("N/A")
            continue
        proximity = ((current - sell_target) / sell_target) * 100
        if proximity >= 0:
            sell_triggers.append("SELL NOW")
        elif proximity >= -2:
            sell_triggers.append("SELL SOON")
        elif proximity >= -5:
            sell_triggers.append("APPROACHING")
        else:
            sell_triggers.append("HOLD")
    result = df.copy()
    result['Sell Trigger'] = sell_triggers
    return result

def _fetch_price_history_for_backtesting(symbol):
    """Fetch 5 years of daily OHLC for a symbol. Returns DataFrame or None."""
    try:
        hist = yf.Ticker(f"{symbol}.NS").history(period="5y", interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            return None
        hist.index = pd.to_datetime(hist.index).tz_localize(None).normalize()
        return hist
    except Exception:
        return None


def _analyze_all_signal_outcomes(symbol_signals, price_history):
    """
    For each V20 signal determine what happened AFTER the green candle sequence ended.

    Critical fix: look for entry only AFTER Sell_Date (sequence end), NOT after Buy_Date.
    During the sequence (Buy_Date → Sell_Date) prices are naturally near Buy_Price_Low at
    the start, so using Buy_Date caused the sequence itself to be detected as a "trade".

    Status values:
      COMPLETED  — buy trigger fired + sell trigger fired (full closed trade)
      OPEN       — buy trigger fired, sell target not yet reached
      MISSED     — price never returned to buy zone after sequence ended
      NO_DATA    — price history unavailable or too old
    """
    results = []
    for _, sig in symbol_signals.sort_values('Buy_Date', ascending=False).iterrows():
        buy_target = sig.get('Buy_Price_Low')
        sell_target = sig.get('Sell_Price_High')
        buy_date = pd.to_datetime(sig.get('Buy_Date'))
        sell_date = pd.to_datetime(sig.get('Sell_Date'))

        if pd.isna(buy_target) or pd.isna(sell_target) or pd.isna(buy_date):
            continue

        def _norm(dt):
            return dt.tz_localize(None).normalize() if dt.tzinfo else dt.normalize()

        buy_dt = _norm(buy_date)
        seq_end = _norm(sell_date) if pd.notna(sell_date) else buy_dt
        gain_pct = round((sell_target - buy_target) / buy_target * 100, 2)

        base = {
            'signal_date': buy_dt.strftime('%Y-%m-%d'),
            'seq_end': seq_end.strftime('%Y-%m-%d'),
            'buy_target': round(buy_target, 2),
            'sell_target': round(sell_target, 2),
            'gain_pct': gain_pct,
            'entry_date': None,
            'exit_date': None,
            'holding_days': None,
            'status': 'NO_DATA',
        }

        if price_history is None or price_history.empty:
            results.append(base)
            continue

        # Look for the retracement to buy level strictly AFTER the sequence ends
        post_seq = price_history[price_history.index > seq_end]
        if post_seq.empty:
            base['status'] = 'NO_DATA'
            results.append(base)
            continue

        # Buy trigger: Low touched buy zone (within 2%, matching BUY NOW threshold)
        buy_entries = post_seq[post_seq['Low'] <= buy_target * 1.02]
        if buy_entries.empty:
            base['status'] = 'MISSED'
            results.append(base)
            continue

        entry_date = buy_entries.index[0]
        base['entry_date'] = entry_date.strftime('%Y-%m-%d')

        # Sell trigger: High reached sell zone (within 3%) after entry
        post_entry = price_history[price_history.index >= entry_date]
        sell_exits = post_entry[post_entry['High'] >= sell_target * 0.97]
        if sell_exits.empty:
            base['status'] = 'OPEN'
            results.append(base)
            continue

        exit_date = sell_exits.index[0]
        holding_days = (exit_date - entry_date).days
        if holding_days < 1:
            # Same-day entry+exit — skip (artifact of price data precision)
            base['status'] = 'MISSED'
            results.append(base)
            continue

        base['status'] = 'COMPLETED'
        base['exit_date'] = exit_date.strftime('%Y-%m-%d')
        base['holding_days'] = holding_days
        results.append(base)

    return results


def build_stock_history_panel(symbol, current_row, outcomes):
    """
    Build history panel showing ALL V20 signals for this stock with their outcome status.
    Completed trades drive the summary stats and chart; all signals appear in the status table.
    """
    current_buy = current_row.get('Target Buy Price (Low)', 'N/A')
    current_sell = current_row.get('Target Sell Price', 'N/A')
    current_signal = current_row.get('Signal Strength', '')
    signal_colors = {'STRONG BUY': '#28a745', 'BUY NOW': '#17a2b8', 'BUY': '#007bff'}
    sig_color = signal_colors.get(current_signal, '#6c757d')

    header = html.Div([
        html.Div([
            html.Span(symbol, style={'fontSize': '22px', 'fontWeight': '700', 'color': '#2c3e50'}),
            html.Span(f'  {current_signal}', style={
                'fontSize': '13px', 'fontWeight': '600', 'color': sig_color,
                'backgroundColor': sig_color + '1a', 'padding': '3px 10px',
                'borderRadius': '12px', 'marginLeft': '10px', 'border': f'1px solid {sig_color}'
            }),
        ], style={'display': 'flex', 'alignItems': 'center', 'marginBottom': '4px'}),
        html.Div(
            f'Buy Target: ₹{current_buy}  |  Sell Target: ₹{current_sell}',
            style={'fontSize': '12px', 'color': '#6c757d'}
        ),
    ], style={'marginBottom': '16px'})

    if not outcomes:
        return html.Div([header,
                         html.Div('No historical V20 signals found for this stock.',
                                  style={'color': '#6c757d', 'fontStyle': 'italic'})])

    completed = [o for o in outcomes if o['status'] == 'COMPLETED']
    open_trades = [o for o in outcomes if o['status'] == 'OPEN']
    missed = [o for o in outcomes if o['status'] == 'MISSED']
    no_data = [o for o in outcomes if o['status'] == 'NO_DATA']
    total = len(outcomes)

    # --- Coverage summary bar ---
    coverage = html.Div([
        html.Span(f'{len(completed)} Completed', style={
            'backgroundColor': '#d4edda', 'color': '#155724', 'padding': '3px 10px',
            'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '600', 'marginRight': '6px'}),
        html.Span(f'{len(open_trades)} Open', style={
            'backgroundColor': '#fff3cd', 'color': '#856404', 'padding': '3px 10px',
            'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '600', 'marginRight': '6px'}),
        html.Span(f'{len(missed)} Missed', style={
            'backgroundColor': '#f8d7da', 'color': '#721c24', 'padding': '3px 10px',
            'borderRadius': '12px', 'fontSize': '12px', 'fontWeight': '600', 'marginRight': '6px'}),
        html.Span(f'{total} total V20 signals', style={'fontSize': '12px', 'color': '#6c757d'}),
    ], style={'marginBottom': '16px', 'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '4px'})

    # --- Stats cards (completed trades only) ---
    if completed:
        gains = [t['gain_pct'] for t in completed]
        days_list = [t['holding_days'] for t in completed]
        ann_returns = [min(((1 + g / 100) ** (365 / max(d, 1)) - 1) * 100, 999.0)
                       for g, d in zip(gains, days_list)]
        avg_gain = round(np.mean(gains), 1)
        med_gain = round(np.median(gains), 1)
        avg_days = round(np.mean(days_list), 1)
        avg_ann = round(np.mean(ann_returns), 0)
        cv = (np.std(gains) / np.mean(gains) * 100) if len(gains) > 1 and np.mean(gains) > 0 else 100
        consistency = max(0, min(100, round(100 - cv))) if len(gains) > 1 else None

        def stat_card(label, value, sub=None, color='#2c3e50'):
            return html.Div([
                html.Div(value, style={'fontSize': '26px', 'fontWeight': '700', 'color': color}),
                html.Div(label, style={'fontSize': '11px', 'color': '#6c757d', 'fontWeight': '500',
                                       'textTransform': 'uppercase', 'letterSpacing': '0.5px'}),
                html.Div(sub, style={'fontSize': '11px', 'color': '#999', 'marginTop': '2px'}) if sub else None,
            ], style={'backgroundColor': '#fff', 'border': '1px solid #e9ecef', 'borderRadius': '8px',
                      'padding': '14px 18px', 'textAlign': 'center', 'flex': '1', 'minWidth': '130px'})

        cons_val = f'{consistency}/100' if consistency is not None else 'N/A*'
        cons_sub = ('High' if consistency and consistency >= 70 else 'Low') if consistency else '2+ needed'
        cards = html.Div([
            stat_card('Avg Gain', f'{avg_gain}%', f'Median {med_gain}%', '#28a745'),
            stat_card('Avg Hold Time', f'{avg_days}d', 'actual calendar days', '#007bff'),
            stat_card('Avg Ann. Return', f'~{int(avg_ann)}%', 'annualized (capped 999%)', '#e67e22'),
            stat_card('Consistency', cons_val, cons_sub, '#8e44ad'),
        ], style={'display': 'flex', 'gap': '10px', 'flexWrap': 'wrap', 'marginBottom': '16px'})

        # Completed bar chart
        c_sorted = sorted(completed, key=lambda x: x['entry_date'])
        fig = go.Figure(go.Bar(
            x=[t['entry_date'] for t in c_sorted],
            y=[t['gain_pct'] for t in c_sorted],
            marker=dict(
                color=[t['holding_days'] for t in c_sorted],
                colorscale=[[0, '#28a745'], [0.4, '#ffc107'], [1, '#dc3545']],
                colorbar=dict(title='Days Held', thickness=12, len=0.8),
                showscale=True,
            ),
            customdata=[(t['holding_days'],
                         min(((1 + t['gain_pct'] / 100) ** (365 / max(t['holding_days'], 1)) - 1) * 100, 999.0),
                         t['exit_date'], t['buy_target'], t['sell_target']) for t in c_sorted],
            hovertemplate=(
                '<b>Entry: %{x}</b>  →  Exit: %{customdata[2]}<br>'
                'Gain: <b>%{y:.1f}%</b>  |  Days held: %{customdata[0]}<br>'
                'Ann. return: ~%{customdata[1]:.0f}%<br>'
                'Buy ₹%{customdata[3]:.2f} → Sell ₹%{customdata[4]:.2f}<extra></extra>'
            ),
        ))
        fig.update_layout(
            title=dict(text=f'{symbol} — Completed V20 Trades (green=fast exit, red=slow)',
                       font_size=13),
            xaxis_title='Actual Entry Date', yaxis_title='Gain %',
            plot_bgcolor='#fafafa', paper_bgcolor='#fff',
            margin=dict(l=40, r=60, t=44, b=40), height=260,
            font=dict(family='Inter, Segoe UI, sans-serif', size=11),
            yaxis=dict(ticksuffix='%', gridcolor='#e9ecef'),
            xaxis=dict(gridcolor='#e9ecef'),
        )
        chart_section = [cards, dcc.Graph(figure=fig, config={'displayModeBar': False},
                                          style={'marginBottom': '16px'})]
    else:
        chart_section = [html.Div('No completed trades in 5-year price history.',
                                  style={'color': '#6c757d', 'fontStyle': 'italic',
                                         'marginBottom': '16px', 'padding': '10px',
                                         'backgroundColor': '#fff3cd', 'borderRadius': '6px'})]

    # --- All-signals status table ---
    th_style = {'padding': '8px 10px', 'textAlign': 'left', 'fontSize': '11px',
                'fontWeight': '600', 'color': '#fff', 'backgroundColor': '#2c3e50',
                'textTransform': 'uppercase', 'letterSpacing': '0.5px'}
    status_cfg = {
        'COMPLETED': ('✓ COMPLETED', '#155724', '#d4edda'),
        'OPEN':      ('⏳ OPEN',     '#856404', '#fff3cd'),
        'MISSED':    ('✗ MISSED',   '#721c24', '#f8d7da'),
        'NO_DATA':   ('— NO DATA',  '#6c757d', '#f8f9fa'),
    }
    trows = []
    for o in outcomes:
        label, fc, bg = status_cfg.get(o['status'], ('?', '#000', '#fff'))
        status_cell = html.Td(label, style={
            'fontWeight': '700', 'fontSize': '11px', 'color': fc,
            'backgroundColor': bg, 'padding': '6px 10px',
            'borderRadius': '4px', 'whiteSpace': 'nowrap'
        })
        entry_td = html.Td(o['entry_date'] or '—')
        exit_td  = html.Td(o['exit_date'] or '—')
        days_td  = html.Td(f'{o["holding_days"]}d' if o['holding_days'] else '—')
        ann_td   = html.Td('')
        if o['status'] == 'COMPLETED' and o['holding_days']:
            ann = min(((1 + o['gain_pct'] / 100) ** (365 / max(o['holding_days'], 1)) - 1) * 100, 999.0)
            ann_td = html.Td(f'~{int(ann)}%', style={'color': '#e67e22', 'fontWeight': '600'})
        trows.append(html.Tr([
            html.Td(o['signal_date'], style={'fontSize': '12px', 'color': '#6c757d'}),
            html.Td(f'₹{o["buy_target"]:.2f}'),
            html.Td(f'₹{o["sell_target"]:.2f}'),
            html.Td(f'{o["gain_pct"]:.1f}%', style={'color': '#28a745', 'fontWeight': '600'}),
            status_cell,
            entry_td, exit_td, days_td, ann_td,
        ], style={'borderBottom': '1px solid #f0f0f0'}))

    all_table = html.Table([
        html.Thead(html.Tr([
            html.Th('Signal Date', style=th_style),
            html.Th('Buy Target ₹', style=th_style),
            html.Th('Sell Target ₹', style=th_style),
            html.Th('Signal Gain%', style=th_style),
            html.Th('Status', style=th_style),
            html.Th('Actual Entry', style=th_style),
            html.Th('Actual Exit', style=th_style),
            html.Th('Days Held', style=th_style),
            html.Th('Ann. Return', style=th_style),
        ])),
        html.Tbody(trows),
    ], style={'width': '100%', 'borderCollapse': 'collapse', 'fontSize': '13px'})

    notes = html.Div([
        html.Div('Buy trigger: price Low ≤ buy target +5% after sequence ends  |  '
                 'Sell trigger: price High ≥ sell target −3%  |  '
                 'Price history: last 5 years (older signals may show MISSED due to data limit)',
                 style={'fontSize': '11px', 'color': '#aaa', 'marginTop': '8px'})
    ])

    return html.Div([
        header, coverage,
        *chart_section,
        html.H6('All V20 Signals — Status',
                style={'color': '#2c3e50', 'fontWeight': '600', 'marginBottom': '8px'}),
        all_table,
        notes,
    ])


def generate_v20_notifications(df, notification_engine):
    """Generate notifications for V20 signals"""
    try:
        notifications = []
        current_time = datetime.now()
        
        # Check for STRONG BUY signals (best conditions)
        strong_buy_signals = df[df.get('Signal Strength', '') == 'STRONG BUY'] if 'Signal Strength' in df.columns else pd.DataFrame()
        
        for _, stock in strong_buy_signals.head(2).iterrows():
            symbol = stock.get('Symbol', 'Unknown')
            closeness = stock.get('Closeness (%)', 0)
            buy_price = stock.get('Target Buy Price (Low)', 0)
            sell_price = buy_price * 1.20 if buy_price > 0 else 0
            full_name = stock_resolver.get_display_name(symbol)
            
            notifications.append(
                html.Div([
                    html.Div([
                        html.Span("🚀", style={'fontSize': '20px', 'marginRight': '10px'}),
                        html.Span(f"STRONG BUY: {full_name}", style={'fontWeight': 'bold', 'color': '#28a745'})
                    ]),
                    html.Div(f"{closeness:.1f}% from target | Buy: ₹{buy_price:.2f} | Sell: ₹{sell_price:.2f}", style={'fontSize': '12px', 'color': '#6c757d'}),
                    html.Div("💰 Sell at 20% profit, hold longer if strong momentum continues", style={'fontSize': '11px', 'color': '#28a745', 'fontStyle': 'italic'}),
                    html.Div(current_time.strftime('%H:%M:%S'), style={'fontSize': '10px', 'color': '#adb5bd'})
                ], style={
                    'backgroundColor': '#d4edda',
                    'border': '1px solid #c3e6cb',
                    'borderRadius': '5px',
                    'padding': '10px',
                    'margin': '5px 0',
                    'borderLeft': '4px solid #28a745'
                })
            )
        
        # Check for BUY NOW signals
        buy_now_signals = df[df.get('Signal Strength', '') == 'BUY NOW'] if 'Signal Strength' in df.columns else pd.DataFrame()
        
        for _, stock in buy_now_signals.head(3).iterrows():
            symbol = stock.get('Symbol', 'Unknown')
            closeness = stock.get('Closeness (%)', 0)
            buy_price = stock.get('Target Buy Price (Low)', 0)
            sell_price = buy_price * 1.30 if buy_price > 0 else 0
            full_name = stock_resolver.get_display_name(symbol)
            
            notifications.append(
                html.Div([
                    html.Div([
                        html.Span("📍", style={'fontSize': '20px', 'marginRight': '10px'}),
                        html.Span(f"BUY NOW: {full_name}", style={'fontWeight': 'bold', 'color': '#17a2b8'})
                    ]),
                    html.Div(f"{closeness:.1f}% from target | Buy: ₹{buy_price:.2f} | Sell: ₹{sell_price:.2f}", style={'fontSize': '12px', 'color': '#6c757d'}),
                    html.Div("💰 Target 30% gains, consider partial profit-taking at 20%", style={'fontSize': '11px', 'color': '#17a2b8', 'fontStyle': 'italic'}),
                    html.Div(current_time.strftime('%H:%M:%S'), style={'fontSize': '10px', 'color': '#adb5bd'})
                ], style={
                    'backgroundColor': '#d1ecf1',
                    'border': '1px solid #bee5eb',
                    'borderRadius': '5px',
                    'padding': '10px',
                    'margin': '5px 0',
                    'borderLeft': '4px solid #17a2b8'
                })
            )
        
        # Check for WAIT (Bearish) signals - Important warnings!
        bearish_signals = df[df.get('Signal Strength', '') == 'WAIT (Bearish)'] if 'Signal Strength' in df.columns else pd.DataFrame()
        
        for _, stock in bearish_signals.head(2).iterrows():
            symbol = stock.get('Symbol', 'Unknown')
            closeness = stock.get('Closeness (%)', 0)
            buy_price = stock.get('Target Buy Price (Low)', 0)
            full_name = stock_resolver.get_display_name(symbol)
            
            notifications.append(
                html.Div([
                    html.Div([
                        html.Span("⚠️", style={'fontSize': '20px', 'marginRight': '10px'}),
                        html.Span(f"WAIT: {full_name}", style={'fontWeight': 'bold', 'color': '#ffc107'})
                    ]),
                    html.Div(f"{closeness:.1f}% from target | Buy trigger: ₹{buy_price:.2f} | Wait for better entry", style={'fontSize': '12px', 'color': '#6c757d'}),
                    html.Div(current_time.strftime('%H:%M:%S'), style={'fontSize': '10px', 'color': '#adb5bd'})
                ], style={
                    'backgroundColor': '#fff3cd',
                    'border': '1px solid #ffeaa7',
                    'borderRadius': '5px',
                    'padding': '10px',
                    'margin': '5px 0',
                    'borderLeft': '4px solid #ffc107'
                })
            )
        
        if not notifications:
            notifications.append(
                html.Div([
                    html.Span("ℹ️", style={'fontSize': '20px', 'marginRight': '10px'}),
                    html.Span("No active alerts at this time", style={'color': '#6c757d'})
                ], style={
                    'backgroundColor': '#f8f9fa',
                    'border': '1px solid #dee2e6',
                    'borderRadius': '5px',
                    'padding': '10px',
                    'textAlign': 'center'
                })
            )
        
        return html.Div(notifications[:5])  # Limit to 5 notifications
    
    except Exception as e:
        print(f"Error generating notifications: {e}")
        return html.Div("Error loading notifications", style={'color': '#dc3545'})

    # ── Collapse toggles for notifications and indicators panels ─────────────
    from dash import Input as _In, Output as _Out, State as _St
    import dash_bootstrap_components as _dbc

    @app.callback(
        _Out("v20-notifications-collapse", "is_open"),
        _In("v20-notifications-toggle", "n_clicks"),
        _St("v20-notifications-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_notifications(n, is_open):
        return not is_open if n else is_open

    @app.callback(
        _Out("v20-indicators-collapse", "is_open"),
        _In("v20-indicators-toggle", "n_clicks"),
        _St("v20-indicators-collapse", "is_open"),
        prevent_initial_call=True,
    )
    def toggle_indicators(n, is_open):
        return not is_open if n else is_open
