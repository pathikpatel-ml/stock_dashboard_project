"""
Signal Generator Module

Generates trading signals based on technical indicators and market conditions.
Provides buy/sell signal generation for various trading strategies.

Author: Stock Dashboard Project
Date: 2026-01-01
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Types of trading signals."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    STRONG_BUY = "strong_buy"
    STRONG_SELL = "strong_sell"


class SignalStrength(Enum):
    """Signal strength levels."""
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4


class TradingSignal:
    """Represents a trading signal."""
    
    def __init__(self, symbol: str, signal_type: SignalType, strength: SignalStrength,
                 price: float, timestamp: datetime, confidence: float = 0.0,
                 indicators: Optional[Dict[str, Any]] = None, reason: str = ""):
        """
        Initialize trading signal.
        
        Args:
            symbol: Stock symbol
            signal_type: Type of signal (buy/sell/hold)
            strength: Signal strength
            price: Price at signal generation
            timestamp: When signal was generated
            confidence: Confidence level (0-1)
            indicators: Technical indicators used
            reason: Reason for signal generation
        """
        self.symbol = symbol
        self.signal_type = signal_type
        self.strength = strength
        self.price = price
        self.timestamp = timestamp
        self.confidence = confidence
        self.indicators = indicators or {}
        self.reason = reason
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary."""
        return {
            'symbol': self.symbol,
            'signal_type': self.signal_type.value,
            'strength': self.strength.value,
            'price': self.price,
            'timestamp': self.timestamp.isoformat(),
            'confidence': self.confidence,
            'indicators': self.indicators,
            'reason': self.reason
        }


