#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Improved test script to verify the stock screening fixes with better error handling
"""

import sys
import os
import time
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_screening_fixes():
    """Test the fixed screening logic with improved error handling"""
    print("Testing Stock Screening Fixes (Improved)")
    print("=" * 50)
    
    screener = StockScreener()
    
    # Test with a few known stocks - start with more reliable ones
    test_stocks = ['TCS', 'INFY', 'HDFCBANK', 'WIPRO', 'TECHM']
    
    print(f"Testing {len(test_stocks)} stocks...")
    
    results = []
    successful_tests = 0
    
    for i, symbol in enumerate(test_stocks):
        print(f"\n[{i+1}/{len(test_stocks)}] Testing {symbol}...")
        
        try:
            # Get financial data with retry logic
            stock_data = screener.get_financial_data(symbol)
            
            if stock_data:
                successful_tests += 1
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
                print(f"  ✓ Company: {result['Company']}\")\n                print(f"  ✓ Sector: {result['Sector']}\")\n                print(f"  ✓ Is Bank/Finance: {result['Is Bank/Finance']}\")\n                print(f"  ✓ Is PSU: {result['Is PSU']}\")\n                print(f"  ✓ Net Profit: ₹{result['Net Profit (Cr)']} Cr\")\n                print(f"  ✓ ROCE: {result['ROCE (%)']}%\")\n                print(f"  ✓ ROE: {result['ROE (%)']}%\")\n                print(f"  ✓ Debt/Equity: {result['Debt/Equity']}\")\n                print(f"  ✓ Latest Quarter Profit: ₹{result['Latest Q Profit (Cr)']} Cr\")\n                print(f"  ✓ Public Holding: {result['Public Holding (%)']}%\")\n                print(f"  ✓ Is Highest Quarter: {result['Is Highest Quarter']}\")\n                print(f"  ✓ PASSES CRITERIA: {result['Passes Criteria']}\")\n                \n                # Show detailed criteria check\n                if result['Is Bank/Finance']:\n                    print(f"  📊 Bank/Finance Criteria Check:\")\n                    net_profit_check = result['Net Profit (Cr)'] > 1000\n                    roe_check = result['ROE (%)'] > 10\n                    highest_quarter_check = result['Is Highest Quarter']\n                    \n                    print(f"    - Net Profit > 1000 Cr: {net_profit_check} ({result['Net Profit (Cr)']} Cr)\")\n                    print(f"    - ROE > 10%: {roe_check} ({result['ROE (%)']}%)\")\n                    print(f"    - Is Highest Quarter: {highest_quarter_check}\")\n                    \n                    expected_pass = net_profit_check and roe_check and highest_quarter_check\n                    print(f"    - Expected Result: {expected_pass}\")\n                    print(f"    - Actual Result: {result['Passes Criteria']}\")\n                    \n                else:\n                    print(f"  📊 Non-Bank Criteria Check:\")\n                    net_profit_check = result['Net Profit (Cr)'] > 200\n                    roce_check = result['ROCE (%)'] > 20\n                    debt_check = result['Debt/Equity'] < 0.25\n                    highest_quarter_check = result['Is Highest Quarter']\n                    \n                    print(f"    - Net Profit > 200 Cr: {net_profit_check} ({result['Net Profit (Cr)']} Cr)\")\n                    print(f"    - ROCE > 20%: {roce_check} ({result['ROCE (%)']}%)\")\n                    print(f"    - Debt/Equity < 0.25: {debt_check} ({result['Debt/Equity']})\")\n                    print(f"    - Is Highest Quarter: {highest_quarter_check}\")\n                    \n                    if result['Is PSU']:\n                        expected_pass = net_profit_check and roce_check and debt_check and highest_quarter_check\n                        print(f"    - PSU: No public holding requirement\")\n                    else:\n                        public_holding_check = result['Public Holding (%)'] > 30\n                        print(f"    - Public Holding > 30%: {public_holding_check} ({result['Public Holding (%)']}%)\")\n                        expected_pass = net_profit_check and roce_check and debt_check and highest_quarter_check and public_holding_check\n                    \n                    print(f"    - Expected Result: {expected_pass}\")\n                    print(f"    - Actual Result: {result['Passes Criteria']}\")\n                \n            else:\n                print(f"  ❌ Failed to get data for {symbol}\")\n                \n        except Exception as e:\n            print(f"  ❌ Error processing {symbol}: {e}\")\n        \n        # Small delay between stocks\n        if i < len(test_stocks) - 1:\n            time.sleep(1)\n    \n    print(\"\\n\" + \"=\" * 50)\n    print(\"SUMMARY\")\n    print(\"=\" * 50)\n    \n    if results:\n        passing_stocks = [r for r in results if r['Passes Criteria']]\n        print(f\"Total stocks tested: {len(results)}\")\n        print(f\"Successful API calls: {successful_tests}\")\n        print(f\"Stocks passing criteria: {len(passing_stocks)}\")\n        print(f\"Success rate: {(len(passing_stocks)/len(results))*100:.1f}%\")\n        \n        if passing_stocks:\n            print(f\"\\n✅ Stocks that PASS criteria:\")\n            for stock in passing_stocks:\n                print(f\"  - {stock['Symbol']}: {stock['Company']}\")\n        \n        failing_stocks = [r for r in results if not r['Passes Criteria']]\n        if failing_stocks:\n            print(f\"\\n❌ Stocks that FAIL criteria:\")\n            for stock in failing_stocks:\n                print(f\"  - {stock['Symbol']}: {stock['Company']}\")\n                \n        # Show sector breakdown\n        sectors = {}\n        for stock in results:\n            sector = stock['Sector']\n            if sector not in sectors:\n                sectors[sector] = {'total': 0, 'passing': 0}\n            sectors[sector]['total'] += 1\n            if stock['Passes Criteria']:\n                sectors[sector]['passing'] += 1\n        \n        print(f\"\\n📊 Sector Analysis:\")\n        for sector, data in sectors.items():\n            rate = (data['passing'] / data['total']) * 100 if data['total'] > 0 else 0\n            print(f\"  - {sector}: {data['passing']}/{data['total']} ({rate:.1f}%)\")\n            \n    else:\n        print(\"❌ No results to analyze - all API calls failed\")\n        print(\"\\n💡 Suggestions:\")\n        print(\"  - Check internet connection\")\n        print(\"  - Try running the test again (API might be temporarily unavailable)\")\n        print(\"  - Consider using a VPN if there are regional restrictions\")\n\ndef test_individual_stock(symbol):\n    \"\"\"Test a single stock in detail\"\"\"\n    print(f\"\\nDetailed test for {symbol}:\")\n    print(\"-\" * 30)\n    \n    screener = StockScreener()\n    stock_data = screener.get_financial_data(symbol)\n    \n    if stock_data:\n        print(f\"Raw data retrieved successfully:\")\n        for key, value in stock_data.items():\n            print(f\"  {key}: {value}\")\n        \n        passes = screener.apply_screening_criteria(stock_data)\n        print(f\"\\nPasses screening: {passes}\")\n    else:\n        print(f\"Failed to get data for {symbol}\")\n\nif __name__ == \"__main__\":\n    test_screening_fixes()\n    \n    # Optionally test individual stocks\n    print(\"\\n\" + \"=\" * 50)\n    print(\"Individual Stock Test (Optional)\")\n    print(\"=\" * 50)\n    \n    test_symbol = input(\"\\nEnter a stock symbol to test individually (or press Enter to skip): \").strip().upper()\n    if test_symbol:\n        test_individual_stock(test_symbol)