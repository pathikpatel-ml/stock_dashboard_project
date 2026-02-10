#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test Script for Stock Screener Implementation
Tests all the new modules and functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_nse_categories():
    """Test NSE category fetcher"""
    print("Testing NSE Category Fetcher...")
    try:
        from modules.nse_category_fetcher import get_nse_stock_categories
        categories = get_nse_stock_categories()
        print(f"✓ NSE Categories: Found {len(categories)} stocks with categories")
        
        # Show sample
        sample_stocks = list(categories.keys())[:5]
        for stock in sample_stocks:
            print(f"  {stock}: {categories[stock]}")
        return True
    except Exception as e:
        print(f"✗ NSE Categories Error: {e}")
        return False

def test_moving_averages():
    """Test moving average calculator"""
    print("\nTesting Moving Average Calculator...")
    try:
        from modules.ma_calculator import calculate_moving_averages
        ma_data = calculate_moving_averages("RELIANCE")
        print(f"✓ Moving Averages: {ma_data}")
        return True
    except Exception as e:
        print(f"✗ Moving Averages Error: {e}")
        return False

def test_data_manager():
    """Test data manager functions"""
    print("\nTesting Data Manager...")
    try:
        import data_manager
        
        # Test loading functions
        print("✓ Data Manager: All functions imported successfully")
        
        # Test global variables
        print(f"✓ Comprehensive stocks DF: {type(data_manager.comprehensive_stocks_df)}")
        print(f"✓ NSE categories DF: {type(data_manager.nse_categories_df)}")
        return True
    except Exception as e:
        print(f"✗ Data Manager Error: {e}")
        return False

def test_screener_layout():
    """Test screener layout"""
    print("\nTesting Screener Layout...")
    try:
        from modules.screener_layout import create_screener_layout
        layout = create_screener_layout()
        print("✓ Screener Layout: Created successfully")
        return True
    except Exception as e:
        print(f"✗ Screener Layout Error: {e}")
        return False

def test_screener_callbacks():
    """Test screener callbacks"""
    print("\nTesting Screener Callbacks...")
    try:
        from modules.screener_callbacks import register_screener_callbacks
        print("✓ Screener Callbacks: Imported successfully")
        return True
    except Exception as e:
        print(f"✗ Screener Callbacks Error: {e}")
        return False

def test_app_integration():
    """Test app integration"""
    print("\nTesting App Integration...")
    try:
        import app
        print("✓ App Integration: All imports successful")
        return True
    except Exception as e:
        print(f"✗ App Integration Error: {e}")
        return False

def main():
    """Run all tests"""
    print("Stock Screener Implementation Test")
    print("=" * 40)
    
    tests = [
        test_nse_categories,
        test_moving_averages,
        test_data_manager,
        test_screener_layout,
        test_screener_callbacks,
        test_app_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 40)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Stock screener is ready to use.")
        print("\nNext steps:")
        print("1. Run the app: python app.py")
        print("2. Navigate to the 'Stock Screener' tab")
        print("3. Apply filters and explore stocks")
    else:
        print("❌ Some tests failed. Please check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)