#!/usr/bin/env python
# coding: utf-8

"""
Test script for Stock Screener Module
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_screener():
    """Test the stock screener with a small sample"""
    print("Testing Stock Screener...")
    
    screener = StockScreener()
    
    # Test with a few stocks first
    test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK']
    
    print(f"Testing with {len(test_symbols)} stocks: {', '.join(test_symbols)}")
    
    screened_stocks = []
    
    for symbol in test_symbols:
        print(f"\nTesting {symbol}...")
        stock_data = screener.get_financial_data(symbol)
        
        if stock_data:
            print(f"  Company: {stock_data['company_name']}")
            print(f"  Sector: {stock_data['sector']}")
            print(f"  Net Profit: ₹{stock_data['net_profit']:.2f} Cr")
            print(f"  ROCE: {stock_data['roce']:.2f}%")
            print(f"  ROE: {stock_data['roe']:.2f}%")
            print(f"  Debt/Equity: {stock_data['debt_to_equity']:.4f}")
            print(f"  Is Bank/Finance: {stock_data['is_bank_finance']}")
            
            if screener.apply_screening_criteria(stock_data):
                print(f"  ✅ {symbol} PASSES screening criteria")
                screened_stocks.append(stock_data)
            else:
                print(f"  ❌ {symbol} does not meet criteria")
        else:
            print(f"  ❌ Failed to get data for {symbol}")
    
    print(f"\n{'='*50}")
    print(f"Test Results: {len(screened_stocks)} out of {len(test_symbols)} stocks passed screening")
    
    if screened_stocks:
        print("\nStocks that passed:")
        for stock in screened_stocks:
            print(f"  - {stock['symbol']}: {stock['company_name']}")

if __name__ == "__main__":
    test_screener()