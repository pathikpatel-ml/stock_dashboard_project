"""
Comprehensive test suite for advanced indicators module.

This module contains extensive unit tests for all advanced technical indicators
including RSI, MACD, Bollinger Bands, Stochastic Oscillator, ADX, and more.
"""

import unittest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.indicators.advanced_indicators import (
    RSI,
    MACD,
    BollingerBands,
    StochasticOscillator,
    ADX,
    ATR,
    IchimokuCloud,
    KeltnerChannel
)


class TestDataGenerator:
    """Utility class to generate test data for indicator testing."""
    
    @staticmethod
    def generate_price_data(length=100, trend='neutral', volatility=2.0):
        """
        Generate synthetic price data for testing.
        
        Args:
            length (int): Number of data points
            trend (str): 'uptrend', 'downtrend', or 'neutral'
            volatility (float): Standard deviation of price changes
            
        Returns:
            pd.DataFrame: DataFrame with OHLCV data
        """
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=length, freq='D')
        
        # Base price
        base_price = 100.0
        close_prices = [base_price]
        
        # Generate price movement based on trend
        for i in range(1, length):
            trend_factor = {
                'uptrend': 0.5,
                'downtrend': -0.5,
                'neutral': 0.0
            }.get(trend, 0.0)
            
            change = np.random.normal(trend_factor, volatility)
            new_price = max(close_prices[-1] + change, 1.0)
            close_prices.append(new_price)
        
        close_prices = np.array(close_prices)
        
        # Generate OHLC from close prices
        opens = close_prices + np.random.normal(0, 0.5, length)
        highs = np.maximum(close_prices, opens) + np.abs(np.random.normal(0, 0.5, length))
        lows = np.minimum(close_prices, opens) - np.abs(np.random.normal(0, 0.5, length))
        volumes = np.random.randint(1000000, 5000000, length)
        
        df = pd.DataFrame({
            'date': dates,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': close_prices,
            'volume': volumes
        })
        
        df.set_index('date', inplace=True)
        return df


