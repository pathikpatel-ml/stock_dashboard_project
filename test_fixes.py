#!/usr/bin/env python3
"""
Quick test script to verify the dashboard fixes
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that all critical imports work."""
    print("Testing imports...")
    
    try:
        import data_manager
        print("✓ data_manager imported successfully")
    except Exception as e:
        print(f"✗ data_manager import failed: {e}")
        return False
    
    try:
        from modules import signal_generator
        print("✓ signal_generator imported successfully")
    except Exception as e:
        print(f"✗ signal_generator import failed: {e}")
        return False
    
    try:
        from modules import news_sentiment_analyzer
        print("✓ news_sentiment_analyzer imported successfully")
    except Exception as e:
        print(f"✗ news_sentiment_analyzer import failed: {e}")
        return False
    
    try:
        from modules import notification_engine
        print("✓ notification_engine imported successfully")
    except Exception as e:
        print(f"✗ notification_engine import failed: {e}")
        return False
    
    return True

def test_data_manager():
    """Test data_manager functionality."""
    print("\nTesting data_manager...")
    
    try:
        import data_manager
        
        # Check if global variables exist
        assert hasattr(data_manager, 'v20_signals_df'), "v20_signals_df not found"
        assert hasattr(data_manager, 'ma_signals_df'), "ma_signals_df not found"
        print("✓ Global variables exist")
        
        # Test that they are DataFrames
        import pandas as pd
        assert isinstance(data_manager.v20_signals_df, pd.DataFrame), "v20_signals_df is not a DataFrame"
        assert isinstance(data_manager.ma_signals_df, pd.DataFrame), "ma_signals_df is not a DataFrame"
        print("✓ Global variables are proper DataFrames")
        
        return True
    except Exception as e:
        print(f"✗ data_manager test failed: {e}")
        return False

def test_signal_generator():
    """Test signal generator functionality."""
    print("\nTesting signal_generator...")
    
    try:
        from modules.signal_generator import SignalGenerator, SignalType, generate_quick_signal
        
        generator = SignalGenerator()
        print("✓ SignalGenerator created successfully")
        
        # Test quick signal generation
        signal = generate_quick_signal("TEST", 100.0, rsi=25.0)
        assert signal is not None, "Quick signal generation failed"
        assert signal.signal_type == SignalType.BUY, "Expected BUY signal for low RSI"
        print("✓ Quick signal generation works")
        
        return True
    except Exception as e:
        print(f"✗ signal_generator test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("Running dashboard fix verification tests...\n")
    
    tests = [
        test_imports,
        test_data_manager,
        test_signal_generator
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n{'='*50}")
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Dashboard should work now.")
        print("\nNext steps:")
        print("1. Install dependencies: pip install -r requirements.txt")
        print("2. Run the dashboard: python app.py")
    else:
        print("❌ Some tests failed. Check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)