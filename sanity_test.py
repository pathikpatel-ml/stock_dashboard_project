#!/usr/bin/env python3
"""
Sanity Test for Stock Dashboard Implementation
Tests all critical components before pushing to main branch
"""

import sys
import os
import pandas as pd
import traceback
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test all critical imports"""
    print("[TEST] Testing imports...")
    try:
        import data_manager
        from modules import v20_layout, v20_callbacks, screener_layout, screener_callbacks
        import app
        print("[PASS] All imports successful")
        return True
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        return False

def test_data_manager():
    """Test data manager functionality"""
    print("[TEST] Testing data manager...")
    try:
        import data_manager
        
        # Test global variables exist
        assert hasattr(data_manager, 'v20_signals_df')
        assert hasattr(data_manager, 'v20_processed_df')
        assert hasattr(data_manager, 'all_available_symbols')
        
        # Test functions exist
        assert callable(data_manager.process_v20_signals)
        assert callable(data_manager.load_and_process_data_on_startup)
        
        print("[PASS] Data manager structure valid")
        return True
    except Exception as e:
        print(f"[FAIL] Data manager test failed: {e}")
        return False

def test_v20_processing():
    """Test V20 signal processing with mock data"""
    print("[TEST] Testing V20 processing...")
    try:
        import data_manager
        
        # Create mock data
        mock_data = pd.DataFrame({
            'Symbol': ['RELIANCE', 'TCS'],
            'Buy_Price_Low': [2500.0, 3500.0],
            'Buy_Date': ['2024-01-15', '2024-01-16'],
            'Sequence_Gain_Percent': [15.5, 12.3]
        })
        
        # Test processing (will fail on yfinance but structure should work)
        result = data_manager.process_v20_signals(mock_data)
        assert isinstance(result, pd.DataFrame)
        
        print("[PASS] V20 processing structure valid")
        return True
    except Exception as e:
        print(f"[FAIL] V20 processing test failed: {e}")
        return False

def test_app_structure():
    """Test app structure and layout"""
    print("[TEST] Testing app structure...")
    try:
        import app
        
        # Check app exists and has required attributes
        assert hasattr(app, 'app')
        assert hasattr(app, 'server')
        
        # Check layout exists
        assert app.app.layout is not None
        
        print("[PASS] App structure valid")
        return True
    except Exception as e:
        print(f"[FAIL] App structure test failed: {e}")
        return False

def test_module_layouts():
    """Test module layouts"""
    print("[TEST] Testing module layouts...")
    try:
        from modules import v20_layout, screener_layout
        
        # Test layout functions exist
        assert callable(v20_layout.create_v20_layout)
        assert callable(screener_layout.create_screener_layout)
        
        print("[PASS] Module layouts valid")
        return True
    except Exception as e:
        print(f"[FAIL] Module layouts test failed: {e}")
        return False

def test_file_structure():
    """Test critical files exist"""
    print("[TEST] Testing file structure...")
    try:
        required_files = [
            'app.py',
            'data_manager.py',
            'modules/v20_layout.py',
            'modules/v20_callbacks.py',
            'modules/screener_layout.py',
            'modules/screener_callbacks.py',
            'requirements.txt'
        ]
        
        for file_path in required_files:
            full_path = os.path.join(os.path.dirname(__file__), file_path)
            assert os.path.exists(full_path), f"Missing file: {file_path}"
        
        print("[PASS] File structure valid")
        return True
    except Exception as e:
        print(f"[FAIL] File structure test failed: {e}")
        return False

def test_startup_data_loading():
    """Test startup data loading"""
    print("[TEST] Testing startup data loading...")
    try:
        import data_manager
        
        # Reset globals
        data_manager.v20_signals_df = pd.DataFrame()
        data_manager.v20_processed_df = pd.DataFrame()
        data_manager.all_available_symbols = []
        
        # Test startup function exists and runs
        data_manager.load_and_process_data_on_startup()
        
        print("[PASS] Startup data loading completed (may have empty results if no data)")
        return True
    except Exception as e:
        print(f"[FAIL] Startup data loading test failed: {e}")
        return False

def run_sanity_tests():
    """Run all sanity tests"""
    print("[START] Starting Sanity Tests for Stock Dashboard")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_file_structure,
        test_data_manager,
        test_v20_processing,
        test_module_layouts,
        test_app_structure,
        test_startup_data_loading
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[FAIL] Test {test.__name__} crashed: {e}")
            failed += 1
        print()
    
    print("=" * 50)
    print(f"[RESULTS] Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("[SUCCESS] ALL TESTS PASSED! Ready for commit to main branch.")
        return True
    else:
        print("[WARNING] Some tests failed. Please fix issues before committing.")
        return False

if __name__ == "__main__":
    success = run_sanity_tests()
    sys.exit(0 if success else 1)