class SignalGenerator:
    """Main signal generation class."""
    
    def __init__(self, min_confidence: float = 0.6):
        """
        Initialize signal generator.
        
        Args:
            min_confidence: Minimum confidence threshold for signals
        """
        self.min_confidence = min_confidence
        self.logger = logging.getLogger(f"{__name__}.SignalGenerator")
    
    def generate_rsi_signals(self, symbol: str, prices: np.ndarray, 
                           rsi_values: np.ndarray, current_price: float) -> List[TradingSignal]:
        """
        Generate signals based on RSI values.
        
        Args:
            symbol: Stock symbol
            prices: Price array
            rsi_values: RSI values array
            current_price: Current stock price
            
        Returns:
            List of trading signals
        """
        signals = []
        
        if len(rsi_values) == 0 or np.isnan(rsi_values[-1]):
            return signals
        
        current_rsi = rsi_values[-1]
        timestamp = datetime.now()
        
        # Oversold condition (RSI < 30)
        if current_rsi < 30:
            strength = SignalStrength.STRONG if current_rsi < 25 else SignalStrength.MODERATE
            confidence = min(0.9, (30 - current_rsi) / 30 + 0.5)
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.STRONG_BUY if current_rsi < 25 else SignalType.BUY,
                strength=strength,
                price=current_price,
                timestamp=timestamp,
                confidence=confidence,
                indicators={'rsi': current_rsi},
                reason=f"RSI oversold at {current_rsi:.1f}"
            )
            signals.append(signal)
        
        # Overbought condition (RSI > 70)
        elif current_rsi > 70:
            strength = SignalStrength.STRONG if current_rsi > 75 else SignalStrength.MODERATE
            confidence = min(0.9, (current_rsi - 70) / 30 + 0.5)
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.STRONG_SELL if current_rsi > 75 else SignalType.SELL,
                strength=strength,
                price=current_price,
                timestamp=timestamp,
                confidence=confidence,
                indicators={'rsi': current_rsi},
                reason=f"RSI overbought at {current_rsi:.1f}"
            )
            signals.append(signal)
        
        return signals
    
    def generate_macd_signals(self, symbol: str, macd_line: np.ndarray, 
                            signal_line: np.ndarray, histogram: np.ndarray,
                            current_price: float) -> List[TradingSignal]:
        """
        Generate signals based on MACD indicator.
        
        Args:
            symbol: Stock symbol
            macd_line: MACD line values
            signal_line: Signal line values
            histogram: MACD histogram
            current_price: Current stock price
            
        Returns:
            List of trading signals
        """
        signals = []
        
        if len(macd_line) < 2 or len(signal_line) < 2:
            return signals
        
        current_macd = macd_line[-1]
        current_signal = signal_line[-1]
        prev_macd = macd_line[-2]
        prev_signal = signal_line[-2]
        
        timestamp = datetime.now()
        
        # Bullish crossover (MACD crosses above signal line)
        if prev_macd <= prev_signal and current_macd > current_signal:
            confidence = min(0.85, abs(current_macd - current_signal) * 10 + 0.5)
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                price=current_price,
                timestamp=timestamp,
                confidence=confidence,
                indicators={
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': histogram[-1] if len(histogram) > 0 else 0
                },
                reason="MACD bullish crossover"
            )
            signals.append(signal)
        
        # Bearish crossover (MACD crosses below signal line)
        elif prev_macd >= prev_signal and current_macd < current_signal:
            confidence = min(0.85, abs(current_macd - current_signal) * 10 + 0.5)
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                price=current_price,
                timestamp=timestamp,
                confidence=confidence,
                indicators={
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': histogram[-1] if len(histogram) > 0 else 0
                },
                reason="MACD bearish crossover"
            )
            signals.append(signal)
        
        return signals
    
    def generate_bollinger_signals(self, symbol: str, prices: np.ndarray,
                                 upper_band: np.ndarray, lower_band: np.ndarray,
                                 current_price: float) -> List[TradingSignal]:
        """
        Generate signals based on Bollinger Bands.
        
        Args:
            symbol: Stock symbol
            prices: Price array
            upper_band: Upper Bollinger Band
            lower_band: Lower Bollinger Band
            current_price: Current stock price
            
        Returns:
            List of trading signals
        """
        signals = []
        
        if len(upper_band) == 0 or len(lower_band) == 0:
            return signals
        
        current_upper = upper_band[-1]
        current_lower = lower_band[-1]
        timestamp = datetime.now()
        
        # Price near lower band (potential buy)
        if current_price <= current_lower * 1.02:  # Within 2% of lower band
            distance_ratio = (current_lower - current_price) / current_lower
            confidence = min(0.8, distance_ratio * 5 + 0.5)
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                price=current_price,
                timestamp=timestamp,
                confidence=confidence,
                indicators={
                    'bb_upper': current_upper,
                    'bb_lower': current_lower,
                    'price_position': 'near_lower'
                },
                reason="Price near Bollinger lower band"
            )
            signals.append(signal)
        
        # Price near upper band (potential sell)
        elif current_price >= current_upper * 0.98:  # Within 2% of upper band
            distance_ratio = (current_price - current_upper) / current_upper
            confidence = min(0.8, distance_ratio * 5 + 0.5)
            
            signal = TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                price=current_price,
                timestamp=timestamp,
                confidence=confidence,
                indicators={
                    'bb_upper': current_upper,
                    'bb_lower': current_lower,
                    'price_position': 'near_upper'
                },
                reason="Price near Bollinger upper band"
            )
            signals.append(signal)
        
        return signals
    
    def generate_combined_signals(self, symbol: str, indicators: Dict[str, Any],
                                current_price: float) -> List[TradingSignal]:
        """
        Generate signals by combining multiple indicators.
        
        Args:
            symbol: Stock symbol
            indicators: Dictionary of calculated indicators
            current_price: Current stock price
            
        Returns:
            List of combined trading signals
        """
        all_signals = []
        
        try:
            # Generate RSI signals
            if 'rsi' in indicators:
                rsi_signals = self.generate_rsi_signals(
                    symbol, np.array([current_price]), indicators['rsi'], current_price
                )
                all_signals.extend(rsi_signals)
            
            # Generate MACD signals
            if all(k in indicators for k in ['macd_line', 'macd_signal', 'macd_histogram']):
                macd_signals = self.generate_macd_signals(
                    symbol, indicators['macd_line'], indicators['macd_signal'],
                    indicators['macd_histogram'], current_price
                )
                all_signals.extend(macd_signals)
            
            # Generate Bollinger Band signals
            if all(k in indicators for k in ['bb_upper', 'bb_lower']):
                bb_signals = self.generate_bollinger_signals(
                    symbol, np.array([current_price]), indicators['bb_upper'],
                    indicators['bb_lower'], current_price
                )
                all_signals.extend(bb_signals)
            
            # Filter by minimum confidence
            filtered_signals = [s for s in all_signals if s.confidence >= self.min_confidence]
            
            # Create combined signal if multiple indicators agree
            if len(filtered_signals) >= 2:
                buy_signals = [s for s in filtered_signals if s.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]]
                sell_signals = [s for s in filtered_signals if s.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]]
                
                if len(buy_signals) >= 2:
                    combined_confidence = np.mean([s.confidence for s in buy_signals])
                    combined_signal = TradingSignal(
                        symbol=symbol,
                        signal_type=SignalType.STRONG_BUY,
                        strength=SignalStrength.VERY_STRONG,
                        price=current_price,
                        timestamp=datetime.now(),
                        confidence=combined_confidence,
                        indicators=indicators,
                        reason=f"Multiple indicators agree: {', '.join([s.reason for s in buy_signals])}"
                    )
                    filtered_signals.append(combined_signal)
                
                elif len(sell_signals) >= 2:
                    combined_confidence = np.mean([s.confidence for s in sell_signals])
                    combined_signal = TradingSignal(
                        symbol=symbol,
                        signal_type=SignalType.STRONG_SELL,
                        strength=SignalStrength.VERY_STRONG,
                        price=current_price,
                        timestamp=datetime.now(),
                        confidence=combined_confidence,
                        indicators=indicators,
                        reason=f"Multiple indicators agree: {', '.join([s.reason for s in sell_signals])}"
                    )
                    filtered_signals.append(combined_signal)
            
            return filtered_signals
        
        except Exception as e:
            self.logger.error(f"Error generating combined signals for {symbol}: {e}")
            return []
    
    def get_signal_summary(self, signals: List[TradingSignal]) -> Dict[str, Any]:
        """
        Get summary of generated signals.
        
        Args:
            signals: List of trading signals
            
        Returns:
            Summary dictionary
        """
        if not signals:
            return {
                'total_signals': 0,
                'buy_signals': 0,
                'sell_signals': 0,
                'hold_signals': 0,
                'avg_confidence': 0,
                'strongest_signal': None
            }
        
        buy_count = len([s for s in signals if s.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]])
        sell_count = len([s for s in signals if s.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]])
        hold_count = len([s for s in signals if s.signal_type == SignalType.HOLD])
        
        avg_confidence = np.mean([s.confidence for s in signals])
        strongest_signal = max(signals, key=lambda x: x.confidence * x.strength.value)
        
        return {
            'total_signals': len(signals),
            'buy_signals': buy_count,
            'sell_signals': sell_count,
            'hold_signals': hold_count,
            'avg_confidence': round(avg_confidence, 3),
            'strongest_signal': strongest_signal.to_dict()
        }
    
    def backtest_signals(self, symbol: str, historical_data: pd.DataFrame,
                        lookback_days: int = 30) -> Dict[str, Any]:
        """
        Backtest signal generation performance.
        
        Args:
            symbol: Stock symbol
            historical_data: Historical price data
            lookback_days: Days to look back for backtesting
            
        Returns:
            Backtesting results
        """
        try:
            if len(historical_data) < lookback_days:
                return {'error': 'Insufficient historical data'}
            
            # This is a simplified backtest - in practice, you'd want more sophisticated logic
            recent_data = historical_data.tail(lookback_days)
            
            total_signals = 0
            profitable_signals = 0
            total_return = 0
            
            for i in range(5, len(recent_data) - 5):  # Leave buffer for indicators
                # Mock signal generation for backtesting
                current_price = recent_data.iloc[i]['Close']
                future_price = recent_data.iloc[i + 5]['Close']  # 5 days later
                
                # Simple momentum-based signal for backtesting
                if current_price > recent_data.iloc[i-5:i]['Close'].mean():
                    # Generated buy signal
                    total_signals += 1
                    if future_price > current_price:
                        profitable_signals += 1
                        total_return += (future_price - current_price) / current_price
            
            accuracy = profitable_signals / total_signals if total_signals > 0 else 0
            avg_return = total_return / total_signals if total_signals > 0 else 0
            
            return {
                'symbol': symbol,
                'total_signals': total_signals,
                'profitable_signals': profitable_signals,
                'accuracy': round(accuracy, 3),
                'avg_return_per_signal': round(avg_return, 4),
                'total_return': round(total_return, 4),
                'lookback_days': lookback_days
            }
        
        except Exception as e:
            self.logger.error(f"Error in backtesting for {symbol}: {e}")
            return {'error': str(e)}


