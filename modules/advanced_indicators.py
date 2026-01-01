"""
Advanced Technical Indicators Module

This module provides efficient implementations of advanced technical indicators
including RSI, MACD, Bollinger Bands, and Stochastic Oscillator with caching
and optimized calculations for stock analysis.

Author: pathikpatel-ml
Date: 2026-01-01
"""

import numpy as np
import pandas as pd
from functools import lru_cache
from typing import Tuple, Dict, List, Optional
import hashlib


class IndicatorCache:
    """
    Caching system for technical indicator calculations to avoid redundant computations.
    Uses hash-based cache keys for efficient lookup.
    """
    
    def __init__(self, max_cache_size: int = 128):
        """
        Initialize the cache system.
        
        Args:
            max_cache_size: Maximum number of cached calculations to store
        """
        self.cache = {}
        self.max_cache_size = max_cache_size
        self.access_count = {}
    
    def _generate_key(self, data: np.ndarray, params: Dict) -> str:
        """
        Generate a hash key for cache lookup based on data and parameters.
        
        Args:
            data: Input data array
            params: Dictionary of parameters
            
        Returns:
            Hash key string
        """
        data_hash = hashlib.md5(data.tobytes()).hexdigest()
        params_str = '|'.join(f"{k}:{v}" for k, v in sorted(params.items()))
        return f"{data_hash}:{params_str}"
    
    def get(self, data: np.ndarray, params: Dict):
        """Retrieve cached result if available."""
        key = self._generate_key(data, params)
        if key in self.cache:
            self.access_count[key] = self.access_count.get(key, 0) + 1
            return self.cache[key]
        return None
    
    def put(self, data: np.ndarray, params: Dict, result):
        """Store result in cache, removing least accessed item if cache is full."""
        key = self._generate_key(data, params)
        
        if len(self.cache) >= self.max_cache_size:
            # Remove least accessed item
            least_accessed = min(self.access_count, key=self.access_count.get)
            del self.cache[least_accessed]
            del self.access_count[least_accessed]
        
        self.cache[key] = result
        self.access_count[key] = 1
    
    def clear(self):
        """Clear all cached data."""
        self.cache.clear()
        self.access_count.clear()


class RSI:
    """
    Relative Strength Index (RSI) Calculator
    
    RSI measures the magnitude of recent price changes to evaluate
    overbought or oversold conditions.
    """
    
    def __init__(self, period: int = 14, cache_enabled: bool = True):
        """
        Initialize RSI calculator.
        
        Args:
            period: Period for RSI calculation (default: 14)
            cache_enabled: Enable result caching
        """
        self.period = period
        self.cache = IndicatorCache() if cache_enabled else None
    
    def calculate(self, prices: np.ndarray) -> np.ndarray:
        """
        Calculate RSI values efficiently.
        
        Args:
            prices: Array of price data
            
        Returns:
            Array of RSI values (0-100)
        """
        if len(prices) < self.period + 1:
            raise ValueError(f"Need at least {self.period + 1} data points")
        
        # Check cache
        if self.cache:
            params = {'period': self.period}
            cached_result = self.cache.get(prices, params)
            if cached_result is not None:
                return cached_result
        
        # Calculate price changes
        deltas = np.diff(prices)
        seed = deltas[:self.period + 1]
        
        # Separate gains and losses
        up = seed[seed >= 0].sum() / self.period
        down = -seed[seed < 0].sum() / self.period
        rs = up / down if down != 0 else 0
        rsi = np.zeros_like(prices)
        rsi[:self.period] = 100. - 100. / (1. + rs)
        
        # Smooth calculation using EMA method
        for i in range(self.period, len(prices)):
            delta = deltas[i - 1]
            if delta > 0:
                upval = delta
                downval = 0.
            else:
                upval = 0.
                downval = -delta
            
            up = (up * (self.period - 1) + upval) / self.period
            down = (down * (self.period - 1) + downval) / self.period
            
            rs = up / down if down != 0 else 0
            rsi[i] = 100. - 100. / (1. + rs)
        
        # Cache result
        if self.cache:
            params = {'period': self.period}
            self.cache.put(prices, params, rsi)
        
        return rsi


