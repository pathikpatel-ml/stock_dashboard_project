#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Manual test runner for local validation
Run this before pushing to GitHub to ensure everything works
"""

import sys
import os
import subprocess
import json
from datetime import datetime

def run_command(cmd, description):
    """Run a command and return success status"""
    print(f"\n{'='*50}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    print('='*50)
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        success = result.returncode == 0
        print(f"Status: {'SUCCESS' if success else 'FAILED'}")
        return success, result.stdout, result.stderr
        
    except Exception as e:
        print(f"Error running command: {e}")
        return False, "", str(e)

def main():
    """Main test runner"""
    print("Stock Screener - Local Test Runner")
    print("=" * 50)
    print(f"Test started at: {datetime.now()}")
    
    # Create output directory
    os.makedirs('output', exist_ok=True)
    
    test_results = {
        'timestamp': datetime.now().isoformat(),
        'tests': {}
    }
    
    # Test 1: Run basic functionality test
    success, stdout, stderr = run_command(
        "python test_updated_screener.py",
        "Basic functionality test"
    )
    test_results['tests']['basic_functionality'] = {
        'success': success,
        'stdout_length': len(stdout),
        'stderr_length': len(stderr)
    }
    
    # Test 2: Run pytest suite
    success, stdout, stderr = run_command(
        "python -m pytest test_github_actions.py -v --tb=short",
        "Comprehensive pytest suite"
    )
    test_results['tests']['pytest_suite'] = {
        'success': success,
        'stdout_length': len(stdout),
        'stderr_length': len(stderr)
    }
    
    # Test 3: Check if modules can be imported
    success, stdout, stderr = run_command(
        "python -c \"from modules.stock_screener import StockScreener; print('Import successful')\"",
        "Module import test"
    )
    test_results['tests']['module_import'] = {
        'success': success,
        'stdout_length': len(stdout),
        'stderr_length': len(stderr)
    }
    
    # Test 4: Quick API connectivity test
    success, stdout, stderr = run_command(
        "python -c \"import yfinance as yf; ticker = yf.Ticker('RELIANCE.NS'); info = ticker.info; print(f'API Test: {info.get(\\\"longName\\\", \\\"Unknown\\\")}')\"",
        "API connectivity test"
    )
    test_results['tests']['api_connectivity'] = {
        'success': success,
        'stdout_length': len(stdout),
        'stderr_length': len(stderr)
    }
    
    # Calculate overall results
    total_tests = len(test_results['tests'])
    passed_tests = sum(1 for test in test_results['tests'].values() if test['success'])
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    test_results['summary'] = {
        'total_tests': total_tests,
        'passed_tests': passed_tests,
        'success_rate': success_rate,
        'overall_status': 'READY' if passed_tests == total_tests else 'ISSUES_FOUND'
    }
    
    # Save results
    with open('local_test_results.json', 'w') as f:
        json.dump(test_results, f, indent=2)
    
    # Print summary
    print(f"\n{'='*50}")
    print("LOCAL TEST SUMMARY")
    print('='*50)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    print(f"Overall Status: {test_results['summary']['overall_status']}")
    
    if test_results['summary']['overall_status'] == 'READY':
        print("\n✅ ALL TESTS PASSED - Ready for GitHub Actions!")
        print("\nNext steps:")
        print("1. Commit and push your changes")
        print("2. GitHub Actions will run automatically")
        print("3. Check the Actions tab for results")
    else:
        print("\n❌ SOME TESTS FAILED - Fix issues before pushing")
        print("\nCheck the output above for specific failures")
    
    print(f"\nTest completed at: {datetime.now()}")
    return test_results['summary']['overall_status'] == 'READY'

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)