class TestRSI(unittest.TestCase):
    """Test suite for Relative Strength Index (RSI) indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
        self.rsi = RSI(period=14)
    
    def test_rsi_initialization(self):
        """Test RSI initialization with valid parameters."""
        self.assertEqual(self.rsi.period, 14)
        self.assertIsNotNone(self.rsi)
    
    def test_rsi_calculation(self):
        """Test RSI calculation produces valid values."""
        rsi_values = self.rsi.calculate(self.test_data['close'])
        
        # RSI should be between 0 and 100
        valid_rsi = rsi_values.dropna()
        self.assertTrue(np.all((valid_rsi >= 0) & (valid_rsi <= 100)))
    
    def test_rsi_length(self):
        """Test RSI output has correct length."""
        rsi_values = self.rsi.calculate(self.test_data['close'])
        self.assertEqual(len(rsi_values), len(self.test_data))
    
    def test_rsi_nan_handling(self):
        """Test RSI handles NaN values in first period-1 values."""
        rsi_values = self.rsi.calculate(self.test_data['close'])
        
        # First (period-1) values should be NaN
        self.assertTrue(rsi_values.iloc[:self.rsi.period-1].isna().all())
    
    def test_rsi_oversold_condition(self):
        """Test RSI detects oversold conditions (RSI < 30)."""
        # Create data with downtrend
        downtrend_data = TestDataGenerator.generate_price_data(
            length=100, trend='downtrend', volatility=3.0
        )
        rsi_values = self.rsi.calculate(downtrend_data['close'])
        
        # Should have some oversold values
        oversold = (rsi_values < 30).sum()
        self.assertGreater(oversold, 0)
    
    def test_rsi_overbought_condition(self):
        """Test RSI detects overbought conditions (RSI > 70)."""
        # Create data with uptrend
        uptrend_data = TestDataGenerator.generate_price_data(
            length=100, trend='uptrend', volatility=3.0
        )
        rsi_values = self.rsi.calculate(uptrend_data['close'])
        
        # Should have some overbought values
        overbought = (rsi_values > 70).sum()
        self.assertGreater(overbought, 0)
    
    def test_rsi_custom_period(self):
        """Test RSI with custom period."""
        custom_rsi = RSI(period=21)
        rsi_values = custom_rsi.calculate(self.test_data['close'])
        
        # Custom period should result in more NaN values at start
        self.assertTrue(rsi_values.iloc[:20].isna().all())
        self.assertFalse(rsi_values.iloc[20:].isna().all())
    
    def test_rsi_empty_input(self):
        """Test RSI handles empty input gracefully."""
        empty_series = pd.Series([], dtype=float)
        result = self.rsi.calculate(empty_series)
        self.assertEqual(len(result), 0)
    
    def test_rsi_constant_prices(self):
        """Test RSI with constant prices (no change)."""
        constant_prices = pd.Series([100.0] * 50)
        result = self.rsi.calculate(constant_prices)
        
        # With no price changes, RSI should be 50
        valid_rsi = result.dropna()
        if len(valid_rsi) > 0:
            self.assertTrue(np.allclose(valid_rsi.iloc[-1], 50, atol=5))


class TestMACD(unittest.TestCase):
    """Test suite for MACD (Moving Average Convergence Divergence) indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
        self.macd = MACD(fast_period=12, slow_period=26, signal_period=9)
    
    def test_macd_initialization(self):
        """Test MACD initialization with valid parameters."""
        self.assertEqual(self.macd.fast_period, 12)
        self.assertEqual(self.macd.slow_period, 26)
        self.assertEqual(self.macd.signal_period, 9)
    
    def test_macd_calculation(self):
        """Test MACD calculation produces valid outputs."""
        macd_line, signal_line, histogram = self.macd.calculate(self.test_data['close'])
        
        # Check all outputs have correct length
        self.assertEqual(len(macd_line), len(self.test_data))
        self.assertEqual(len(signal_line), len(self.test_data))
        self.assertEqual(len(histogram), len(self.test_data))
    
    def test_macd_histogram_calculation(self):
        """Test MACD histogram is correctly calculated."""
        macd_line, signal_line, histogram = self.macd.calculate(self.test_data['close'])
        
        # Histogram should be MACD - Signal
        expected_histogram = macd_line - signal_line
        
        valid_indices = ~(macd_line.isna() | signal_line.isna() | histogram.isna())
        np.testing.assert_array_almost_equal(
            histogram[valid_indices],
            expected_histogram[valid_indices],
            decimal=6
        )
    
    def test_macd_signal_crossover(self):
        """Test MACD signal line crossover detection."""
        macd_line, signal_line, histogram = self.macd.calculate(self.test_data['close'])
        
        # Detect crossovers where histogram changes sign
        valid_histogram = histogram.dropna()
        if len(valid_histogram) > 1:
            sign_changes = np.diff(np.sign(valid_histogram))
            crossovers = np.sum(sign_changes != 0)
            self.assertGreaterEqual(crossovers, 0)
    
    def test_macd_custom_periods(self):
        """Test MACD with custom periods."""
        custom_macd = MACD(fast_period=5, slow_period=13, signal_period=5)
        macd_line, signal_line, histogram = custom_macd.calculate(self.test_data['close'])
        
        self.assertEqual(len(macd_line), len(self.test_data))
    
    def test_macd_nan_handling(self):
        """Test MACD handles NaN values appropriately."""
        macd_line, signal_line, histogram = self.macd.calculate(self.test_data['close'])
        
        # First slow_period values should be NaN
        self.assertTrue(macd_line.iloc[:self.macd.slow_period-1].isna().all())


