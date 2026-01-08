#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for stock screener with limited stocks
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_small_batch():
    """Test with a small batch of stocks"""
    screener = StockScreener()
    
    # Override the stock list with just a few stocks for testing
    test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK']
    
    print("Testing stock screener with 5 stocks...")
    print("="*50)
    
    screened_stocks = []
    
    for i, symbol in enumerate(test_symbols):
        try:
            print(f"Processing [{i+1}/5] {symbol}")
            
            # Get financial data
            stock_data = screener.get_financial_data(symbol)
            
            if stock_data:
                passes_criteria = screener.apply_screening_criteria(stock_data)
                
                print(f"  Company: {stock_data['company_name']}")
                print(f"  Sector: {stock_data['sector']}")
                print(f"  Net Profit: {stock_data['net_profit']:.2f} Cr")
                print(f"  ROCE: {stock_data['roce']:.2f}%")
                print(f"  ROE: {stock_data['roe']:.2f}%")
                print(f"  Passes Criteria: {passes_criteria}")
                print("-" * 30)
                
                if passes_criteria:
                    screened_stocks.append(stock_data)
            else:
                print(f"  Failed to get data for {symbol}")
                print("-" * 30)
                
        except Exception as e:
            print(f"  Error processing {symbol}: {e}")
            print("-" * 30)
    
    print(f"\nTest completed. Found {len(screened_stocks)} stocks meeting criteria.")
    return len(screened_stocks) > 0

if __name__ == "__main__":
    success = test_small_batch()
    if success:
        print("\nTest successful! You can now run the full screener.")
    else:
        print("\nTest failed. Check your internet connection and dependencies.")