class MACD:
    """
    Moving Average Convergence Divergence (MACD) Calculator
    
    MACD is a momentum indicator that shows the relationship between
    two moving averages of a security's price.
    """
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, 
                 signal_period: int = 9, cache_enabled: bool = True):
        """
        Initialize MACD calculator.
        
        Args:
            fast_period: Period for fast EMA (default: 12)
            slow_period: Period for slow EMA (default: 26)
            signal_period: Period for signal line EMA (default: 9)
            cache_enabled: Enable result caching
        """
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.cache = IndicatorCache() if cache_enabled else None
    
    @staticmethod
    def _ema(prices: np.ndarray, period: int) -> np.ndarray:
        """Calculate Exponential Moving Average efficiently."""
        ema = np.zeros_like(prices)
        multiplier = 2.0 / (period + 1.0)
        ema[0] = prices[0]
        
        for i in range(1, len(prices)):
            ema[i] = prices[i] * multiplier + ema[i - 1] * (1 - multiplier)
        
        return ema
    
    def calculate(self, prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate MACD, Signal line, and Histogram.
        
        Args:
            prices: Array of price data
            
        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        if len(prices) < self.slow_period:
            raise ValueError(f"Need at least {self.slow_period} data points")
        
        # Check cache
        if self.cache:
            params = {'fast': self.fast_period, 'slow': self.slow_period, 
                     'signal': self.signal_period}
            cached_result = self.cache.get(prices, params)
            if cached_result is not None:
                return cached_result
        
        # Calculate EMAs
        fast_ema = self._ema(prices, self.fast_period)
        slow_ema = self._ema(prices, self.slow_period)
        
        # Calculate MACD line
        macd_line = fast_ema - slow_ema
        
        # Calculate signal line
        signal_line = self._ema(macd_line, self.signal_period)
        
        # Calculate histogram
        histogram = macd_line - signal_line
        
        result = (macd_line, signal_line, histogram)
        
        # Cache result
        if self.cache:
            params = {'fast': self.fast_period, 'slow': self.slow_period, 
                     'signal': self.signal_period}
            self.cache.put(prices, params, result)
        
        return result


class BollingerBands:
    """
    Bollinger Bands Calculator
    
    Bollinger Bands consist of a moving average and two standard deviation bands,
    used to measure volatility and identify overbought/oversold conditions.
    """
    
    def __init__(self, period: int = 20, std_dev: float = 2.0, cache_enabled: bool = True):
        """
        Initialize Bollinger Bands calculator.
        
        Args:
            period: Period for moving average (default: 20)
            std_dev: Number of standard deviations (default: 2.0)
            cache_enabled: Enable result caching
        """
        self.period = period
        self.std_dev = std_dev
        self.cache = IndicatorCache() if cache_enabled else None
    
    def calculate(self, prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate Bollinger Bands (upper band, middle band, lower band).
        
        Args:
            prices: Array of price data
            
        Returns:
            Tuple of (upper_band, middle_band, lower_band)
        """
        if len(prices) < self.period:
            raise ValueError(f"Need at least {self.period} data points")
        
        # Check cache
        if self.cache:
            params = {'period': self.period, 'std_dev': self.std_dev}
            cached_result = self.cache.get(prices, params)
            if cached_result is not None:
                return cached_result
        
        # Calculate moving average
        middle_band = np.zeros_like(prices)
        for i in range(self.period - 1, len(prices)):
            middle_band[i] = np.mean(prices[i - self.period + 1:i + 1])
        
        # Calculate standard deviation
        std_dev_band = np.zeros_like(prices)
        for i in range(self.period - 1, len(prices)):
            std_dev_band[i] = np.std(prices[i - self.period + 1:i + 1])
        
        # Calculate bands
        upper_band = middle_band + (self.std_dev * std_dev_band)
        lower_band = middle_band - (self.std_dev * std_dev_band)
        
        result = (upper_band, middle_band, lower_band)
        
        # Cache result
        if self.cache:
            params = {'period': self.period, 'std_dev': self.std_dev}
            self.cache.put(prices, params, result)
        
        return result


class StochasticOscillator:
    """
    Stochastic Oscillator Calculator
    
    The Stochastic Oscillator compares a price to a range over time,
    showing momentum and trend strength.
    """
    
    def __init__(self, period: int = 14, smoothing_period: int = 3, cache_enabled: bool = True):
        """
        Initialize Stochastic Oscillator calculator.
        
        Args:
            period: Period for high/low range (default: 14)
            smoothing_period: Period for smoothing (default: 3)
            cache_enabled: Enable result caching
        """
        self.period = period
        self.smoothing_period = smoothing_period
        self.cache = IndicatorCache() if cache_enabled else None
    
    def calculate(self, prices: np.ndarray, high_prices: Optional[np.ndarray] = None,
                  low_prices: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Stochastic Oscillator (%K and %D).
        
        Args:
            prices: Array of closing prices
            high_prices: Array of high prices (optional, uses prices if not provided)
            low_prices: Array of low prices (optional, uses prices if not provided)
            
        Returns:
            Tuple of (%K line, %D line)
        """
        if len(prices) < self.period:
            raise ValueError(f"Need at least {self.period} data points")
        
        # Use price as default for high/low if not provided
        high_prices = high_prices if high_prices is not None else prices
        low_prices = low_prices if low_prices is not None else prices
        
        # Check cache
        if self.cache:
            combined_data = np.concatenate([prices, high_prices, low_prices])
            params = {'period': self.period, 'smoothing': self.smoothing_period}
            cached_result = self.cache.get(combined_data, params)
            if cached_result is not None:
                return cached_result
        
        # Calculate %K
        k_percent = np.zeros_like(prices)
        for i in range(self.period - 1, len(prices)):
            lowest_low = np.min(low_prices[i - self.period + 1:i + 1])
            highest_high = np.max(high_prices[i - self.period + 1:i + 1])
            
            if highest_high - lowest_low != 0:
                k_percent[i] = 100 * (prices[i] - lowest_low) / (highest_high - lowest_low)
            else:
                k_percent[i] = 50  # Default to 50 if range is 0
        
        # Calculate %D (smoothed %K)
        d_percent = np.zeros_like(prices)
        for i in range(self.period + self.smoothing_period - 2, len(prices)):
            d_percent[i] = np.mean(k_percent[i - self.smoothing_period + 1:i + 1])
        
        result = (k_percent, d_percent)
        
        # Cache result
        if self.cache:
            combined_data = np.concatenate([prices, high_prices, low_prices])
            params = {'period': self.period, 'smoothing': self.smoothing_period}
            self.cache.put(combined_data, params, result)
        
        return result


class AdvancedIndicatorCalculator:
    """
    Unified calculator for all advanced technical indicators.
    Provides convenient methods to calculate multiple indicators at once.
    """
    
    def __init__(self, cache_enabled: bool = True):
        """
        Initialize the advanced indicator calculator.
        
        Args:
            cache_enabled: Enable caching for all indicators
        """
        self.rsi = RSI(cache_enabled=cache_enabled)
        self.macd = MACD(cache_enabled=cache_enabled)
        self.bollinger = BollingerBands(cache_enabled=cache_enabled)
        self.stochastic = StochasticOscillator(cache_enabled=cache_enabled)
    
    def calculate_all(self, prices: np.ndarray, high_prices: Optional[np.ndarray] = None,
                     low_prices: Optional[np.ndarray] = None) -> Dict:
        """
        Calculate all technical indicators at once.
        
        Args:
            prices: Array of closing prices
            high_prices: Array of high prices (optional)
            low_prices: Array of low prices (optional)
            
        Returns:
            Dictionary containing all calculated indicators
        """
        results = {}
        
        try:
            # Calculate RSI
            results['rsi'] = self.rsi.calculate(prices)
        except ValueError as e:
            results['rsi_error'] = str(e)
        
        try:
            # Calculate MACD
            macd_line, signal_line, histogram = self.macd.calculate(prices)
            results['macd_line'] = macd_line
            results['macd_signal'] = signal_line
            results['macd_histogram'] = histogram
        except ValueError as e:
            results['macd_error'] = str(e)
        
        try:
            # Calculate Bollinger Bands
            upper, middle, lower = self.bollinger.calculate(prices)
            results['bb_upper'] = upper
            results['bb_middle'] = middle
            results['bb_lower'] = lower
        except ValueError as e:
            results['bb_error'] = str(e)
        
        try:
            # Calculate Stochastic Oscillator
            k_percent, d_percent = self.stochastic.calculate(prices, high_prices, low_prices)
            results['stoch_k'] = k_percent
            results['stoch_d'] = d_percent
        except ValueError as e:
            results['stoch_error'] = str(e)
        
        return results
    
    def clear_cache(self):
        """Clear all cached calculations."""
        self.rsi.cache.clear() if self.rsi.cache else None
        self.macd.cache.clear() if self.macd.cache else None
        self.bollinger.cache.clear() if self.bollinger.cache else None
        self.stochastic.cache.clear() if self.stochastic.cache else None


# Utility functions for indicator analysis

def identify_signals(indicators: Dict) -> Dict[str, List[str]]:
    """
    Identify trading signals based on calculated indicators.
    
    Args:
        indicators: Dictionary of calculated indicators
        
    Returns:
        Dictionary containing identified signals
    """
    signals = {
        'rsi_signals': [],
        'macd_signals': [],
        'bb_signals': [],
        'stoch_signals': [],
        'combined_signals': []
    }
    
    # RSI signals (last value)
    if 'rsi' in indicators:
        rsi_val = indicators['rsi'][-1]
        if rsi_val > 70:
            signals['rsi_signals'].append('OVERBOUGHT')
        elif rsi_val < 30:
            signals['rsi_signals'].append('OVERSOLD')
    
    # MACD signals
    if 'macd_line' in indicators and 'macd_signal' in indicators:
        if indicators['macd_line'][-1] > indicators['macd_signal'][-1]:
            signals['macd_signals'].append('BULLISH_CROSSOVER')
        else:
            signals['macd_signals'].append('BEARISH_CROSSOVER')
    
    # Bollinger Bands signals
    if 'bb_upper' in indicators and 'bb_lower' in indicators:
        price = indicators.get('price', 0)
        if price > indicators['bb_upper'][-1]:
            signals['bb_signals'].append('PRICE_ABOVE_UPPER_BAND')
        elif price < indicators['bb_lower'][-1]:
            signals['bb_signals'].append('PRICE_BELOW_LOWER_BAND')
    
    # Stochastic Oscillator signals
    if 'stoch_k' in indicators:
        stoch_val = indicators['stoch_k'][-1]
        if stoch_val > 80:
            signals['stoch_signals'].append('OVERBOUGHT')
        elif stoch_val < 20:
            signals['stoch_signals'].append('OVERSOLD')
    
    return signals