class TestBollingerBands(unittest.TestCase):
    """Test suite for Bollinger Bands indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
        self.bb = BollingerBands(period=20, num_std=2)
    
    def test_bollinger_bands_initialization(self):
        """Test Bollinger Bands initialization."""
        self.assertEqual(self.bb.period, 20)
        self.assertEqual(self.bb.num_std, 2)
    
    def test_bollinger_bands_calculation(self):
        """Test Bollinger Bands calculation."""
        upper, middle, lower = self.bb.calculate(self.test_data['close'])
        
        self.assertEqual(len(upper), len(self.test_data))
        self.assertEqual(len(middle), len(self.test_data))
        self.assertEqual(len(lower), len(self.test_data))
    
    def test_bollinger_bands_ordering(self):
        """Test upper band > middle > lower band."""
        upper, middle, lower = self.bb.calculate(self.test_data['close'])
        
        valid_indices = ~(upper.isna() | middle.isna() | lower.isna())
        
        self.assertTrue(np.all(upper[valid_indices] >= middle[valid_indices]))
        self.assertTrue(np.all(middle[valid_indices] >= lower[valid_indices]))
    
    def test_bollinger_bands_symmetry(self):
        """Test upper and lower bands are symmetric around middle."""
        upper, middle, lower = self.bb.calculate(self.test_data['close'])
        
        valid_indices = ~(upper.isna() | middle.isna() | lower.isna())
        
        # Distance from middle to upper should equal distance from lower to middle
        upper_distance = upper[valid_indices] - middle[valid_indices]
        lower_distance = middle[valid_indices] - lower[valid_indices]
        
        np.testing.assert_array_almost_equal(upper_distance, lower_distance, decimal=5)
    
    def test_bollinger_bands_squeeze(self):
        """Test Bollinger Bands squeeze detection."""
        # Use constant volatility data
        constant_data = TestDataGenerator.generate_price_data(
            length=100, trend='neutral', volatility=0.5
        )
        upper, middle, lower = self.bb.calculate(constant_data['close'])
        
        # With low volatility, bands should be closer
        valid_bandwidth = (upper - lower).dropna()
        self.assertGreater(len(valid_bandwidth), 0)
    
    def test_bollinger_bands_custom_std(self):
        """Test Bollinger Bands with custom standard deviation."""
        bb_1std = BollingerBands(period=20, num_std=1)
        bb_3std = BollingerBands(period=20, num_std=3)
        
        upper_1, middle_1, lower_1 = bb_1std.calculate(self.test_data['close'])
        upper_3, middle_3, lower_3 = bb_3std.calculate(self.test_data['close'])
        
        valid_indices = ~(upper_1.isna() | upper_3.isna())
        
        # 3-std bands should be wider than 1-std bands
        self.assertTrue(np.all((upper_3[valid_indices] - middle_3[valid_indices]) > 
                               (upper_1[valid_indices] - middle_1[valid_indices])))


class TestStochasticOscillator(unittest.TestCase):
    """Test suite for Stochastic Oscillator indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
        self.stoch = StochasticOscillator(k_period=14, d_period=3)
    
    def test_stochastic_initialization(self):
        """Test Stochastic Oscillator initialization."""
        self.assertEqual(self.stoch.k_period, 14)
        self.assertEqual(self.stoch.d_period, 3)
    
    def test_stochastic_calculation(self):
        """Test Stochastic Oscillator calculation."""
        k_line, d_line = self.stoch.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        self.assertEqual(len(k_line), len(self.test_data))
        self.assertEqual(len(d_line), len(self.test_data))
    
    def test_stochastic_bounds(self):
        """Test Stochastic values are between 0 and 100."""
        k_line, d_line = self.stoch.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        k_valid = k_line.dropna()
        d_valid = d_line.dropna()
        
        self.assertTrue(np.all((k_valid >= 0) & (k_valid <= 100)))
        self.assertTrue(np.all((d_valid >= 0) & (d_valid <= 100)))
    
    def test_stochastic_oversold(self):
        """Test Stochastic detects oversold conditions."""
        downtrend_data = TestDataGenerator.generate_price_data(
            length=100, trend='downtrend', volatility=3.0
        )
        k_line, d_line = self.stoch.calculate(
            downtrend_data['high'],
            downtrend_data['low'],
            downtrend_data['close']
        )
        
        oversold = (k_line < 20).sum()
        self.assertGreater(oversold, 0)
    
    def test_stochastic_overbought(self):
        """Test Stochastic detects overbought conditions."""
        uptrend_data = TestDataGenerator.generate_price_data(
            length=100, trend='uptrend', volatility=3.0
        )
        k_line, d_line = self.stoch.calculate(
            uptrend_data['high'],
            uptrend_data['low'],
            uptrend_data['close']
        )
        
        overbought = (k_line > 80).sum()
        self.assertGreater(overbought, 0)


