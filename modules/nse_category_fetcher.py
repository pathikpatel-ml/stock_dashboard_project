import requests
import pandas as pd
from bs4 import BeautifulSoup
import json

def fetch_nse_indices():
    """Fetch all NSE indices and their constituents"""
    indices_data = {}
    
    # Major NSE indices to fetch
    indices = {
        'NIFTY 50': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050',
        'NIFTY BANK': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20BANK',
        'NIFTY IT': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20IT',
        'NIFTY PHARMA': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20PHARMA',
        'NIFTY AUTO': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20AUTO',
        'NIFTY FMCG': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20FMCG',
        'NIFTY METAL': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20METAL',
        'NIFTY REALTY': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20REALTY',
        'NIFTY ENERGY': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20ENERGY',
        'NIFTY MIDCAP 50': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20MIDCAP%2050',
        'NIFTY SMALLCAP 50': 'https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%20SMALLCAP%2050'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    for index_name, url in indices.items():
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    symbols = [stock['symbol'] for stock in data['data']]
                    indices_data[index_name] = symbols
                    print(f"Fetched {len(symbols)} stocks for {index_name}")
        except Exception as e:
            print(f"Error fetching {index_name}: {e}")
            # Fallback data for major indices
            if index_name == 'NIFTY 50':
                indices_data[index_name] = get_nifty50_fallback()
    
    return indices_data

def get_nifty50_fallback():
    """Fallback NIFTY 50 stocks if API fails"""
    return ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'HINDUNILVR', 'ICICIBANK', 'KOTAKBANK', 
            'BHARTIARTL', 'ITC', 'SBIN', 'LT', 'ASIANPAINT', 'AXISBANK', 'MARUTI', 'NESTLEIND',
            'HCLTECH', 'BAJFINANCE', 'TITAN', 'ULTRACEMCO', 'WIPRO', 'SUNPHARMA', 'ONGC',
            'NTPC', 'TECHM', 'POWERGRID', 'TATAMOTORS', 'BAJAJFINSV', 'COALINDIA', 'HDFCLIFE',
            'GRASIM', 'SBILIFE', 'BRITANNIA', 'EICHERMOT', 'ADANIPORTS', 'JSWSTEEL', 'HINDALCO',
            'INDUSINDBK', 'TATASTEEL', 'CIPLA', 'DRREDDY', 'APOLLOHOSP', 'DIVISLAB', 'HEROMOTOCO',
            'BAJAJ-AUTO', 'BPCL', 'TATACONSUM', 'UPL', 'SHREECEM', 'ADANIENT', 'LTIM']

def create_stock_category_mapping(indices_data):
    """Create mapping of stock to categories"""
    stock_categories = {}
    
    for index_name, symbols in indices_data.items():
        for symbol in symbols:
            if symbol not in stock_categories:
                stock_categories[symbol] = []
            stock_categories[symbol].append(index_name)
    
    return stock_categories

def get_nse_stock_categories():
    """Get all NSE stock categories mapping"""
    try:
        indices_data = fetch_nse_indices()
        return create_stock_category_mapping(indices_data)
    except:
        return {}

def get_stock_categories(symbol):
    """Get categories for a specific stock"""
    try:
        indices_data = fetch_nse_indices()
        stock_categories = create_stock_category_mapping(indices_data)
        return stock_categories.get(symbol.upper(), [])
    except:
        return []