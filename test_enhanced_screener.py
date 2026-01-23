#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script for enhanced stock screener
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_enhanced_screener():
    """Test the enhanced screener with a small sample"""
    print("Testing Enhanced Stock Screener")
    print("=" * 50)
    
    screener = StockScreener()
    
    # Test with a few stocks
    test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK']
    
    print(f"Testing with symbols: {test_symbols}")
    print()
    
    for symbol in test_symbols:
        print(f"Testing {symbol}...")
        
        # Test Screener.in data extraction
        screener_data = screener.get_screener_data(symbol)
        if screener_data:
            print(f"  Screener.in D/E: {screener_data.get('debt_to_equity', 'N/A')}")
            print(f"  Screener.in Public Holding: {screener_data.get('public_holding', 'N/A')}%")
        else:
            print(f"  Failed to get Screener.in data")
        
        # Test full financial data
        financial_data = screener.get_financial_data(symbol)
        if financial_data:
            print(f"  Company: {financial_data['company_name']}")
            print(f"  Sector: {financial_data['sector']}")
            print(f"  Is Bank/Finance: {financial_data['is_bank_finance']}")
            print(f"  Is PSU: {financial_data['is_psu']}")
            print(f"  Net Profit: {financial_data['net_profit']} Cr")
            print(f"  ROCE: {financial_data['roce']}%")
            print(f"  ROE: {financial_data['roe']}%")
            print(f"  D/E Ratio: {financial_data['debt_to_equity']}")
            print(f"  Public Holding: {financial_data['public_holding']}%")
            
            # Test screening criteria
            passes = screener.apply_screening_criteria(financial_data)
            print(f"  Passes Criteria: {passes}")
        else:
            print(f"  Failed to get financial data")
        
        print("-" * 30)
    
    print("Test completed!")

if __name__ == "__main__":
    test_enhanced_screener()