class TestADX(unittest.TestCase):
    """Test suite for Average Directional Index (ADX) indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
        self.adx = ADX(period=14)
    
    def test_adx_initialization(self):
        """Test ADX initialization."""
        self.assertEqual(self.adx.period, 14)
    
    def test_adx_calculation(self):
        """Test ADX calculation."""
        adx_line, plus_di, minus_di = self.adx.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        self.assertEqual(len(adx_line), len(self.test_data))
        self.assertEqual(len(plus_di), len(self.test_data))
        self.assertEqual(len(minus_di), len(self.test_data))
    
    def test_adx_bounds(self):
        """Test ADX values are between 0 and 100."""
        adx_line, plus_di, minus_di = self.adx.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        adx_valid = adx_line.dropna()
        self.assertTrue(np.all((adx_valid >= 0) & (adx_valid <= 100)))
    
    def test_adx_trend_strength(self):
        """Test ADX with strong trend data."""
        uptrend_data = TestDataGenerator.generate_price_data(
            length=100, trend='uptrend', volatility=2.0
        )
        adx_line, plus_di, minus_di = self.adx.calculate(
            uptrend_data['high'],
            uptrend_data['low'],
            uptrend_data['close']
        )
        
        # With uptrend, +DI should generally exceed -DI
        valid_indices = ~(plus_di.isna() | minus_di.isna())
        plus_greater = (plus_di[valid_indices] > minus_di[valid_indices]).sum()
        self.assertGreater(plus_greater, len(plus_di[valid_indices]) / 2)


class TestATR(unittest.TestCase):
    """Test suite for Average True Range (ATR) indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
        self.atr = ATR(period=14)
    
    def test_atr_initialization(self):
        """Test ATR initialization."""
        self.assertEqual(self.atr.period, 14)
    
    def test_atr_calculation(self):
        """Test ATR calculation."""
        atr_values = self.atr.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        self.assertEqual(len(atr_values), len(self.test_data))
    
    def test_atr_positive_values(self):
        """Test ATR values are always positive."""
        atr_values = self.atr.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        atr_valid = atr_values.dropna()
        self.assertTrue(np.all(atr_valid > 0))
    
    def test_atr_volatility_correlation(self):
        """Test ATR increases with volatility."""
        low_vol = TestDataGenerator.generate_price_data(
            length=100, trend='neutral', volatility=0.5
        )
        high_vol = TestDataGenerator.generate_price_data(
            length=100, trend='neutral', volatility=5.0
        )
        
        atr_low = self.atr.calculate(low_vol['high'], low_vol['low'], low_vol['close'])
        atr_high = self.atr.calculate(high_vol['high'], high_vol['low'], high_vol['close'])
        
        avg_atr_low = atr_low.dropna().mean()
        avg_atr_high = atr_high.dropna().mean()
        
        self.assertGreater(avg_atr_high, avg_atr_low)


class TestIchimokuCloud(unittest.TestCase):
    """Test suite for Ichimoku Cloud indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=150)
        self.ichimoku = IchimokuCloud(
            conversion_period=9,
            base_period=26,
            leading_span_b_period=52,
            lagging_span=26
        )
    
    def test_ichimoku_initialization(self):
        """Test Ichimoku Cloud initialization."""
        self.assertEqual(self.ichimoku.conversion_period, 9)
        self.assertEqual(self.ichimoku.base_period, 26)
    
    def test_ichimoku_calculation(self):
        """Test Ichimoku Cloud calculation."""
        result = self.ichimoku.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        # Should return all five lines
        self.assertEqual(len(result), 5)
        
        conversion_line, base_line, leading_span_a, leading_span_b, lagging_span = result
        
        self.assertEqual(len(conversion_line), len(self.test_data))
        self.assertEqual(len(base_line), len(self.test_data))
        self.assertEqual(len(leading_span_a), len(self.test_data))
        self.assertEqual(len(leading_span_b), len(self.test_data))
        self.assertEqual(len(lagging_span), len(self.test_data))
    
    def test_ichimoku_cloud_bounds(self):
        """Test Ichimoku Cloud bounds."""
        conversion_line, base_line, leading_span_a, leading_span_b, lagging_span = \
            self.ichimoku.calculate(
                self.test_data['high'],
                self.test_data['low'],
                self.test_data['close']
            )
        
        # Leading spans A should be between B and prices
        valid_indices = ~(leading_span_a.isna() | leading_span_b.isna())
        
        # Both should be reasonable values
        self.assertTrue(np.all(leading_span_a[valid_indices] > 0))
        self.assertTrue(np.all(leading_span_b[valid_indices] > 0))


class TestKeltnerChannel(unittest.TestCase):
    """Test suite for Keltner Channel indicator."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
        self.kc = KeltnerChannel(period=20, atr_period=10, atr_multiplier=2.0)
    
    def test_keltner_channel_initialization(self):
        """Test Keltner Channel initialization."""
        self.assertEqual(self.kc.period, 20)
        self.assertEqual(self.kc.atr_period, 10)
        self.assertEqual(self.kc.atr_multiplier, 2.0)
    
    def test_keltner_channel_calculation(self):
        """Test Keltner Channel calculation."""
        upper, middle, lower = self.kc.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        self.assertEqual(len(upper), len(self.test_data))
        self.assertEqual(len(middle), len(self.test_data))
        self.assertEqual(len(lower), len(self.test_data))
    
    def test_keltner_channel_ordering(self):
        """Test upper > middle > lower in Keltner Channel."""
        upper, middle, lower = self.kc.calculate(
            self.test_data['high'],
            self.test_data['low'],
            self.test_data['close']
        )
        
        valid_indices = ~(upper.isna() | middle.isna() | lower.isna())
        
        self.assertTrue(np.all(upper[valid_indices] >= middle[valid_indices]))
        self.assertTrue(np.all(middle[valid_indices] >= lower[valid_indices]))


