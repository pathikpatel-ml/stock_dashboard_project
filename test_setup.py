#!/usr/bin/env python
"""
Comprehensive test setup script to verify all changes and requirements
for the stock dashboard project.
"""

import sys
import os
import subprocess
from pathlib import Path

def print_header(text):
    """Print formatted header."""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60 + "\n")

def check_python_version():
    """Verify Python version is 3.10+."""
    print_header("1. CHECKING PYTHON VERSION")
    version = sys.version_info
    print(f"Python Version: {version.major}.{version.minor}.{version.micro}")
    if version.major >= 3 and version.minor >= 10:
        print("? Python version is compatible (3.10+)")
        return True
    else:
        print("? Python version is too old. Please upgrade to Python 3.10+")
        return False

def check_and_install_requirements():
    """Check and install all required packages."""
    print_header("2. CHECKING & INSTALLING REQUIREMENTS")
    
    requirements = {
        'numpy': 'numpy',
        'pandas': 'pandas',
        'yfinance': 'yfinance',
        'dash': 'dash',
        'plotly': 'plotly',
        'requests': 'requests',
        'textblob': 'textblob',
        'nltk': 'nltk',
        'newsapi': 'newsapi',
        'python-dotenv': 'python-dotenv',
    }
    
    installed = []
    missing = []
    
    for pkg_name, import_name in requirements.items():
        try:
            __import__(import_name)
            print(f"? {pkg_name} is installed")
            installed.append(pkg_name)
        except ImportError:
            print(f"? {pkg_name} is missing")
            missing.append(pkg_name)
    
    if missing:
        print(f"\nInstalling missing packages: {', '.join(missing)}")
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', 
                '--upgrade', '--quiet'
            ] + missing)
            print("? All missing packages installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"? Failed to install packages: {e}")
            return False
    else:
        print("\n? All required packages are installed")
        return True

def test_indicator_imports():
    """Test importing all indicator modules."""
    print_header("3. TESTING INDICATOR MODULE IMPORTS")
    
    try:
        from src.indicators import (
            IndicatorCache,
            RSI,
            MACD,
            BollingerBands,
            StochasticOscillator,
            ADX,
            ATR,
            IchimokuCloud,
            KeltnerChannel,
            AdvancedIndicatorCalculator,
            identify_signals
        )
        print("? Successfully imported all indicator classes")
        print("  - IndicatorCache")
        print("  - RSI")
        print("  - MACD")
        print("  - BollingerBands")
        print("  - StochasticOscillator")
        print("  - ADX")
        print("  - ATR")
        print("  - IchimokuCloud")
        print("  - KeltnerChannel")
        print("  - AdvancedIndicatorCalculator")
        print("  - identify_signals")
        return True
    except ImportError as e:
        print(f"? Failed to import indicators: {e}")
        return False

def test_news_sentiment_imports():
    """Test importing news and sentiment modules."""
    print_header("4. TESTING NEWS & SENTIMENT MODULE IMPORTS")
    
    try:
        from modules.news_sentiment_analyzer import (
            CacheManager,
            SentimentAnalyzer,
            NewsAPIPatcher
        )
        print("? Successfully imported news sentiment analyzer classes")
        print("  - CacheManager")
        print("  - SentimentAnalyzer")
        print("  - NewsAPIPatcher")
        return True
    except ImportError as e:
        print(f"? Failed to import news sentiment modules: {e}")
        return False

def test_signal_generator_imports():
    """Test importing signal generator module."""
    print_header("5. TESTING SIGNAL GENERATOR MODULE IMPORTS")
    
    try:
        from modules.signal_generator import (
            TechnicalIndicators,
            SignalGenerator,
            SignalType,
            TradingSignal,
            IndicatorSignal
        )
        print("? Successfully imported signal generator classes")
        print("  - TechnicalIndicators")
        print("  - SignalGenerator")
        print("  - SignalType")
        print("  - TradingSignal")
        print("  - IndicatorSignal")
        return True
    except ImportError as e:
        print(f"? Failed to import signal generator modules: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_basic_functionality():
    """Test basic functionality of key modules."""
    print_header("6. TESTING BASIC FUNCTIONALITY")
    
    try:
        import numpy as np
        from src.indicators import RSI, MACD, BollingerBands
        
        # Generate sample price data
        prices = np.array([100 + i + np.sin(i/10)*5 for i in range(100)])
        
        # Test RSI
        rsi = RSI(period=14)
        rsi_values = rsi.calculate(prices)
        print(f"? RSI calculation successful - Last RSI value: {rsi_values[-1]:.2f}")
        
        # Test MACD
        macd = MACD(fast_period=12, slow_period=26, signal_period=9)
        macd_line, signal_line, histogram = macd.calculate(prices)
        print(f"? MACD calculation successful - Last MACD value: {macd_line[-1]:.4f}")
        
        # Test Bollinger Bands
        bb = BollingerBands(period=20, std_dev=2.0)
        upper, middle, lower = bb.calculate(prices)
        print(f"? Bollinger Bands calculation successful - Middle band value: {middle[-1]:.2f}")
        
        return True
    except Exception as e:
        print(f"? Functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_project_structure():
    """Verify project directory structure."""
    print_header("7. VERIFYING PROJECT STRUCTURE")
    
    required_paths = [
        'src/indicators/__init__.py',
        'src/indicators/advanced_indicators.py',
        'modules/signal_generator.py',
        'modules/news_sentiment_analyzer.py',
        'modules/advanced_indicators.py',
        'tests/test_advanced_indicators.py',
        'requirements.txt',
        'environment.yml'
    ]
    
    all_exist = True
    for path in required_paths:
        if os.path.exists(path):
            print(f"? {path}")
        else:
            print(f"? {path} - NOT FOUND")
            all_exist = False
    
    return all_exist

def check_environment_variables():
    """Check for required environment variables."""
    print_header("8. CHECKING ENVIRONMENT VARIABLES")
    
    # Check for .env file
    env_file = Path('.env')
    if env_file.exists():
        print("? .env file found")
        try:
            from dotenv import load_dotenv
            load_dotenv()
            newsapi_key = os.getenv('NEWS_API_KEY')
            if newsapi_key:
                print("? NEWS_API_KEY is configured")
            else:
                print("? NEWS_API_KEY is not set (optional)")
            return True
        except Exception as e:
            print(f"? Error loading .env file: {e}")
            return True
    else:
        print("? .env file not found - create one with NEWS_API_KEY for full functionality")
        return True

def create_venv_instructions():
    """Create instructions for setting up virtual environment."""
    print_header("9. VIRTUAL ENVIRONMENT SETUP INSTRUCTIONS")
    
    instructions = """
For Windows (Command Prompt):
  1. Create virtual environment:
     python -m venv venv
  
  2. Activate virtual environment:
     venv\\Scripts\\activate
  
  3. Install requirements:
     pip install -r requirements.txt
  
For Windows (PowerShell):
  1. Create virtual environment:
     python -m venv venv
  
  2. Activate virtual environment:
     .\\venv\\Scripts\\Activate.ps1
  
  3. Install requirements:
     pip install -r requirements.txt

For macOS/Linux:
  1. Create virtual environment:
     python -m venv venv
  
  2. Activate virtual environment:
     source venv/bin/activate
  
  3. Install requirements:
     pip install -r requirements.txt

Alternative using Conda (if using Conda):
  1. Create environment:
     conda env create -f environment.yml
  
  2. Activate environment:
     conda activate stock-dashboard-env
    """
    
    print(instructions)
    return True

def main():
    """Run all tests and checks."""
    print("\n" + "="*60)
    print("  STOCK DASHBOARD PROJECT - COMPREHENSIVE TEST SETUP")
    print("="*60)
    
    results = {
        'Python Version': check_python_version(),
        'Requirements': check_and_install_requirements(),
        'Project Structure': verify_project_structure(),
        'Indicator Imports': test_indicator_imports(),
        'News/Sentiment Imports': test_news_sentiment_imports(),
        'Signal Generator Imports': test_signal_generator_imports(),
        'Basic Functionality': test_basic_functionality(),
        'Environment Variables': check_environment_variables(),
        'Venv Instructions': create_venv_instructions(),
    }
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "? PASSED" if result else "? FAILED"
        print(f"{test_name:<30} {status}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n? All checks passed! Your environment is ready.")
        print("\nNext Steps:")
        print("  1. Create/activate your virtual environment (see instructions above)")
        print("  2. Run: python -m pytest tests/ -v")
        print("  3. Start the dashboard: python run_dashboard_interactive_host.py")
    else:
        print("\n? Some checks failed. Please review the errors above.")
    
    print("\n" + "="*60 + "\n")
    
    return 0 if passed == total else 1

if __name__ == '__main__':
    sys.exit(main())
