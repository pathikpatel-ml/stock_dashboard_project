#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script to verify the stock screening fixes
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_screening_fixes():
    """Test the fixed screening logic"""
    print("Testing Stock Screening Fixes")
    print("=" * 50)
    
    screener = StockScreener()
    
    # Test with a few known stocks
    test_stocks = ['TCS', 'RELIANCE', 'HDFCBANK', 'ICICIBANK', 'SBIN']
    
    print(f"Testing {len(test_stocks)} stocks...")
    
    results = []
    for symbol in test_stocks:
        print(f"\nTesting {symbol}...")
        
        # Get financial data
        stock_data = screener.get_financial_data(symbol)
        
        if stock_data:
            passes_criteria = screener.apply_screening_criteria(stock_data)
            
            result = {
                'Symbol': symbol,
                'Company': stock_data['company_name'],
                'Sector': stock_data['sector'],
                'Net Profit (Cr)': round(stock_data['net_profit'], 2),
                'ROCE (%)': round(stock_data['roce'], 2),
                'ROE (%)': round(stock_data['roe'], 2),
                'Debt/Equity': round(stock_data['debt_to_equity'], 4),
                'Latest Q Profit (Cr)': round(stock_data['latest_quarter_profit'], 2),
                'Public Holding (%)': round(stock_data['public_holding'], 2),
                'Is Bank/Finance': stock_data['is_bank_finance'],
                'Is PSU': stock_data['is_psu'],
                'Is Highest Quarter': stock_data.get('is_highest_quarter', False),
                'Passes Criteria': passes_criteria
            }
            
            results.append(result)
            
            # Print detailed info
            print(f"  Company: {result['Company']}")
            print(f"  Sector: {result['Sector']}")
            print(f"  Is Bank/Finance: {result['Is Bank/Finance']}")
            print(f"  Is PSU: {result['Is PSU']}")
            print(f"  Net Profit: ₹{result['Net Profit (Cr)']} Cr")
            print(f"  ROCE: {result['ROCE (%)']}%")
            print(f"  ROE: {result['ROE (%)']}%")
            print(f"  Debt/Equity: {result['Debt/Equity']}")
            print(f"  Public Holding: {result['Public Holding (%)']}%")
            print(f"  Latest Quarter Profit: ₹{result['Latest Q Profit (Cr)']} Cr")
            print(f"  Is Highest Quarter: {result['Is Highest Quarter']}")
            print(f"  PASSES CRITERIA: {result['Passes Criteria']}")
            
            # Show why it passed/failed
            if result['Is Bank/Finance']:
                print(f"  Bank Criteria Check:")
                print(f"    - Net Profit > 1000 Cr: {result['Net Profit (Cr)'] > 1000}")
                print(f"    - ROE > 10%: {result['ROE (%)'] > 10}")
            else:
                print(f"  Non-Bank Criteria Check:")
                print(f"    - Net Profit > 200 Cr: {result['Net Profit (Cr)'] > 200}")
                print(f"    - ROCE > 20%: {result['ROCE (%)'] > 20}")
                print(f"    - Debt/Equity < 0.25: {result['Debt/Equity'] < 0.25}")
                if not result['Is PSU']:
                    print(f"    - Public Holding < 30%: {result['Public Holding (%)'] < 30}")
            
            print(f"    - Is Highest Quarter: {result['Is Highest Quarter']}")
        else:
            print(f"  Failed to get data for {symbol}")
    
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    if results:
        passing_stocks = [r for r in results if r['Passes Criteria']]
        print(f"Total stocks tested: {len(results)}")
        print(f"Stocks passing criteria: {len(passing_stocks)}")
        print(f"Success rate: {(len(passing_stocks)/len(results))*100:.1f}%")
        
        if passing_stocks:
            print(f"\nStocks that PASS criteria:")
            for stock in passing_stocks:
                print(f"  - {stock['Symbol']}: {stock['Company']}")
        
        failing_stocks = [r for r in results if not r['Passes Criteria']]
        if failing_stocks:
            print(f"\nStocks that FAIL criteria:")
            for stock in failing_stocks:
                print(f"  - {stock['Symbol']}: {stock['Company']}")
    else:
        print("No results to analyze")

if __name__ == "__main__":
    test_screening_fixes()
