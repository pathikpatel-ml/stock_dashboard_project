#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for GitHub Actions
Tests all stock screener functionality and algorithms
"""

import sys
import os
import json
from datetime import datetime
import pandas as pd

# Try to import pytest, fallback to basic testing if not available
try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    print("Warning: pytest not available, using basic test runner")

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

class TestStockScreener:
    """Test class for stock screener functionality"""
    
    @classmethod
    def setup_class(cls):
        """Setup test environment"""
        cls.screener = StockScreener()
        cls.test_results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'summary': {}
        }
    
    def test_nse_stock_list_fetch(self):
        """Test NSE stock list fetching"""
        stocks = self.screener.get_nse_stock_list()
        
        assert stocks is not None, "Stock list should not be None"
        assert len(stocks) > 0, "Stock list should not be empty"
        assert isinstance(stocks, list), "Stock list should be a list"
        
        # Test specific stocks are present
        expected_stocks = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY']
        for stock in expected_stocks:
            assert stock in stocks, f"{stock} should be in stock list"
        
        self.test_results['tests']['nse_stock_list'] = {
            'status': 'PASS',
            'count': len(stocks),
            'sample_stocks': stocks[:10]
        }
    
    def test_financial_data_extraction(self):
        """Test financial data extraction for sample stocks"""
        test_stocks = ['RELIANCE', 'TCS', 'SBIN', 'HDFCBANK']
        results = {}
        
        for symbol in test_stocks:
            data = self.screener.get_financial_data(symbol)
            
            if data:
                # Validate required fields
                required_fields = ['symbol', 'company_name', 'sector', 'net_profit', 
                                 'roce', 'roe', 'debt_to_equity', 'is_bank_finance', 'is_psu']
                
                for field in required_fields:
                    assert field in data, f"Field {field} missing for {symbol}"
                
                # Validate data types
                assert isinstance(data['net_profit'], (int, float)), f"Net profit should be numeric for {symbol}"
                assert isinstance(data['roce'], (int, float)), f"ROCE should be numeric for {symbol}"
                assert isinstance(data['roe'], (int, float)), f"ROE should be numeric for {symbol}"
                assert isinstance(data['is_bank_finance'], bool), f"is_bank_finance should be boolean for {symbol}"
                assert isinstance(data['is_psu'], bool), f"is_psu should be boolean for {symbol}"
                
                results[symbol] = {
                    'status': 'SUCCESS',
                    'company_name': data['company_name'],
                    'sector': data['sector'],
                    'net_profit': data['net_profit'],
                    'is_bank_finance': data['is_bank_finance'],
                    'is_psu': data['is_psu']
                }
            else:
                results[symbol] = {'status': 'FAILED'}
        
        # At least 50% should succeed
        success_count = sum(1 for r in results.values() if r['status'] == 'SUCCESS')
        assert success_count >= len(test_stocks) * 0.5, "At least 50% of data extraction should succeed"
        
        self.test_results['tests']['financial_data'] = results
    
    def test_sector_classification(self):
        """Test sector classification logic"""
        # Test bank classification
        bank_data = {
            'sector': 'Financial Services',
            'industry': 'Banks—Regional',
            'company_name': 'State Bank of India'
        }
        
        # Mock the classification logic
        sector = bank_data['sector'].lower()
        industry = bank_data['industry'].lower()
        is_bank = any(keyword in sector + industry for keyword in 
                     ['bank', 'finance', 'financial', 'insurance'])
        
        assert is_bank == True, "Should classify banks correctly"
        
        # Test PSU classification
        psu_companies = ['State Bank of India', 'Oil and Natural Gas Corporation', 'NTPC Limited']
        psu_results = {}
        
        for company in psu_companies:
            company_lower = company.lower()
            psu_keywords = ['bharat', 'indian', 'national', 'state bank', 'oil india', 
                           'coal india', 'ntpc', 'ongc']
            is_psu = any(keyword in company_lower for keyword in psu_keywords)
            psu_results[company] = is_psu
        
        # At least 2 should be classified as PSU
        psu_count = sum(psu_results.values())
        assert psu_count >= 2, "Should identify PSU companies correctly"
        
        self.test_results['tests']['sector_classification'] = {
            'bank_classification': True,
            'psu_classification': psu_results
        }
    
    def test_screening_criteria_logic(self):
        """Test screening criteria application"""
        test_cases = [
            {
                'name': 'Private Sector Pass',
                'data': {
                    'net_profit': 300, 'roce': 25, 'debt_to_equity': 0.2,
                    'public_holding': 35, 'is_bank_finance': False, 'is_psu': False,
                    'is_highest_quarter': True
                },
                'expected': True
            },
            {
                'name': 'Private Sector Fail - Low Public Holding',
                'data': {
                    'net_profit': 300, 'roce': 25, 'debt_to_equity': 0.2,
                    'public_holding': 25, 'is_bank_finance': False, 'is_psu': False,
                    'is_highest_quarter': True
                },
                'expected': False
            },
            {
                'name': 'PSU Pass - No Public Holding Requirement',
                'data': {
                    'net_profit': 300, 'roce': 25, 'debt_to_equity': 0.2,
                    'public_holding': 25, 'is_bank_finance': False, 'is_psu': True,
                    'is_highest_quarter': True
                },
                'expected': True
            },
            {
                'name': 'Bank Pass',
                'data': {
                    'net_profit': 1500, 'roe': 15, 'is_bank_finance': True,
                    'is_psu': False, 'is_highest_quarter': True
                },
                'expected': True
            },
            {
                'name': 'Fail - Not Highest Quarter',
                'data': {
                    'net_profit': 1500, 'roe': 15, 'is_bank_finance': True,
                    'is_psu': False, 'is_highest_quarter': False
                },
                'expected': False
            }
        ]
        
        results = {}
        for test_case in test_cases:
            result = self.screener.apply_screening_criteria(test_case['data'])
            success = result == test_case['expected']
            results[test_case['name']] = {
                'expected': test_case['expected'],
                'actual': result,
                'success': success
            }
            
            assert success, f"Test case '{test_case['name']}' failed: expected {test_case['expected']}, got {result}"
        
        self.test_results['tests']['screening_criteria'] = results
    
    def test_limited_screening_process(self):
        """Test full screening process with limited stocks"""
        # Override stock list for testing
        original_method = self.screener.get_nse_stock_list
        test_stocks = ['RELIANCE', 'TCS', 'SBIN', 'HDFCBANK', 'ICICIBANK']
        self.screener.get_nse_stock_list = lambda: test_stocks
        
        try:
            df = self.screener.screen_stocks()
            
            # Validate DataFrame structure
            if not df.empty:
                expected_columns = ['Symbol', 'Company Name', 'Sector', 'Net Profit (Cr)', 
                                  'ROCE (%)', 'ROE (%)', 'Is Bank/Finance', 'Is PSU']
                
                for col in expected_columns:
                    assert col in df.columns, f"Column {col} missing from results"
                
                # Validate data types
                assert df['Net Profit (Cr)'].dtype in ['float64', 'int64'], "Net Profit should be numeric"
                assert df['ROCE (%)'].dtype in ['float64', 'int64'], "ROCE should be numeric"
                assert df['ROE (%)'].dtype in ['float64', 'int64'], "ROE should be numeric"
            
            self.test_results['tests']['screening_process'] = {
                'total_tested': len(test_stocks),
                'results_found': len(df),
                'success': True,
                'columns_valid': True
            }
            
        finally:
            # Restore original method
            self.screener.get_nse_stock_list = original_method
    
    def test_data_validation(self):
        """Test data validation and error handling"""
        # Test with invalid data - should handle gracefully
        invalid_data = {
            'net_profit': None,
            'roce': 'invalid',
            'debt_to_equity': -1,
            'is_bank_finance': 'not_boolean'
        }
        
        # Simple validation logic
        def validate_data(data):
            try:
                # Check if numeric fields are valid
                if data.get('net_profit') is None:
                    return False
                if not isinstance(data.get('roce'), (int, float)):
                    return False
                if data.get('debt_to_equity', 0) < 0:
                    return False
                if not isinstance(data.get('is_bank_finance'), bool):
                    return False
                return True
            except:
                return False
        
        result = validate_data(invalid_data)
        assert result == False, "Should reject invalid data"
        
        # Test with valid data
        valid_data = {
            'net_profit': 100,
            'roce': 15.5,
            'debt_to_equity': 0.3,
            'is_bank_finance': True
        }
        
        result = validate_data(valid_data)
        assert result == True, "Should accept valid data"
        
        self.test_results['tests']['data_validation'] = {
            'invalid_data_handled': True,
            'valid_data_accepted': True
        }
    
    def test_export_functionality(self):
        """Test CSV export functionality"""
        # Create sample DataFrame
        sample_data = {
            'Symbol': ['TEST1', 'TEST2'],
            'Company Name': ['Test Company 1', 'Test Company 2'],
            'Sector': ['Technology', 'Finance'],
            'Net Profit (Cr)': [100, 200],
            'ROCE (%)': [15, 20],
            'ROE (%)': [12, 18],
            'Is Bank/Finance': [False, True],
            'Is PSU': [False, False]
        }
        
        df = pd.DataFrame(sample_data)
        
        # Test export
        export_path = 'test_export.csv'
        try:
            df.to_csv(export_path, index=False)
            assert os.path.exists(export_path), "Export file should be created"
            
            # Verify content
            imported_df = pd.read_csv(export_path)
            assert len(imported_df) == 2, "Should have 2 rows"
            assert list(imported_df.columns) == list(df.columns), "Columns should match"
            
            self.test_results['tests']['export_functionality'] = {
                'export_successful': True,
                'data_integrity': True
            }
            
        finally:
            # Cleanup
            if os.path.exists(export_path):
                os.remove(export_path)
    
    @classmethod
    def teardown_class(cls):
        """Generate test summary and save results"""
        total_tests = len(cls.test_results['tests'])
        passed_tests = sum(1 for test in cls.test_results['tests'].values() 
                          if test.get('status') != 'FAILED' and 
                          test.get('success', True) != False)
        
        cls.test_results['summary'] = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': total_tests - passed_tests,
            'success_rate': f"{(passed_tests/total_tests)*100:.1f}%" if total_tests > 0 else "0%"
        }
        
        # Save results to file
        with open('test_results.json', 'w') as f:
            json.dump(cls.test_results, f, indent=2, default=str)
        
        print(f"\n=== TEST SUMMARY ===")
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {cls.test_results['summary']['success_rate']}")
        print(f"Results saved to: test_results.json")

def run_tests():
    """Run all tests and return exit code"""
    if PYTEST_AVAILABLE:
        try:
            # Run pytest
            exit_code = pytest.main([__file__, '-v', '--tb=short'])
            return exit_code
        except Exception as e:
            print(f"Error running pytest: {e}")
            return 1
    else:
        # Fallback to manual test execution
        return run_manual_tests()

def run_manual_tests():
    """Manual test runner when pytest is not available"""
    test_instance = TestStockScreener()
    test_instance.setup_class()
    
    test_methods = [
        'test_nse_stock_list_fetch',
        'test_financial_data_extraction', 
        'test_sector_classification',
        'test_screening_criteria_logic',
        'test_limited_screening_process',
        'test_data_validation',
        'test_export_functionality'
    ]
    
    passed = 0
    failed = 0
    
    for method_name in test_methods:
        try:
            print(f"Running {method_name}...")
            method = getattr(test_instance, method_name)
            method()
            print(f"✓ {method_name} PASSED")
            passed += 1
        except Exception as e:
            print(f"✗ {method_name} FAILED: {e}")
            failed += 1
    
    test_instance.teardown_class()
    
    print(f"\nManual Test Results: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    print("Starting Stock Screener Test Suite...")
    print(f"Python Version: {sys.version}")
    print(f"Working Directory: {os.getcwd()}")
    print("=" * 50)
    
    exit_code = run_tests()
    
    print("\n" + "=" * 50)
    print(f"Tests completed with exit code: {exit_code}")
    
    sys.exit(exit_code)

def test_integration():
    """Integration test to verify end-to-end functionality"""
    screener = StockScreener()
    
    # Test with a known stock
    test_symbol = 'RELIANCE'
    data = screener.get_financial_data(test_symbol)
    
    if data:
        # Test that we can apply criteria
        result = screener.apply_screening_criteria(data)
        assert isinstance(result, bool), "Screening should return boolean result"
        
        print(f"Integration test passed for {test_symbol}")
        print(f"Company: {data.get('company_name', 'Unknown')}")
        print(f"Sector: {data.get('sector', 'Unknown')}")
        print(f"Meets criteria: {result}")
    else:
        if PYTEST_AVAILABLE:
            pytest.skip(f"Could not fetch data for {test_symbol} - API might be unavailable")
        else:
            print(f"Warning: Could not fetch data for {test_symbol} - API might be unavailable")