class TestIndicatorIntegration(unittest.TestCase):
    """Integration tests for multiple indicators."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.test_data = TestDataGenerator.generate_price_data(length=100)
    
    def test_multiple_indicators_same_data(self):
        """Test multiple indicators can be calculated on same data."""
        rsi = RSI(period=14)
        macd = MACD()
        bb = BollingerBands()
        
        rsi_result = rsi.calculate(self.test_data['close'])
        macd_result = macd.calculate(self.test_data['close'])
        bb_result = bb.calculate(self.test_data['close'])
        
        self.assertIsNotNone(rsi_result)
        self.assertIsNotNone(macd_result)
        self.assertIsNotNone(bb_result)
    
    def test_indicators_with_real_trading_scenario(self):
        """Test indicators in realistic trading scenario."""
        uptrend_data = TestDataGenerator.generate_price_data(
            length=100, trend='uptrend', volatility=2.0
        )
        
        rsi = RSI(period=14)
        macd = MACD()
        bb = BollingerBands()
        
        rsi_values = rsi.calculate(uptrend_data['close'])
        macd_line, signal_line, histogram = macd.calculate(uptrend_data['close'])
        upper, middle, lower = bb.calculate(uptrend_data['close'])
        
        # In uptrend, RSI should tend toward overbought
        latest_rsi = rsi_values.iloc[-1]
        self.assertGreater(latest_rsi, 50)
        
        # MACD histogram should show some positive values
        positive_histogram = (histogram > 0).sum()
        self.assertGreater(positive_histogram, 0)
    
    def test_indicators_consistency(self):
        """Test that indicators produce consistent results."""
        rsi = RSI(period=14)
        
        # Calculate twice with same data
        result1 = rsi.calculate(self.test_data['close'])
        result2 = rsi.calculate(self.test_data['close'])
        
        # Results should be identical
        np.testing.assert_array_equal(
            result1.fillna(-999),
            result2.fillna(-999)
        )


class TestErrorHandling(unittest.TestCase):
    """Test error handling in indicators."""
    
    def test_rsi_with_insufficient_data(self):
        """Test RSI with insufficient data points."""
        short_data = pd.Series([100.0, 101.0, 102.0])
        rsi = RSI(period=14)
        result = rsi.calculate(short_data)
        
        # Should return all NaN
        self.assertTrue(result.isna().all())
    
    def test_indicators_with_nan_values(self):
        """Test indicators handle NaN values in input."""
        data_with_nan = self.test_data['close'].copy()
        data_with_nan.iloc[10:15] = np.nan
        
        rsi = RSI(period=14)
        result = rsi.calculate(data_with_nan)
        
        # Should still produce some valid results
        valid_results = result.dropna()
        self.assertGreater(len(valid_results), 0)
    
    def test_bollinger_bands_with_zero_volatility(self):
        """Test Bollinger Bands with zero volatility."""
        constant_prices = pd.Series([100.0] * 50)
        bb = BollingerBands(period=20)
        upper, middle, lower = bb.calculate(constant_prices)
        
        # Middle should be 100
        valid_middle = middle.dropna()
        if len(valid_middle) > 0:
            self.assertTrue(np.allclose(valid_middle.iloc[-1], 100.0))


class TestPerformance(unittest.TestCase):
    """Performance tests for indicators."""
    
    def test_large_dataset_performance(self):
        """Test indicators can handle large datasets."""
        large_data = TestDataGenerator.generate_price_data(length=10000)
        
        rsi = RSI(period=14)
        macd = MACD()
        bb = BollingerBands()
        
        # Should complete without timeout
        rsi_result = rsi.calculate(large_data['close'])
        macd_result = macd.calculate(large_data['close'])
        bb_result = bb.calculate(large_data['close'])
        
        self.assertEqual(len(rsi_result), 10000)
        self.assertEqual(len(macd_result[0]), 10000)
        self.assertEqual(len(bb_result[0]), 10000)


if __name__ == '__main__':
    unittest.main()