# Convenience functions
def generate_quick_signal(symbol: str, current_price: float, 
                         rsi: float = None, macd_diff: float = None) -> Optional[TradingSignal]:
    """
    Generate a quick signal based on basic indicators.
    
    Args:
        symbol: Stock symbol
        current_price: Current price
        rsi: RSI value
        macd_diff: MACD line - signal line difference
        
    Returns:
        Trading signal or None
    """
    generator = SignalGenerator()
    
    if rsi is not None:
        if rsi < 30:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strength=SignalStrength.MODERATE,
                price=current_price,
                timestamp=datetime.now(),
                confidence=0.7,
                indicators={'rsi': rsi},
                reason=f"RSI oversold at {rsi:.1f}"
            )
        elif rsi > 70:
            return TradingSignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strength=SignalStrength.MODERATE,
                price=current_price,
                timestamp=datetime.now(),
                confidence=0.7,
                indicators={'rsi': rsi},
                reason=f"RSI overbought at {rsi:.1f}"
            )
    
    return None


def get_signal_color(signal_type: SignalType) -> str:
    """Get color code for signal type."""
    color_map = {
        SignalType.STRONG_BUY: "#28a745",
        SignalType.BUY: "#17a2b8",
        SignalType.HOLD: "#6c757d",
        SignalType.SELL: "#ffc107",
        SignalType.STRONG_SELL: "#dc3545"
    }
    return color_map.get(signal_type, "#6c757d")


def get_signal_icon(signal_type: SignalType) -> str:
    """Get icon for signal type."""
    icon_map = {
        SignalType.STRONG_BUY: "🚀",
        SignalType.BUY: "📈",
        SignalType.HOLD: "⏸️",
        SignalType.SELL: "📉",
        SignalType.STRONG_SELL: "🔻"
    }
    return icon_map.get(signal_type, "❓")