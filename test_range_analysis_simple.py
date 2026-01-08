#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Simple test for stock screener without Unicode issues
"""

import sys
import os

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_simple_screening():
    """Test basic screening functionality"""
    print("Testing Stock Screener - Simple Version")
    print("=" * 40)
    
    screener = StockScreener()
    
    # Test with a small subset of stocks
    test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK']
    
    print(f"Testing with {len(test_symbols)} stocks: {', '.join(test_symbols)}")
    
    for symbol in test_symbols:
        print(f"\nTesting {symbol}...")
        try:
            data = screener.get_financial_data(symbol)
            if data:
                passes = screener.apply_screening_criteria(data)
                print(f"  Company: {data['company_name']}")
                print(f"  Sector: {data['sector']}")
                print(f"  Net Profit: Rs.{data['net_profit']:.2f} Cr")
                print(f"  Passes Criteria: {passes}")
            else:
                print(f"  Failed to get data for {symbol}")
        except Exception as e:
            print(f"  Error: {e}")
    
    print("\nTest completed successfully!")

if __name__ == "__main__":
    test_simple_screening()