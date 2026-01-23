#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script to fetch public holding and debt to equity using yfinance API
"""

import requests
import time

def get_screener_data(symbol):
    """Fetch public holding and debt to equity using yfinance as fallback"""
    try:
        import yfinance as yf
        
        # Try yfinance as primary source since Screener.in API seems to be having issues
        print(f"\nFetching data for {symbol} using yfinance...")
        ticker = yf.Ticker(f"{symbol}.NS")
        info = ticker.info
        
        if not info or 'symbol' not in info:
            print(f"No data found for {symbol}")
            return {'success': False}
        
        # Extract available data
        company_name = info.get('longName', symbol)
        
        # Calculate public holding percentage
        float_shares = info.get('floatShares', 0)
        shares_outstanding = info.get('sharesOutstanding', 0)
        public_holding = (float_shares / shares_outstanding * 100) if shares_outstanding > 0 else 0
        
        # Get debt to equity ratio
        debt_to_equity = info.get('debtToEquity', 0) / 100 if info.get('debtToEquity') else 0
        
        # Additional useful metrics
        market_cap = info.get('marketCap', 0)
        sector = info.get('sector', 'Unknown')
        industry = info.get('industry', 'Unknown')
        
        print(f"Symbol: {symbol}")
        print(f"Company: {company_name}")
        print(f"Sector: {sector}")
        print(f"Industry: {industry}")
        print(f"Market Cap: {market_cap:,}")
        print(f"Public Holding: {public_holding:.2f}%")
        print(f"Debt to Equity: {debt_to_equity:.4f}")
        
        return {
            'symbol': symbol,
            'company_name': company_name,
            'sector': sector,
            'industry': industry,
            'market_cap': market_cap,
            'public_holding': public_holding,
            'debt_to_equity': debt_to_equity,
            'success': True
        }
            
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return {'success': False}

if __name__ == "__main__":
    # Test with a few stocks
    test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK']
    
    print("Testing Stock Data API for Public Holding and Debt to Equity")
    print("=" * 60)
    
    successful_fetches = 0
    
    for symbol in test_symbols:
        result = get_screener_data(symbol)
        if result.get('success'):
            successful_fetches += 1
        time.sleep(1)  # Rate limiting
        print("-" * 60)
    
    print(f"\nTest completed! Successfully fetched data for {successful_fetches}/{len(test_symbols)} stocks.")
