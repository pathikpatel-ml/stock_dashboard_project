"""
Advanced Trading Signal Generator with Consensus-Based Approach

This module implements a sophisticated trading signal generation system that combines
multiple technical indicators (RSI, MACD, Bollinger Bands, Stochastic) using a 
consensus-based approach. Multiple indicators must agree before generating buy/sell 
signals, with confidence scoring and comprehensive signal history tracking.

Author: Stock Dashboard Project
Date: 2026-01-01
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Enumeration for signal types"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"


class IndicatorSignal(Enum):
    """Enumeration for individual indicator signals"""
    BULLISH = 1
    NEUTRAL = 0
    BEARISH = -1


@dataclass
class IndicatorReading:
    """Data class for storing individual indicator readings"""
    name: str
    value: float
    signal: IndicatorSignal
    strength: float  # 0-1 range indicating signal strength
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Convert to dictionary representation"""
        return {
            'name': self.name,
            'value': self.value,
            'signal': self.signal.name,
            'strength': self.strength,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class TradingSignal:
    """Data class for complete trading signals"""
    timestamp: datetime
    signal_type: SignalType
    confidence_score: float  # 0-100
    agreement_ratio: float  # Percentage of indicators agreeing (0-100)
    bullish_count: int
    bearish_count: int
    neutral_count: int
    indicator_readings: List[IndicatorReading] = field(default_factory=list)
    reasoning: str = ""
    price: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary representation"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'signal_type': self.signal_type.name,
            'confidence_score': self.confidence_score,
            'agreement_ratio': self.agreement_ratio,
            'bullish_count': self.bullish_count,
            'bearish_count': self.bearish_count,
            'neutral_count': self.neutral_count,
            'indicator_readings': [ir.to_dict() for ir in self.indicator_readings],
            'reasoning': self.reasoning,
            'price': self.price
        }


