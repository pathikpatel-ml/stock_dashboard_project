#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Stock Screening Debug Tool
"""

import sys
import os
import time
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

def test_imports():
    """Test if all required modules can be imported"""
    print("Testing imports...")
    try:
        import pandas as pd
        print("[OK] pandas imported")
        
        import yfinance as yf
        print("[OK] yfinance imported")
        
        import requests
        print("[OK] requests imported")
        
        from stock_screener import StockScreener
        print("[OK] StockScreener imported")
        
        return True
    except Exception as e:
        print(f"[ERROR] Import error: {e}")
        return False

def test_single_stock():
    """Test fetching data for a single stock"""
    print("\nTesting single stock data fetch...")
    try:
        from stock_screener import StockScreener
        screener = StockScreener()
        
        symbol = 'RELIANCE'
        print(f"Fetching data for {symbol}...")
        
        start_time = time.time()
        stock_data = screener.get_financial_data(symbol)
        end_time = time.time()
        
        if stock_data:
            print(f"[OK] Data fetched in {end_time - start_time:.2f} seconds")
            print(f"  Company: {stock_data['company_name']}")
            print(f"  Sector: {stock_data['sector']}")
            print(f"  Market Cap: {stock_data['market_cap']:,}")
            print(f"  Net Profit: {stock_data['net_profit']:.2f} Cr")
            print(f"  ROCE: {stock_data['roce']:.2f}%")
            print(f"  ROE: {stock_data['roe']:.2f}%")
            print(f"  Debt/Equity: {stock_data['debt_to_equity']:.4f}")
            print(f"  Is Bank/Finance: {stock_data['is_bank_finance']}")
            print(f"  Is PSU: {stock_data['is_psu']}")
            
            # Test screening criteria
            passes = screener.apply_screening_criteria(stock_data)
            print(f"  Passes Criteria: {passes}")
            
            return True
        else:
            print("[ERROR] Failed to fetch stock data")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error testing single stock: {e}")
        return False

def test_multiple_stocks():
    """Test fetching data for multiple stocks"""
    print("\nTesting multiple stocks...")
    try:
        from stock_screener import StockScreener
        screener = StockScreener()
        
        test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK']
        successful = 0
        
        for symbol in test_symbols:
            print(f"Testing {symbol}...")
            try:
                stock_data = screener.get_financial_data(symbol)
                if stock_data:
                    print(f"  [OK] {symbol}: {stock_data['company_name']}")
                    successful += 1
                else:
                    print(f"  [ERROR] {symbol}: No data")
            except Exception as e:
                print(f"  [ERROR] {symbol}: {str(e)[:50]}")
        
        print(f"\nSuccess rate: {successful}/{len(test_symbols)} ({successful/len(test_symbols)*100:.1f}%)")
        return successful > 0
        
    except Exception as e:
        print(f"[ERROR] Error testing multiple stocks: {e}")
        return False

def test_network():
    """Test network connectivity"""
    print("\nTesting network connectivity...")
    try:
        import requests
        
        # Test yfinance endpoint
        response = requests.get('https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS', timeout=10)
        if response.status_code == 200:
            print("[OK] Yahoo Finance API accessible")
        else:
            print(f"[ERROR] Yahoo Finance API returned status {response.status_code}")
            
        return True
    except Exception as e:
        print(f"[ERROR] Network test failed: {e}")
        return False

def main():
    """Main debug function"""
    print("Stock Screening Debug Tool")
    print("=" * 50)
    
    # Run all tests
    tests = [
        ("Import Test", test_imports),
        ("Network Test", test_network),
        ("Single Stock Test", test_single_stock),
        ("Multiple Stocks Test", test_multiple_stocks)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}")
        print("-" * len(test_name))
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"[ERROR] {test_name} crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("DEBUG SUMMARY")
    print("=" * 50)
    
    passed = 0
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n[SUCCESS] All tests passed! Your stock screener should work.")
        print("You can now run: python modules/stock_screener.py")
    else:
        print("\n[WARNING] Some tests failed. Check the errors above.")
        
        if passed == 0:
            print("\nTroubleshooting steps:")
            print("1. Check internet connection")
            print("2. Install missing packages: pip install yfinance pandas requests")
            print("3. Try running again after a few minutes")

if __name__ == "__main__":
    main()