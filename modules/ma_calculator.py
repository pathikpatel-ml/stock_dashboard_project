import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def calculate_moving_averages(symbol, periods=[10, 50, 100, 200]):
    """Calculate moving averages for a stock symbol"""
    try:
        # Fetch historical data (250 days to ensure we have enough for MA200)
        ticker = f"{symbol}.NS"
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")
        
        if hist.empty:
            return {}
        
        ma_data = {}
        current_price = hist['Close'].iloc[-1]
        
        for period in periods:
            if len(hist) >= period:
                ma_value = hist['Close'].rolling(window=period).mean().iloc[-1]
                ma_data[f'MA{period}'] = round(ma_value, 2)
                ma_data[f'MA{period}_Signal'] = 'Above' if current_price > ma_value else 'Below'
                ma_data[f'MA{period}_Diff_Pct'] = round(((current_price - ma_value) / ma_value) * 100, 2)
        
        # Calculate crossovers
        ma_data.update(calculate_ma_crossovers(hist))
        ma_data['Current_Price'] = round(current_price, 2)
        
        return ma_data
    except Exception as e:
        print(f"Error calculating MAs for {symbol}: {e}")
        return {}

def calculate_ma_crossovers(hist_data):
    """Calculate moving average crossovers"""
    crossovers = {}
    
    if len(hist_data) < 200:
        return crossovers
    
    # Calculate MAs
    hist_data['MA10'] = hist_data['Close'].rolling(window=10).mean()
    hist_data['MA50'] = hist_data['Close'].rolling(window=50).mean()
    hist_data['MA100'] = hist_data['Close'].rolling(window=100).mean()
    hist_data['MA200'] = hist_data['Close'].rolling(window=200).mean()
    
    # Check recent crossovers (last 5 days)
    recent_data = hist_data.tail(5)
    
    # MA10 vs MA50 crossover
    if len(recent_data) >= 2:
        ma10_above_ma50_today = recent_data['MA10'].iloc[-1] > recent_data['MA50'].iloc[-1]
        ma10_above_ma50_yesterday = recent_data['MA10'].iloc[-2] > recent_data['MA50'].iloc[-2]
        
        if ma10_above_ma50_today and not ma10_above_ma50_yesterday:
            crossovers['MA10_MA50_Cross'] = 'Golden Cross'
        elif not ma10_above_ma50_today and ma10_above_ma50_yesterday:
            crossovers['MA10_MA50_Cross'] = 'Death Cross'
        else:
            crossovers['MA10_MA50_Cross'] = 'No Recent Cross'
    
    # MA50 vs MA200 crossover
    if len(recent_data) >= 2:
        ma50_above_ma200_today = recent_data['MA50'].iloc[-1] > recent_data['MA200'].iloc[-1]
        ma50_above_ma200_yesterday = recent_data['MA50'].iloc[-2] > recent_data['MA200'].iloc[-2]
        
        if ma50_above_ma200_today and not ma50_above_ma200_yesterday:
            crossovers['MA50_MA200_Cross'] = 'Golden Cross'
        elif not ma50_above_ma200_today and ma50_above_ma200_yesterday:
            crossovers['MA50_MA200_Cross'] = 'Death Cross'
        else:
            crossovers['MA50_MA200_Cross'] = 'No Recent Cross'
    
    return crossovers

def get_ma_signals(symbol):
    """Get MA-based buy/sell signals"""
    ma_data = calculate_moving_averages(symbol)
    signals = []
    
    if not ma_data:
        return signals
    
    # Strong buy signal: Price above all MAs
    if all(ma_data.get(f'MA{period}_Signal') == 'Above' for period in [10, 50, 100, 200] if f'MA{period}_Signal' in ma_data):
        signals.append('Strong Buy - Above all MAs')
    
    # Buy signal: Golden cross
    if ma_data.get('MA10_MA50_Cross') == 'Golden Cross':
        signals.append('Buy - MA10/MA50 Golden Cross')
    
    if ma_data.get('MA50_MA200_Cross') == 'Golden Cross':
        signals.append('Buy - MA50/MA200 Golden Cross')
    
    # Sell signals
    if ma_data.get('MA10_MA50_Cross') == 'Death Cross':
        signals.append('Sell - MA10/MA50 Death Cross')
    
    if ma_data.get('MA50_MA200_Cross') == 'Death Cross':
        signals.append('Sell - MA50/MA200 Death Cross')
    
    return signals

def calculate_bulk_mas(symbols, batch_size=20):
    """Calculate MAs for multiple symbols in batches"""
    results = {}
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        print(f"Processing MA batch {i//batch_size + 1}: {len(batch)} symbols")
        
        for symbol in batch:
            results[symbol] = calculate_moving_averages(symbol)
    
    return results