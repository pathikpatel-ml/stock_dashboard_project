import pytest
import pandas as pd
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import time
from datetime import datetime

# Add the modules directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'modules'))

from stock_screener import StockScreener


class TestStockScreenerUnit:
    """Unit tests for StockScreener class"""
    
    @pytest.fixture
    def screener(self):
        return StockScreener()
    
    @pytest.fixture
    def sample_stock_data(self):
        return {
            'symbol': 'RELIANCE',
            'company_name': 'Reliance Industries Limited',
            'sector': 'Oil Gas & Consumable Fuels',
            'industry': 'Refineries',
            'market_cap': 1500000000000,
            'net_profit': 500,
            'roce': 25,
            'roe': 15,
            'debt_to_equity': 0.2,
            'latest_quarter_profit': 150,
            'public_holding': 50,
            'is_bank_finance': False,
            'is_psu': False,
            'is_highest_quarter': True
        }
    
    def test_screener_initialization(self, screener):
        """Test StockScreener initialization"""
        assert screener is not None
        assert hasattr(screener, 'get_nse_stock_list')
        assert hasattr(screener, 'get_financial_data')
        assert hasattr(screener, 'apply_screening_criteria')
    
    def test_apply_screening_criteria_private_sector_pass(self, screener, sample_stock_data):
        """Test screening criteria for private sector stocks that should pass"""
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is True
    
    def test_apply_screening_criteria_private_sector_fail_profit(self, screener, sample_stock_data):
        """Test screening criteria fails for low profit"""
        sample_stock_data['net_profit'] = 100  # Below 200 cr threshold
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is False
    
    def test_apply_screening_criteria_private_sector_fail_roce(self, screener, sample_stock_data):
        """Test screening criteria fails for low ROCE"""
        sample_stock_data['roce'] = 15  # Below 20% threshold
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is False
    
    def test_apply_screening_criteria_private_sector_fail_debt(self, screener, sample_stock_data):
        """Test screening criteria fails for high debt"""
        sample_stock_data['debt_to_equity'] = 0.3  # Above 0.25 threshold
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is False
    
    def test_apply_screening_criteria_private_sector_fail_public_holding(self, screener, sample_stock_data):
        """Test screening criteria fails for low public holding"""
        sample_stock_data['public_holding'] = 25  # Below 30% threshold
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is False
    
    def test_apply_screening_criteria_psu_pass(self, screener, sample_stock_data):
        """Test screening criteria for PSU stocks that should pass"""
        sample_stock_data['is_psu'] = True
        sample_stock_data['public_holding'] = 20  # PSU doesn't need 30% public holding
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is True
    
    def test_apply_screening_criteria_bank_pass(self, screener, sample_stock_data):
        """Test screening criteria for bank stocks that should pass"""
        sample_stock_data['is_bank_finance'] = True
        sample_stock_data['net_profit'] = 1200  # Above 1000 cr threshold
        sample_stock_data['roe'] = 15  # Above 10% threshold
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is True
    
    def test_apply_screening_criteria_bank_fail(self, screener, sample_stock_data):
        """Test screening criteria for bank stocks that should fail"""
        sample_stock_data['is_bank_finance'] = True
        sample_stock_data['net_profit'] = 800  # Below 1000 cr threshold
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is False
    
    def test_apply_screening_criteria_no_highest_quarter(self, screener, sample_stock_data):
        """Test screening criteria fails when not highest quarter"""
        sample_stock_data['is_highest_quarter'] = False
        result = screener.apply_screening_criteria(sample_stock_data)
        assert result is False
    
    def test_apply_screening_criteria_none_data(self, screener):
        """Test screening criteria with None data"""
        result = screener.apply_screening_criteria(None)
        assert result is False
    
    def test_apply_screening_criteria_empty_data(self, screener):
        """Test screening criteria with empty data"""
        result = screener.apply_screening_criteria({})
        assert result is False


