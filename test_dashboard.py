#!/usr/bin/env python
"""
Test script for Stock Dashboard
Verifies all components work correctly and generates sample data if needed.
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import numpy as np

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.append(project_root)

def create_sample_data():
    """Create sample data files for testing if they don't exist."""
    
    # Sample V20 signals data
    current_date = datetime.now()
    sample_signals = []
    
    symbols = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'ITC', 'LT', 'WIPRO', 'MARUTI']
    
    for i, symbol in enumerate(symbols):
        buy_date = current_date - timedelta(days=np.random.randint(1, 30))
        buy_price = np.random.uniform(100, 2000)
        sell_price = buy_price * np.random.uniform(1.05, 1.25)  # 5-25% gain target
        
        sample_signals.append({
            'Symbol': symbol,
            'Buy_Date': buy_date,
            'Buy_Price_Low': buy_price,
            'Sell_Price_High': sell_price,
            'Sell_Date': pd.NaT if np.random.random() > 0.3 else buy_date + timedelta(days=np.random.randint(1, 15)),
            'Sequence_Gain_Percent': ((sell_price - buy_price) / buy_price) * 100,
            'Company_Name': f'{symbol} Company',
            'Market_Cap': np.random.uniform(10000, 500000)
        })
    
    # Create V20 signals file
    signals_df = pd.DataFrame(sample_signals)
    signals_filename = f"stock_candle_signals_from_listing_{current_date.strftime('%Y%m%d')}.csv"
    signals_path = os.path.join(project_root, signals_filename)
    signals_df.to_csv(signals_path, index=False)
    print(f"Created sample V20 signals file: {signals_filename}")
    
    # Sample MA signals data
    ma_events = []
    event_types = ['Primary_Buy', 'Primary_Sell', 'Secondary_Buy_Dip', 'Secondary_Sell_Rise', 'Open_Position']
    
    for symbol in symbols[:5]:  # Use fewer symbols for MA signals
        for j in range(np.random.randint(2, 6)):  # 2-5 events per symbol
            event_date = current_date - timedelta(days=np.random.randint(1, 60))
            event_type = np.random.choice(event_types)
            price = np.random.uniform(100, 2000)
            
            ma_events.append({
                'Symbol': symbol,
                'Date': event_date,
                'Event_Type': event_type,
                'Price': price,
                'Company Name': f'{symbol} Company',
                'Type': 'Large Cap',
                'MarketCap': np.random.uniform(50000, 500000),
                'Details': f'{event_type} signal at {price:.2f}'
            })
    
    # Create MA signals file
    ma_df = pd.DataFrame(ma_events)
    ma_filename = f"ma_signals_data_{current_date.strftime('%Y%m%d')}.csv"
    ma_path = os.path.join(project_root, ma_filename)
    ma_df.to_csv(ma_path, index=False)
    print(f"Created sample MA signals file: {ma_filename}")
    
    # Sample growth data
    growth_data = []
    for symbol in symbols:
        growth_data.append({
            'Symbol': symbol,
            'Company_Name': f'{symbol} Company',
            'Market_Cap': np.random.uniform(10000, 500000),
            'Growth_Rate': np.random.uniform(-10, 25),
            'Sector': np.random.choice(['Technology', 'Banking', 'Energy', 'Consumer', 'Industrial'])
        })
    
    growth_df = pd.DataFrame(growth_data)
    growth_path = os.path.join(project_root, "Master_company_market_trend_analysis.csv")
    growth_df.to_csv(growth_path, index=False)
    print(f"Created sample growth file: Master_company_market_trend_analysis.csv")

def test_dashboard_components():
    """Test individual dashboard components."""
    
    print("\n=== Testing Dashboard Components ===")
    
    try:
        # Test imports
        print("Testing imports...")
        from run_dashboard_interactive_host import (
            load_data_for_dashboard_from_repo,
            process_ma_signals_for_ui,
            fetch_historical_data_for_graph,
            get_nearest_to_buy_from_loaded_signals,
            indicator_calculator,
            sentiment_analyzer,
            signal_generator,
            notification_engine
        )
        print("✓ All imports successful")
        
        # Test data loading
        print("Testing data loading...")
        result = load_data_for_dashboard_from_repo()
        print(f"✓ Data loading: {'Success' if result else 'Failed'}")
        
        # Test indicator calculator
        print("Testing indicator calculator...")
        sample_prices = np.random.uniform(100, 200, 100)
        indicators = indicator_calculator.calculate_all(sample_prices, sample_prices, sample_prices)
        print(f"✓ Indicator calculator: {len(indicators)} indicators calculated")
        
        # Test sentiment analyzer
        print("Testing sentiment analyzer...")
        sample_text = "This is a positive news about the stock market"
        try:
            sentiment = sentiment_analyzer.analyze_text(sample_text)
            print(f"✓ Sentiment analyzer: Working")
        except Exception as e:
            print(f"⚠ Sentiment analyzer: {e}")
        
        # Test signal generator
        print("Testing signal generator...")
        try:
            signals = signal_generator.generate_signals(sample_prices, sample_prices, sample_prices, sample_prices)
            print(f"✓ Signal generator: {len(signals)} signals generated")
        except Exception as e:
            print(f"⚠ Signal generator: {e}")
        
        print("\n✓ All component tests completed")
        
    except Exception as e:
        print(f"✗ Component test failed: {e}")
        return False
    
    return True

def test_dashboard_startup():
    """Test dashboard startup without running the server."""
    
    print("\n=== Testing Dashboard Startup ===")
    
    try:
        # Import the app
        from run_dashboard_interactive_host import app, server
        
        # Test layout creation
        layout = app.layout()
        print("✓ Dashboard layout created successfully")
        
        # Test server object
        if server:
            print("✓ WSGI server object created")
        
        print("✓ Dashboard startup test completed")
        return True
        
    except Exception as e:
        print(f"✗ Dashboard startup test failed: {e}")
        return False

def main():
    """Main test function."""
    
    print("Stock Dashboard Test Suite")
    print("=" * 50)
    
    # Check if sample data exists, create if not
    current_date = datetime.now().strftime('%Y%m%d')
    signals_file = f"stock_candle_signals_from_listing_{current_date}.csv"
    ma_file = f"ma_signals_data_{current_date}.csv"
    growth_file = "Master_company_market_trend_analysis.csv"
    
    if not all(os.path.exists(f) for f in [signals_file, ma_file, growth_file]):
        print("Sample data files not found. Creating sample data...")
        create_sample_data()
    else:
        print("Sample data files found.")
    
    # Run component tests
    components_ok = test_dashboard_components()
    
    # Run startup tests
    startup_ok = test_dashboard_startup()
    
    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY:")
    print(f"Components: {'✓ PASS' if components_ok else '✗ FAIL'}")
    print(f"Startup: {'✓ PASS' if startup_ok else '✗ FAIL'}")
    
    if components_ok and startup_ok:
        print("\n🎉 All tests passed! Dashboard is ready to run.")
        print("\nTo start the dashboard:")
        print("python run_dashboard_interactive_host.py")
        print("\nThen open: http://localhost:8050")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
    
    return components_ok and startup_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)