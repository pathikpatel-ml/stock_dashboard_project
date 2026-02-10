#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
V20 Dashboard Integration with Market News & Sentiment
Provides stable, contextualized market signals
"""

import pandas as pd
from datetime import datetime
from modules.market_news_agent import MarketNewsAgent
import yfinance as yf

class V20MarketContextProvider:
    def __init__(self, cache_duration_minutes=30):
        self.news_agent = MarketNewsAgent(cache_duration_minutes)
        self.last_refresh = {}
    
    def get_enhanced_stock_data(self, symbol: str) -> dict:
        """Get stock data with news context"""
        # Get technical data
        technical_data = self._get_technical_indicators(symbol)
        
        # Get news and sentiment
        market_context = self.news_agent.get_market_context(symbol, technical_data)
        
        # Combine for dashboard
        enhanced_data = {
            'symbol': symbol,
            'price': technical_data.get('current_price', 0),
            'change_pct': technical_data.get('change_pct', 0),
            'technical_signal': technical_data.get('signal', 'HOLD'),
            'news_sentiment': market_context['news_sentiment'],
            'combined_signal': market_context['combined_signal'],
            'confidence': market_context['confidence'],
            'news_summary': self._create_news_summary(market_context['top_news']),
            'last_updated': market_context['last_updated'],
            'indicators': {
                'rsi': technical_data.get('rsi', 50),
                'macd': technical_data.get('macd', 'Neutral'),
                'moving_avg': technical_data.get('moving_avg', 'Neutral')
            }
        }
        
        return enhanced_data
    
    def _get_technical_indicators(self, symbol: str) -> dict:
        """Calculate technical indicators"""
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            hist = ticker.history(period="3mo")
            
            if hist.empty:
                return {'signal': 'HOLD', 'current_price': 0, 'change_pct': 0}
            
            current_price = hist['Close'].iloc[-1]
            prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
            change_pct = ((current_price - prev_price) / prev_price) * 100
            
            # Calculate RSI
            rsi = self._calculate_rsi(hist['Close'])
            
            # Calculate MACD signal
            macd_signal = self._calculate_macd_signal(hist['Close'])
            
            # Calculate moving average signal
            ma_signal = self._calculate_ma_signal(hist['Close'])
            
            # Determine overall technical signal
            signal = self._determine_technical_signal(rsi, macd_signal, ma_signal)
            
            return {
                'current_price': round(current_price, 2),
                'change_pct': round(change_pct, 2),
                'rsi': round(rsi, 2),
                'macd': macd_signal,
                'moving_avg': ma_signal,
                'signal': signal
            }
        except Exception as e:
            print(f"Error calculating technical indicators for {symbol}: {e}")
            return {'signal': 'HOLD', 'current_price': 0, 'change_pct': 0}
    
    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not rsi.empty else 50
    
    def _calculate_macd_signal(self, prices):
        """Calculate MACD signal"""
        ema12 = prices.ewm(span=12).mean()
        ema26 = prices.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        
        if macd.iloc[-1] > signal.iloc[-1]:
            return 'Bullish'
        elif macd.iloc[-1] < signal.iloc[-1]:
            return 'Bearish'
        return 'Neutral'
    
    def _calculate_ma_signal(self, prices):
        """Calculate moving average signal"""
        ma20 = prices.rolling(window=20).mean()
        ma50 = prices.rolling(window=50).mean()
        
        current_price = prices.iloc[-1]
        
        if current_price > ma20.iloc[-1] and ma20.iloc[-1] > ma50.iloc[-1]:
            return 'Bullish'
        elif current_price < ma20.iloc[-1] and ma20.iloc[-1] < ma50.iloc[-1]:
            return 'Bearish'
        return 'Neutral'
    
    def _determine_technical_signal(self, rsi, macd_signal, ma_signal):
        """Determine overall technical signal"""
        bullish_count = 0
        bearish_count = 0
        
        # RSI signal
        if rsi < 30:
            bullish_count += 1
        elif rsi > 70:
            bearish_count += 1
        
        # MACD signal
        if macd_signal == 'Bullish':
            bullish_count += 1
        elif macd_signal == 'Bearish':
            bearish_count += 1
        
        # MA signal
        if ma_signal == 'Bullish':
            bullish_count += 1
        elif ma_signal == 'Bearish':
            bearish_count += 1
        
        if bullish_count >= 2:
            return 'BUY'
        elif bearish_count >= 2:
            return 'SELL'
        return 'HOLD'
    
    def _create_news_summary(self, news_items):
        """Create a brief news summary"""
        if not news_items:
            return "No recent news available"
        
        summaries = []
        for item in news_items[:3]:
            title = item.get('title', '')
            if title:
                summaries.append(title[:100])
        
        return " | ".join(summaries)
    
    def get_v20_dashboard_data(self, symbols: list) -> pd.DataFrame:
        """Get enhanced data for all V20 stocks"""
        data = []
        
        for symbol in symbols:
            try:
                enhanced_data = self.get_enhanced_stock_data(symbol)
                data.append(enhanced_data)
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
        
        df = pd.DataFrame(data)
        
        # Add timestamp
        df['refresh_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return df
    
    def should_refresh(self, symbol: str, force_refresh: bool = False) -> bool:
        """Check if data should be refreshed"""
        if force_refresh:
            return True
        
        if symbol not in self.last_refresh:
            return True
        
        time_since_refresh = datetime.now() - self.last_refresh[symbol]
        return time_since_refresh.total_seconds() > 1800  # 30 minutes


# Example usage
if __name__ == "__main__":
    provider = V20MarketContextProvider(cache_duration_minutes=30)
    
    # Test with a single stock
    symbol = "RELIANCE"
    data = provider.get_enhanced_stock_data(symbol)
    
    print(f"\nEnhanced Data for {symbol}:")
    print(f"Price: ₹{data['price']}")
    print(f"Change: {data['change_pct']}%")
    print(f"Technical Signal: {data['technical_signal']}")
    print(f"News Sentiment: {data['news_sentiment']}")
    print(f"Combined Signal: {data['combined_signal']}")
    print(f"Confidence: {data['confidence']}")
    print(f"News Summary: {data['news_summary']}")
    print(f"Last Updated: {data['last_updated']}")
