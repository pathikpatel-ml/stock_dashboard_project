#!/usr/bin/env python
"""
Test script to verify the implementation works correctly
"""

import os
import sys

def test_imports():
    """Test if all modules can be imported"""
    try:
        # Test stock screener
        from modules.stock_screener import StockScreener
        print("✓ StockScreener imports successfully")
        
        # Test data manager
        import data_manager
        print("✓ data_manager imports successfully")
        
        # Test signal generation script
        import generate_daily_signals
        print("✓ generate_daily_signals imports successfully")
        
        # Test weekly stock generation
        import generate_weekly_stock_list
        print("✓ generate_weekly_stock_list imports successfully")
        
        return True
    except Exception as e:
        print(f"✗ Import error: {e}")
        return False

def test_stock_screener():
    """Test stock screener functionality"""
    try:
        from modules.stock_screener import StockScreener
        screener = StockScreener()
        print("✓ StockScreener initialized successfully")
        
        # Test if methods exist
        assert hasattr(screener, 'screen_stocks'), "screen_stocks method missing"
        assert hasattr(screener, 'get_financial_data'), "get_financial_data method missing"
        print("✓ StockScreener has required methods")
        
        return True
    except Exception as e:
        print(f"✗ StockScreener test error: {e}")
        return False

def test_file_structure():
    """Test if required files exist"""
    required_files = [
        'modules/stock_screener.py',
        'generate_weekly_stock_list.py',
        'generate_daily_signals.py',
        'data_manager.py',
        'app.py',
        '.github/workflows/weekly_stock_screening.yml',
        '.github/workflows/daily_signal_generation.yml'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"✗ Missing files: {missing_files}")
        return False
    else:
        print("[OK] All required files exist")
        return True

def test_ma_removal():
    """Test if MA components have been removed"""
    try:
        # Check app.py doesn't import MA modules
        with open('app.py', 'r') as f:
            app_content = f.read()
            if 'ma_layout' in app_content or 'ma_callbacks' in app_content:
                print("✗ MA components still found in app.py")
                return False
        
        # Check data_manager.py doesn't have MA functions
        with open('data_manager.py', 'r') as f:
            data_manager_content = f.read()
            if 'ma_signals_df' in data_manager_content and 'ma_signals_df = pd.DataFrame()' not in data_manager_content:
                print("✗ MA signals still active in data_manager.py")
                return False
        
        print("✓ MA components successfully removed")
        return True
    except Exception as e:
        print(f"✗ MA removal test error: {e}")
        return False

def main():
    """Run all tests"""
    print("Testing Stock Dashboard Implementation...")
    print("=" * 50)
    
    tests = [
        ("File Structure", test_file_structure),
        ("MA Removal", test_ma_removal),
        ("Imports", test_imports),
        ("Stock Screener", test_stock_screener),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{test_name} Test:")
        if test_func():
            passed += 1
        else:
            print(f"  {test_name} test failed!")
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Implementation is ready.")
        return True
    else:
        print("❌ Some tests failed. Please check the implementation.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)