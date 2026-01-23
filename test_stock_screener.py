#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Script for Stock Screener Module
Tests all functionality before committing
"""

import sys
import os
import pandas as pd
from datetime import datetime
import time

# Add the modules directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_basic_initialization():
    """Test 1: Basic initialization"""
    print("Test 1: Testing StockScreener initialization...")
    try:
        screener = StockScreener()
        print("✓ StockScreener initialized successfully")
        return True
    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        return False

def test_nse_stock_list():
    """Test 2: NSE stock list fetching"""
    print("\nTest 2: Testing NSE stock list fetching...")
    try:
        screener = StockScreener()
        symbols = screener.get_nse_stock_list()
        
        if symbols and len(symbols) > 0:
            print(f"✓ Successfully fetched {len(symbols)} NSE symbols")
            print(f"  Sample symbols: {symbols[:5]}")
            return True
        else:
            print("✗ No symbols fetched")
            return False
    except Exception as e:
        print(f"✗ NSE stock list fetch failed: {e}")
        return False

def test_financial_data_fetch():
    """Test 3: Financial data fetching for sample stocks"""
    print("\nTest 3: Testing financial data fetching...")
    try:
        screener = StockScreener()
        test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK']
        
        success_count = 0
        for symbol in test_symbols:
            print(f"  Testing {symbol}...")
            data = screener.get_financial_data(symbol)
            
            if data:
                print(f"    ✓ {symbol}: Company: {data['company_name']}")
                print(f"      Net Profit: {data['net_profit']:.2f} Cr")
                print(f"      ROCE: {data['roce']:.2f}%")
                print(f"      ROE: {data['roe']:.2f}%")
                print(f"      Is Bank/Finance: {data['is_bank_finance']}")
                print(f"      Is PSU: {data['is_psu']}")
                success_count += 1
            else:
                print(f"    ✗ {symbol}: Failed to fetch data")
        
        if success_count > 0:
            print(f"✓ Successfully fetched data for {success_count}/{len(test_symbols)} stocks")
            return True
        else:
            print("✗ Failed to fetch data for any test stocks")
            return False
            
    except Exception as e:
        print(f"✗ Financial data fetch test failed: {e}")
        return False

def test_screening_criteria():
    """Test 4: Screening criteria application"""
    print("\nTest 4: Testing screening criteria...")
    try:
        screener = StockScreener()
        
        # Test bank stock (should pass)
        bank_stock = {
            'symbol': 'TEST_BANK',
            'company_name': 'Test Bank Ltd',
            'sector': 'Financial Services',
            'industry': 'Banks',
            'market_cap': 1000000000000,
            'net_profit': 1500,  # > 1000 cr
            'roce': 15,
            'roe': 15,  # > 10%
            'debt_to_equity': 0.5,
            'latest_quarter_profit': 400,
            'last_3q_profits': [350, 380, 420],
            'public_holding': 75,
            'is_bank_finance': True,
            'is_psu': False
        }
        
        # Test private sector stock (should pass)
        private_stock = {
            'symbol': 'TEST_PVT',
            'company_name': 'Test Private Ltd',
            'sector': 'Technology',
            'industry': 'Software',
            'market_cap': 500000000000,
            'net_profit': 300,  # > 200 cr
            'roce': 25,  # > 20%
            'roe': 18,
            'debt_to_equity': 0.3,
            'latest_quarter_profit': 80,
            'last_3q_profits': [70, 75, 65],  # All < 300 (net profit)
            'public_holding': 80,
            'is_bank_finance': False,
            'is_psu': False
        }
        
        # Test failing stock
        failing_stock = {
            'symbol': 'TEST_FAIL',
            'company_name': 'Test Failing Ltd',
            'sector': 'Manufacturing',
            'industry': 'Textiles',
            'market_cap': 100000000000,
            'net_profit': 150,  # < 200 cr (should fail)
            'roce': 15,  # < 20% (should fail)
            'roe': 12,
            'debt_to_equity': 0.8,
            'latest_quarter_profit': 40,
            'last_3q_profits': [35, 38, 42],
            'public_holding': 60,
            'is_bank_finance': False,
            'is_psu': False
        }
        
        # Test criteria
        bank_result = screener.apply_screening_criteria(bank_stock)
        private_result = screener.apply_screening_criteria(private_stock)
        failing_result = screener.apply_screening_criteria(failing_stock)
        
        print(f"  Bank stock (should pass): {bank_result}")
        print(f"  Private stock (should pass): {private_result}")
        print(f"  Failing stock (should fail): {failing_result}")
        
        if bank_result and private_result and not failing_result:
            print("✓ Screening criteria working correctly")
            return True
        else:
            print("✗ Screening criteria not working as expected")
            return False
            
    except Exception as e:
        print(f"✗ Screening criteria test failed: {e}")
        return False

def test_checkpoint_system():
    """Test 5: Checkpoint system"""
    print("\nTest 5: Testing checkpoint system...")
    try:
        screener = StockScreener()
        
        # Create sample data
        sample_stocks = [
            {
                'Symbol': 'TEST1',
                'Company Name': 'Test Company 1',
                'Sector': 'Technology',
                'Industry': 'Software',
                'Market Cap': 1000000000,
                'Net Profit (Cr)': 250,
                'ROCE (%)': 22,
                'ROE (%)': 18,
                'Debt to Equity': 0.3,
                'Latest Quarter Profit (Cr)': 65,
                'Last 3Q Profits (Cr)': '60, 58, 62',
                'Public Holding (%)': 75,
                'Is Bank/Finance': False,
                'Is PSU': False,
                'Passes Criteria': True,
                'Screening Date': datetime.now().strftime('%Y-%m-%d')
            }
        ]
        
        # Test checkpoint save
        screener._save_checkpoint(sample_stocks, 1)
        
        # Check if file was created
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        if os.path.exists(output_dir):
            checkpoint_files = [f for f in os.listdir(output_dir) if f.startswith('checkpoint_')]
            if checkpoint_files:
                print("✓ Checkpoint system working - file created")
                return True
        
        print("✗ Checkpoint file not found")
        return False
        
    except Exception as e:
        print(f"✗ Checkpoint system test failed: {e}")
        return False

def test_existing_data_check():
    """Test 6: Existing data check functionality"""
    print("\nTest 6: Testing existing data check...")
    try:
        screener = StockScreener()
        
        # Test existing data check
        existing_path = screener.check_existing_comprehensive_data()
        
        if existing_path:
            print(f"✓ Found existing data: {existing_path}")
            
            # Test loading existing data
            df = screener.load_existing_comprehensive_data(existing_path)
            if df is not None and not df.empty:
                print(f"✓ Successfully loaded {len(df)} records from existing data")
                return True
            else:
                print("✗ Failed to load existing data")
                return False
        else:
            print("✓ No existing data found (this is normal for first run)")
            return True
            
    except Exception as e:
        print(f"✗ Existing data check test failed: {e}")
        return False

def test_limited_screening():
    """Test 7: Limited screening with just a few stocks"""
    print("\nTest 7: Testing limited screening (5 stocks)...")
    try:
        screener = StockScreener()
        
        # Override the get_nse_stock_list method for testing
        original_method = screener.get_nse_stock_list
        screener.get_nse_stock_list = lambda: ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK']
        
        print("  Running screening on 5 test stocks...")
        df = screener.screen_stocks(checkpoint_interval=2)
        
        # Restore original method
        screener.get_nse_stock_list = original_method
        
        if df is not None:
            print(f"✓ Screening completed successfully")
            print(f"  Total stocks meeting criteria: {len(df)}")
            
            if not df.empty:
                print("  Sample results:")
                for idx, row in df.head(3).iterrows():
                    print(f"    {row['Symbol']} - {row['Company Name']}")
            
            return True
        else:
            print("✗ Screening returned None")
            return False
            
    except Exception as e:
        print(f"✗ Limited screening test failed: {e}")
        return False

def test_output_files():
    """Test 8: Check output files creation"""
    print("\nTest 8: Testing output files...")
    try:
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        
        if not os.path.exists(output_dir):
            print("✓ No output directory yet (normal for first run)")
            return True
        
        files = os.listdir(output_dir)
        csv_files = [f for f in files if f.endswith('.csv')]
        
        if csv_files:
            print(f"✓ Found {len(csv_files)} CSV files in output directory")
            for file in csv_files[-3:]:  # Show last 3 files
                print(f"  - {file}")
            return True
        else:
            print("✓ No CSV files yet (normal for first run)")
            return True
            
    except Exception as e:
        print(f"✗ Output files test failed: {e}")
        return False

def run_all_tests():
    """Run all tests"""
    print("=" * 60)
    print("STOCK SCREENER COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    
    tests = [
        test_basic_initialization,
        test_nse_stock_list,
        test_financial_data_fetch,
        test_screening_criteria,
        test_checkpoint_system,
        test_existing_data_check,
        test_limited_screening,
        test_output_files
    ]
    
    passed = 0
    total = len(tests)
    
    for i, test in enumerate(tests, 1):
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test {i} crashed: {e}")
        
        if i < total:
            print("\n" + "-" * 40)
    
    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Ready to commit.")
    elif passed >= total * 0.8:
        print("⚠️  Most tests passed. Minor issues may exist.")
    else:
        print("❌ Several tests failed. Review before committing.")
    
    print("=" * 60)
    
    return passed, total

if __name__ == "__main__":
    print("Starting comprehensive test suite...")
    print("This will test all stock screener functionality.\n")
    
    start_time = time.time()
    passed, total = run_all_tests()
    end_time = time.time()
    
    print(f"\nTotal test time: {end_time - start_time:.2f} seconds")
    
    if passed == total:
        print("\n✅ All functionality tested successfully!")
        print("You can now commit your changes with confidence.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed.")
        print("Review the issues before committing.")