class TestStockScreenerIntegration:
    """Integration tests for StockScreener class"""
    
    @pytest.fixture
    def screener(self):
        return StockScreener()
    
    @patch('yfinance.Ticker')
    def test_get_financial_data_success(self, mock_ticker, screener):
        """Test successful financial data retrieval"""
        # Mock yfinance response
        mock_stock = Mock()
        mock_stock.info = {
            'longName': 'Test Company Limited',
            'sector': 'Technology',
            'industry': 'Software',
            'marketCap': 1000000000000,
            'returnOnAssets': 0.15,
            'returnOnEquity': 0.20,
            'debtToEquity': 20,
            'heldPercentInsiders': 25,
            'heldPercentInstitutions': 45
        }
        
        # Mock quarterly financials
        mock_quarterly = pd.DataFrame({
            'Net Income': [100000000, 90000000, 80000000, 85000000]
        })
        mock_stock.quarterly_financials = mock_quarterly
        
        mock_ticker.return_value = mock_stock
        
        result = screener.get_financial_data('TEST')
        
        assert result is not None
        assert result['symbol'] == 'TEST'
        assert result['company_name'] == 'Test Company Limited'
        assert result['sector'] == 'Technology'
        assert result['market_cap'] == 1000000000000
    
    @patch('yfinance.Ticker')
    def test_get_financial_data_failure(self, mock_ticker, screener):
        """Test financial data retrieval failure"""
        mock_ticker.side_effect = Exception("Network error")
        
        result = screener.get_financial_data('INVALID')
        assert result is None
    
    @patch('requests.get')
    def test_get_nse_stock_list_success(self, mock_get, screener):
        """Test successful NSE stock list retrieval"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'data': [
                {'symbol': 'RELIANCE'},
                {'symbol': 'TCS'},
                {'symbol': 'INFY'}
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = screener.get_nse_stock_list()
        
        assert len(result) == 3
        assert 'RELIANCE' in result
        assert 'TCS' in result
        assert 'INFY' in result
    
    @patch('requests.get')
    def test_get_nse_stock_list_failure(self, mock_get, screener):
        """Test NSE stock list retrieval failure"""
        mock_get.side_effect = Exception("Network error")
        
        result = screener.get_nse_stock_list()
        assert result == []
    
    @patch.object(StockScreener, 'get_nse_stock_list')
    @patch.object(StockScreener, 'get_financial_data')
    def test_screen_stocks_integration(self, mock_get_financial, mock_get_nse, screener):
        """Test complete stock screening integration"""
        # Mock NSE stock list
        mock_get_nse.return_value = ['TEST1', 'TEST2']
        
        # Mock financial data - one passes, one fails
        mock_get_financial.side_effect = [
            {
                'symbol': 'TEST1',
                'company_name': 'Test Company 1',
                'sector': 'Technology',
                'industry': 'Software',
                'market_cap': 1000000000000,
                'net_profit': 300,
                'roce': 25,
                'roe': 15,
                'debt_to_equity': 0.2,
                'latest_quarter_profit': 80,
                'public_holding': 50,
                'is_bank_finance': False,
                'is_psu': False,
                'is_highest_quarter': True
            },
            {
                'symbol': 'TEST2',
                'company_name': 'Test Company 2',
                'sector': 'Banking',
                'industry': 'Banks',
                'market_cap': 500000000000,
                'net_profit': 100,  # Fails criteria
                'roce': 15,
                'roe': 8,
                'debt_to_equity': 0.1,
                'latest_quarter_profit': 25,
                'public_holding': 40,
                'is_bank_finance': False,
                'is_psu': False,
                'is_highest_quarter': True
            }
        ]
        
        result = screener.screen_stocks()
        
        assert len(result) == 1
        assert result.iloc[0]['Symbol'] == 'TEST1'


class TestStockScreenerPerformance:
    """Performance tests for StockScreener class"""
    
    @pytest.fixture
    def screener(self):
        return StockScreener()
    
    def test_screening_criteria_performance(self, screener):
        """Test performance of screening criteria application"""
        sample_data = {
            'symbol': 'TEST',
            'company_name': 'Test Company',
            'sector': 'Technology',
            'industry': 'Software',
            'market_cap': 1000000000000,
            'net_profit': 300,
            'roce': 25,
            'roe': 15,
            'debt_to_equity': 0.2,
            'latest_quarter_profit': 80,
            'public_holding': 50,
            'is_bank_finance': False,
            'is_psu': False,
            'is_highest_quarter': True
        }
        
        start_time = time.time()
        
        # Run screening criteria 1000 times
        for _ in range(1000):
            screener.apply_screening_criteria(sample_data)
        
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Should complete 1000 iterations in less than 1 second
        assert execution_time < 1.0, f"Performance test failed: {execution_time:.3f}s for 1000 iterations"
    
    @patch.object(StockScreener, 'get_nse_stock_list')
    @patch.object(StockScreener, 'get_financial_data')
    def test_bulk_screening_performance(self, mock_get_financial, mock_get_nse, screener):
        """Test performance of bulk stock screening"""
        # Mock 100 stocks
        mock_symbols = [f'TEST{i}' for i in range(100)]
        mock_get_nse.return_value = mock_symbols
        
        # Mock financial data that passes criteria
        mock_financial_data = {
            'symbol': 'TEST',
            'company_name': 'Test Company',
            'sector': 'Technology',
            'industry': 'Software',
            'market_cap': 1000000000000,
            'net_profit': 300,
            'roce': 25,
            'roe': 15,
            'debt_to_equity': 0.2,
            'latest_quarter_profit': 80,
            'public_holding': 50,
            'is_bank_finance': False,
            'is_psu': False,
            'is_highest_quarter': True
        }
        
        mock_get_financial.return_value = mock_financial_data
        
        start_time = time.time()
        result = screener.screen_stocks()
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        # Should process 100 stocks in reasonable time (allowing for rate limiting)
        assert execution_time < 60, f"Bulk screening too slow: {execution_time:.3f}s for 100 stocks"
        assert len(result) == 100  # All should pass with mocked data


class TestStockScreenerEdgeCases:
    """Edge case tests for StockScreener class"""
    
    @pytest.fixture
    def screener(self):
        return StockScreener()
    
    def test_missing_financial_data_fields(self, screener):
        """Test handling of missing financial data fields"""
        incomplete_data = {
            'symbol': 'TEST',
            'company_name': 'Test Company',
            'net_profit': 300,
            'is_highest_quarter': True
            # Missing other required fields
        }
        
        # Should handle missing fields gracefully
        result = screener.apply_screening_criteria(incomplete_data)
        # May pass or fail depending on default values, but shouldn't crash
        assert isinstance(result, bool)
    
    def test_extreme_values(self, screener):
        """Test handling of extreme financial values"""
        extreme_data = {
            'symbol': 'TEST',
            'company_name': 'Test Company',
            'sector': 'Technology',
            'industry': 'Software',
            'market_cap': float('inf'),
            'net_profit': 999999,
            'roce': 1000,
            'roe': 500,
            'debt_to_equity': 0,
            'latest_quarter_profit': 250000,
            'public_holding': 100,
            'is_bank_finance': False,
            'is_psu': False,
            'is_highest_quarter': True
        }
        
        # Should handle extreme values without crashing
        result = screener.apply_screening_criteria(extreme_data)
        assert isinstance(result, bool)
    
    def test_negative_values(self, screener):
        """Test handling of negative financial values"""
        negative_data = {
            'symbol': 'TEST',
            'company_name': 'Test Company',
            'sector': 'Technology',
            'industry': 'Software',
            'market_cap': 1000000000000,
            'net_profit': -100,  # Negative profit
            'roce': -5,
            'roe': -10,
            'debt_to_equity': 0.2,
            'latest_quarter_profit': -25,
            'public_holding': 50,
            'is_bank_finance': False,
            'is_psu': False,
            'is_highest_quarter': True
        }
        
        result = screener.apply_screening_criteria(negative_data)
        # Should fail due to negative profit
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])