class TechnicalIndicators:
    """Class for calculating technical indicators"""
    
    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI)
        
        Args:
            prices: Series of price data
            period: Period for RSI calculation (default: 14)
            
        Returns:
            Series of RSI values
        """
        if len(prices) < period + 1:
            return pd.Series(index=prices.index, dtype=float)
        
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, 
                      signal_period: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            prices: Series of price data
            fast: Fast EMA period (default: 12)
            slow: Slow EMA period (default: 26)
            signal_period: Signal line period (default: 9)
            
        Returns:
            Tuple of (MACD line, Signal line, Histogram)
        """
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal_period).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_bollinger_bands(prices: pd.Series, period: int = 20, 
                                 std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands
        
        Args:
            prices: Series of price data
            period: Period for moving average (default: 20)
            std_dev: Number of standard deviations (default: 2.0)
            
        Returns:
            Tuple of (Upper Band, Middle Band, Lower Band)
        """
        middle_band = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = middle_band + (std_dev * std)
        lower_band = middle_band - (std_dev * std)
        
        return upper_band, middle_band, lower_band
    
    @staticmethod
    def calculate_stochastic(high: pd.Series, low: pd.Series, close: pd.Series, 
                            period: int = 14, smooth_k: int = 3, 
                            smooth_d: int = 3) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Stochastic Oscillator
        
        Args:
            high: Series of high prices
            low: Series of low prices
            close: Series of closing prices
            period: Period for calculation (default: 14)
            smooth_k: Smoothing period for %K (default: 3)
            smooth_d: Smoothing period for %D (default: 3)
            
        Returns:
            Tuple of (%K, %D)
        """
        lowest_low = low.rolling(window=period).min()
        highest_high = high.rolling(window=period).max()
        
        k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        k_percent_smooth = k_percent.rolling(window=smooth_k).mean()
        d_percent = k_percent_smooth.rolling(window=smooth_d).mean()
        
        return k_percent_smooth, d_percent


class SignalGenerator:
    """Main signal generation engine using consensus-based approach"""
    
    def __init__(self, min_agreement_ratio: float = 0.60, 
                 confidence_threshold: float = 50.0):
        """
        Initialize the Signal Generator
        
        Args:
            min_agreement_ratio: Minimum ratio of indicators that must agree (0-1)
            confidence_threshold: Minimum confidence score for valid signals (0-100)
        """
        self.min_agreement_ratio = min_agreement_ratio
        self.confidence_threshold = confidence_threshold
        self.signal_history: List[TradingSignal] = []
        self.indicators = TechnicalIndicators()
        logger.info(f"SignalGenerator initialized with min_agreement_ratio={min_agreement_ratio}, "
                   f"confidence_threshold={confidence_threshold}")
    
    def analyze_rsi(self, rsi_value: float, overbought: float = 70.0, 
                   oversold: float = 30.0) -> Tuple[IndicatorSignal, float]:
        """
        Analyze RSI for trading signals
        
        Args:
            rsi_value: Current RSI value
            overbought: Overbought threshold (default: 70)
            oversold: Oversold threshold (default: 30)
            
        Returns:
            Tuple of (Signal, Strength 0-1)
        """
        if pd.isna(rsi_value):
            return IndicatorSignal.NEUTRAL, 0.0
        
        if rsi_value > overbought:
            strength = min((rsi_value - overbought) / (100 - overbought), 1.0)
            return IndicatorSignal.BEARISH, strength
        elif rsi_value < oversold:
            strength = (oversold - rsi_value) / oversold
            return IndicatorSignal.BULLISH, strength
        else:
            return IndicatorSignal.NEUTRAL, 0.0
    
    def analyze_macd(self, macd_line: float, signal_line: float, 
                    histogram: float) -> Tuple[IndicatorSignal, float]:
        """
        Analyze MACD for trading signals
        
        Args:
            macd_line: Current MACD line value
            signal_line: Current signal line value
            histogram: Current histogram value
            
        Returns:
            Tuple of (Signal, Strength 0-1)
        """
        if pd.isna(macd_line) or pd.isna(signal_line):
            return IndicatorSignal.NEUTRAL, 0.0
        
        if histogram > 0 and macd_line > signal_line:
            strength = min(abs(histogram), 1.0)
            return IndicatorSignal.BULLISH, strength
        elif histogram < 0 and macd_line < signal_line:
            strength = min(abs(histogram), 1.0)
            return IndicatorSignal.BEARISH, strength
        else:
            return IndicatorSignal.NEUTRAL, 0.0
    
    def analyze_bollinger_bands(self, price: float, upper_band: float, 
                               middle_band: float, lower_band: float) -> Tuple[IndicatorSignal, float]:
        """
        Analyze Bollinger Bands for trading signals
        
        Args:
            price: Current price
            upper_band: Upper band value
            middle_band: Middle band value
            lower_band: Lower band value
            
        Returns:
            Tuple of (Signal, Strength 0-1)
        """
        if pd.isna(price) or pd.isna(upper_band) or pd.isna(lower_band):
            return IndicatorSignal.NEUTRAL, 0.0
        
        band_width = upper_band - lower_band
        if band_width == 0:
            return IndicatorSignal.NEUTRAL, 0.0
        
        position = (price - lower_band) / band_width
        
        if price > upper_band:
            strength = min((price - upper_band) / (band_width * 0.1) if band_width * 0.1 > 0 else 1.0, 1.0)
            return IndicatorSignal.BEARISH, strength
        elif price < lower_band:
            strength = min((lower_band - price) / (band_width * 0.1) if band_width * 0.1 > 0 else 1.0, 1.0)
            return IndicatorSignal.BULLISH, strength
        elif position > 0.7:
            return IndicatorSignal.BEARISH, 0.4
        elif position < 0.3:
            return IndicatorSignal.BULLISH, 0.4
        else:
            return IndicatorSignal.NEUTRAL, 0.0
    
    def analyze_stochastic(self, k_percent: float, d_percent: float, 
                          overbought: float = 80.0, oversold: float = 20.0) -> Tuple[IndicatorSignal, float]:
        """
        Analyze Stochastic Oscillator for trading signals
        
        Args:
            k_percent: Current %K value
            d_percent: Current %D value
            overbought: Overbought threshold (default: 80)
            oversold: Oversold threshold (default: 20)
            
        Returns:
            Tuple of (Signal, Strength 0-1)
        """
        if pd.isna(k_percent) or pd.isna(d_percent):
            return IndicatorSignal.NEUTRAL, 0.0
        
        if k_percent > overbought:
            strength = (k_percent - overbought) / (100 - overbought)
            return IndicatorSignal.BEARISH, strength
        elif k_percent < oversold:
            strength = (oversold - k_percent) / oversold
            return IndicatorSignal.BULLISH, strength
        elif k_percent > d_percent:
            strength = min((k_percent - d_percent) / 100, 0.6)
            return IndicatorSignal.BULLISH, strength
        elif k_percent < d_percent:
            strength = min((d_percent - k_percent) / 100, 0.6)
            return IndicatorSignal.BEARISH, strength
        else:
            return IndicatorSignal.NEUTRAL, 0.0
    
    def generate_signal(self, price_data: pd.DataFrame, current_price: float,
                       use_high_low: bool = True) -> Optional[TradingSignal]:
        """
        Generate a consensus-based trading signal
        
        Args:
            price_data: DataFrame with OHLC data (columns: Open, High, Low, Close)
            current_price: Current price for analysis
            use_high_low: Whether to use high/low for Stochastic (default: True)
            
        Returns:
            TradingSignal object or None if insufficient data
        """
        if len(price_data) < 30:
            logger.warning("Insufficient data for signal generation")
            return None
        
        try:
            closes = price_data['Close']
            
            # Calculate all indicators
            rsi = self.indicators.calculate_rsi(closes)
            macd_line, signal_line, histogram = self.indicators.calculate_macd(closes)
            upper_band, middle_band, lower_band = self.indicators.calculate_bollinger_bands(closes)
            
            # Collect indicator readings
            indicator_readings = []
            signal_votes = []
            strengths = []
            
            # RSI Analysis
            rsi_signal, rsi_strength = self.analyze_rsi(rsi.iloc[-1])
            indicator_readings.append(IndicatorReading(
                name="RSI(14)",
                value=rsi.iloc[-1],
                signal=rsi_signal,
                strength=rsi_strength
            ))
            signal_votes.append(rsi_signal.value)
            strengths.append(rsi_strength)
            
            # MACD Analysis
            macd_signal, macd_strength = self.analyze_macd(
                macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
            )
            indicator_readings.append(IndicatorReading(
                name="MACD",
                value=macd_line.iloc[-1],
                signal=macd_signal,
                strength=macd_strength
            ))
            signal_votes.append(macd_signal.value)
            strengths.append(macd_strength)
            
            # Bollinger Bands Analysis
            bb_signal, bb_strength = self.analyze_bollinger_bands(
                current_price, upper_band.iloc[-1], middle_band.iloc[-1], lower_band.iloc[-1]
            )
            indicator_readings.append(IndicatorReading(
                name="Bollinger Bands(20)",
                value=current_price,
                signal=bb_signal,
                strength=bb_strength
            ))
            signal_votes.append(bb_signal.value)
            strengths.append(bb_strength)
            
            # Stochastic Analysis
            if use_high_low and 'High' in price_data.columns and 'Low' in price_data.columns:
                k_percent, d_percent = self.indicators.calculate_stochastic(
                    price_data['High'], price_data['Low'], closes
                )
                stoch_signal, stoch_strength = self.analyze_stochastic(
                    k_percent.iloc[-1], d_percent.iloc[-1]
                )
            else:
                stoch_signal = IndicatorSignal.NEUTRAL
                stoch_strength = 0.0
            
            indicator_readings.append(IndicatorReading(
                name="Stochastic(14,3,3)",
                value=k_percent.iloc[-1] if use_high_low else 0.0,
                signal=stoch_signal,
                strength=stoch_strength
            ))
            signal_votes.append(stoch_signal.value)
            strengths.append(stoch_strength)
            
            # Calculate consensus
            bullish_count = sum(1 for v in signal_votes if v > 0)
            bearish_count = sum(1 for v in signal_votes if v < 0)
            neutral_count = sum(1 for v in signal_votes if v == 0)
            total_indicators = len(signal_votes)
            
            # Determine signal type based on majority
            agreement_ratio = max(bullish_count, bearish_count) / total_indicators
            
            if agreement_ratio < self.min_agreement_ratio:
                signal_type = SignalType.HOLD
            elif bullish_count > bearish_count:
                signal_type = SignalType.BUY
            elif bearish_count > bullish_count:
                signal_type = SignalType.SELL
            else:
                signal_type = SignalType.NEUTRAL
            
            # Calculate confidence score
            avg_strength = np.mean(strengths)
            confidence_score = (agreement_ratio * 100) * (0.7) + (avg_strength * 100) * (0.3)
            confidence_score = min(100.0, max(0.0, confidence_score))
            
            # Generate reasoning
            reasoning = self._generate_reasoning(
                signal_type, bullish_count, bearish_count, neutral_count,
                agreement_ratio, confidence_score
            )
            
            # Create signal object
            signal = TradingSignal(
                timestamp=datetime.utcnow(),
                signal_type=signal_type,
                confidence_score=confidence_score,
                agreement_ratio=agreement_ratio * 100,
                bullish_count=bullish_count,
                bearish_count=bearish_count,
                neutral_count=neutral_count,
                indicator_readings=indicator_readings,
                reasoning=reasoning,
                price=current_price
            )
            
            # Add to history
            self.signal_history.append(signal)
            logger.info(f"Signal generated: {signal_type.name} (Confidence: {confidence_score:.2f}%)")
            
            return signal
        
        except Exception as e:
            logger.error(f"Error generating signal: {str(e)}")
            return None
    
    def _generate_reasoning(self, signal_type: SignalType, bullish_count: int,
                           bearish_count: int, neutral_count: int,
                           agreement_ratio: float, confidence_score: float) -> str:
        """Generate human-readable reasoning for the signal"""
        consensus_pct = agreement_ratio * 100
        
        reasoning = f"Signal: {signal_type.name} | "
        reasoning += f"Consensus: {consensus_pct:.1f}% ({bullish_count}B/{bearish_count}S/{neutral_count}N) | "
        reasoning += f"Confidence: {confidence_score:.1f}%"
        
        if confidence_score < self.confidence_threshold:
            reasoning += " [Low confidence - Exercise caution]"
        
        return reasoning
    
    def get_signal_history(self, limit: Optional[int] = None) -> List[TradingSignal]:
        """
        Get signal history
        
        Args:
            limit: Maximum number of recent signals to return
            
        Returns:
            List of TradingSignal objects
        """
        if limit is None:
            return self.signal_history
        return self.signal_history[-limit:]
    
    def get_signal_statistics(self) -> Dict:
        """
        Calculate statistics from signal history
        
        Returns:
            Dictionary containing signal statistics
        """
        if not self.signal_history:
            return {
                'total_signals': 0,
                'buy_signals': 0,
                'sell_signals': 0,
                'hold_signals': 0,
                'avg_confidence': 0.0,
                'high_confidence_signals': 0
            }
        
        buy_signals = sum(1 for s in self.signal_history if s.signal_type == SignalType.BUY)
        sell_signals = sum(1 for s in self.signal_history if s.signal_type == SignalType.SELL)
        hold_signals = sum(1 for s in self.signal_history if s.signal_type == SignalType.HOLD)
        avg_confidence = np.mean([s.confidence_score for s in self.signal_history])
        high_confidence = sum(1 for s in self.signal_history if s.confidence_score >= self.confidence_threshold)
        
        return {
            'total_signals': len(self.signal_history),
            'buy_signals': buy_signals,
            'sell_signals': sell_signals,
            'hold_signals': hold_signals,
            'neutral_signals': len(self.signal_history) - (buy_signals + sell_signals + hold_signals),
            'avg_confidence': avg_confidence,
            'high_confidence_signals': high_confidence,
            'high_confidence_percentage': (high_confidence / len(self.signal_history) * 100) if self.signal_history else 0.0
        }
    
    def export_signal_history(self, filepath: str, format: str = 'csv') -> bool:
        """
        Export signal history to file
        
        Args:
            filepath: Path to export file
            format: Export format ('csv' or 'json')
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if format == 'json':
                import json
                with open(filepath, 'w') as f:
                    json.dump(
                        [s.to_dict() for s in self.signal_history],
                        f,
                        indent=2,
                        default=str
                    )
            elif format == 'csv':
                data = []
                for signal in self.signal_history:
                    data.append({
                        'timestamp': signal.timestamp.isoformat(),
                        'signal_type': signal.signal_type.name,
                        'confidence_score': signal.confidence_score,
                        'agreement_ratio': signal.agreement_ratio,
                        'bullish_count': signal.bullish_count,
                        'bearish_count': signal.bearish_count,
                        'neutral_count': signal.neutral_count,
                        'price': signal.price,
                        'reasoning': signal.reasoning
                    })
                df = pd.DataFrame(data)
                df.to_csv(filepath, index=False)
            else:
                logger.error(f"Unsupported format: {format}")
                return False
            
            logger.info(f"Signal history exported to {filepath}")
            return True
        
        except Exception as e:
            logger.error(f"Error exporting signal history: {str(e)}")
            return False


# Example usage and testing
if __name__ == "__main__":
    # Create sample OHLC data
    dates = pd.date_range(start='2025-01-01', periods=100, freq='D')
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(100) * 2)
    
    sample_data = pd.DataFrame({
        'Date': dates,
        'Open': prices + np.random.randn(100),
        'High': prices + np.random.rand(100) * 2,
        'Low': prices - np.random.rand(100) * 2,
        'Close': prices
    })
    
    # Initialize signal generator
    generator = SignalGenerator(min_agreement_ratio=0.60, confidence_threshold=50.0)
    
    # Generate signal
    signal = generator.generate_signal(sample_data, current_price=prices[-1])
    
    if signal:
        print("\n" + "="*70)
        print("TRADING SIGNAL GENERATED")
        print("="*70)
        print(f"Signal Type: {signal.signal_type.name}")
        print(f"Confidence Score: {signal.confidence_score:.2f}%")
        print(f"Agreement Ratio: {signal.agreement_ratio:.2f}%")
        print(f"Bullish Indicators: {signal.bullish_count}")
        print(f"Bearish Indicators: {signal.bearish_count}")
        print(f"Neutral Indicators: {signal.neutral_count}")
        print(f"Price: ${signal.price:.2f}")
        print(f"\nReasoning: {signal.reasoning}")
        print("\nIndicator Details:")
        for reading in signal.indicator_readings:
            print(f"  {reading.name}: {reading.value:.4f} ({reading.signal.name}) - Strength: {reading.strength:.2f}")
        print("="*70)
        
        # Get statistics
        stats = generator.get_signal_statistics()
        print("\nSignal Statistics:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
