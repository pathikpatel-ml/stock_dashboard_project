#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Market Sentiment and Technical Indicators Module
Fetches sentiment data and technical indicators from Alpha Vantage and Finnhub
"""

import requests
import pandas as pd
import time
from datetime import datetime
import os

class MarketSentiment:
    def __init__(self, alpha_vantage_key=None, finnhub_key=None):
        """
        Initialize with API keys
        Get free keys from:
        - Alpha Vantage: https://www.alphavantage.co/support/#api-key
        - Finnhub: https://finnhub.io/register
        """
        self.alpha_vantage_key = alpha_vantage_key or os.getenv('ALPHA_VANTAGE_KEY')
        self.finnhub_key = finnhub_key or os.getenv('FINNHUB_KEY')
        
        self.alpha_vantage_base = "https://www.alphavantage.co/query"
        self.finnhub_base = "https://finnhub.io/api/v1"
    
    # ===== ALPHA VANTAGE INDICATORS =====
    
    def get_rsi(self, symbol, interval='daily', time_period=14):
        """Get RSI (Relative Strength Index) from Alpha Vantage"""
        if not self.alpha_vantage_key:
            return None
        
        params = {
            'function': 'RSI',
            'symbol': symbol,
            'interval': interval,
            'time_period': time_period,
            'series_type': 'close',
            'apikey': self.alpha_vantage_key
        }
        
        try:
            response = requests.get(self.alpha_vantage_base, params=params, timeout=10)
            data = response.json()
            
            if 'Technical Analysis: RSI' in data:
                latest_date = list(data['Technical Analysis: RSI'].keys())[0]
                rsi_value = float(data['Technical Analysis: RSI'][latest_date]['RSI'])
                return {'date': latest_date, 'rsi': rsi_value}
        except Exception as e:
            print(f"Error fetching RSI for {symbol}: {e}")
        
        return None
    
    def get_macd(self, symbol, interval='daily'):
        """Get MACD (Moving Average Convergence Divergence) from Alpha Vantage"""
        if not self.alpha_vantage_key:
            return None
        
        params = {
            'function': 'MACD',
            'symbol': symbol,
            'interval': interval,
            'series_type': 'close',
            'apikey': self.alpha_vantage_key
        }
        
        try:
            response = requests.get(self.alpha_vantage_base, params=params, timeout=10)
            data = response.json()
            
            if 'Technical Analysis: MACD' in data:
                latest_date = list(data['Technical Analysis: MACD'].keys())[0]
                macd_data = data['Technical Analysis: MACD'][latest_date]
                return {
                    'date': latest_date,
                    'macd': float(macd_data['MACD']),
                    'signal': float(macd_data['MACD_Signal']),
                    'histogram': float(macd_data['MACD_Hist'])
                }
        except Exception as e:
            print(f"Error fetching MACD for {symbol}: {e}")
        
        return None
    
    def get_adx(self, symbol, interval='daily', time_period=14):
        """Get ADX (Average Directional Index) - trend strength indicator"""
        if not self.alpha_vantage_key:
            return None
        
        params = {
            'function': 'ADX',
            'symbol': symbol,
            'interval': interval,
            'time_period': time_period,
            'apikey': self.alpha_vantage_key
        }
        
        try:
            response = requests.get(self.alpha_vantage_base, params=params, timeout=10)
            data = response.json()
            
            if 'Technical Analysis: ADX' in data:
                latest_date = list(data['Technical Analysis: ADX'].keys())[0]
                adx_value = float(data['Technical Analysis: ADX'][latest_date]['ADX'])
                return {'date': latest_date, 'adx': adx_value}
        except Exception as e:
            print(f"Error fetching ADX for {symbol}: {e}")
        
        return None
    
    # ===== FINNHUB SENTIMENT & NEWS =====
    
    def get_news_sentiment(self, symbol):
        """Get news sentiment from Finnhub"""
        if not self.finnhub_key:
            return None
        
        url = f"{self.finnhub_base}/news-sentiment"
        params = {'symbol': symbol, 'token': self.finnhub_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if 'sentiment' in data:
                return {
                    'sentiment_score': data['sentiment'].get('bullishPercent', 0),
                    'bearish_percent': data['sentiment'].get('bearishPercent', 0),
                    'buzz_articles': data.get('buzz', {}).get('articlesInLastWeek', 0)
                }
        except Exception as e:
            print(f"Error fetching sentiment for {symbol}: {e}")
        
        return None
    
    def get_recommendation_trends(self, symbol):
        """Get analyst recommendations from Finnhub"""
        if not self.finnhub_key:
            return None
        
        url = f"{self.finnhub_base}/stock/recommendation"
        params = {'symbol': symbol, 'token': self.finnhub_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data and len(data) > 0:
                latest = data[0]
                return {
                    'period': latest.get('period'),
                    'strong_buy': latest.get('strongBuy', 0),
                    'buy': latest.get('buy', 0),
                    'hold': latest.get('hold', 0),
                    'sell': latest.get('sell', 0),
                    'strong_sell': latest.get('strongSell', 0)
                }
        except Exception as e:
            print(f"Error fetching recommendations for {symbol}: {e}")
        
        return None
    
    def get_company_news(self, symbol, from_date=None, to_date=None):
        """Get recent company news from Finnhub"""
        if not self.finnhub_key:
            return None
        
        if not from_date:
            from_date = (datetime.now() - pd.Timedelta(days=7)).strftime('%Y-%m-%d')
        if not to_date:
            to_date = datetime.now().strftime('%Y-%m-%d')
        
        url = f"{self.finnhub_base}/company-news"
        params = {
            'symbol': symbol,
            'from': from_date,
            'to': to_date,
            'token': self.finnhub_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data:
                return [{
                    'headline': item.get('headline'),
                    'summary': item.get('summary'),
                    'source': item.get('source'),
                    'datetime': datetime.fromtimestamp(item.get('datetime')).strftime('%Y-%m-%d %H:%M:%S')
                } for item in data[:5]]  # Return top 5 news
        except Exception as e:
            print(f"Error fetching news for {symbol}: {e}")
        
        return None
    
    # ===== COMBINED ANALYSIS =====
    
    def get_comprehensive_analysis(self, symbol, nse_format=True):
        """
        Get comprehensive technical and sentiment analysis for a stock
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE' for NSE or 'RELIANCE.NS' for Yahoo)
            nse_format: If True, converts NSE symbol to US format for APIs
        """
        # Convert NSE symbol to format accepted by APIs
        api_symbol = symbol.replace('.NS', '') if nse_format else symbol
        
        print(f"\nFetching comprehensive analysis for {symbol}...")
        
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'technical_indicators': {},
            'sentiment': {},
            'recommendations': {},
            'news': []
        }
        
        # Technical Indicators (Alpha Vantage)
        if self.alpha_vantage_key:
            print(f"  Fetching RSI...")
            rsi = self.get_rsi(api_symbol)
            if rsi:
                analysis['technical_indicators']['rsi'] = rsi
            time.sleep(12)  # Alpha Vantage free tier: 5 calls/min
            
            print(f"  Fetching MACD...")
            macd = self.get_macd(api_symbol)
            if macd:
                analysis['technical_indicators']['macd'] = macd
            time.sleep(12)
            
            print(f"  Fetching ADX...")
            adx = self.get_adx(api_symbol)
            if adx:
                analysis['technical_indicators']['adx'] = adx
        
        # Sentiment & News (Finnhub)
        if self.finnhub_key:
            print(f"  Fetching sentiment...")
            sentiment = self.get_news_sentiment(api_symbol)
            if sentiment:
                analysis['sentiment'] = sentiment
            
            print(f"  Fetching recommendations...")
            recommendations = self.get_recommendation_trends(api_symbol)
            if recommendations:
                analysis['recommendations'] = recommendations
            
            print(f"  Fetching news...")
            news = self.get_company_news(api_symbol)
            if news:
                analysis['news'] = news
        
        return analysis
    
    def analyze_signal(self, analysis):
        """
        Analyze technical indicators and sentiment to generate trading signal
        
        Returns: 'BUY', 'SELL', 'HOLD', or 'NEUTRAL'
        """
        signals = []
        
        # RSI Analysis
        if 'rsi' in analysis.get('technical_indicators', {}):
            rsi_value = analysis['technical_indicators']['rsi']['rsi']
            if rsi_value < 30:
                signals.append('BUY')  # Oversold
            elif rsi_value > 70:
                signals.append('SELL')  # Overbought
            else:
                signals.append('HOLD')
        
        # MACD Analysis
        if 'macd' in analysis.get('technical_indicators', {}):
            macd_data = analysis['technical_indicators']['macd']
            if macd_data['macd'] > macd_data['signal']:
                signals.append('BUY')  # Bullish crossover
            else:
                signals.append('SELL')  # Bearish crossover
        
        # ADX Analysis (trend strength)
        if 'adx' in analysis.get('technical_indicators', {}):
            adx_value = analysis['technical_indicators']['adx']['adx']
            if adx_value > 25:
                signals.append('STRONG_TREND')
        
        # Sentiment Analysis
        if 'sentiment_score' in analysis.get('sentiment', {}):
            sentiment_score = analysis['sentiment']['sentiment_score']
            if sentiment_score > 0.6:
                signals.append('BUY')
            elif sentiment_score < 0.4:
                signals.append('SELL')
        
        # Aggregate signals
        buy_count = signals.count('BUY')
        sell_count = signals.count('SELL')
        
        if buy_count > sell_count:
            return 'BUY'
        elif sell_count > buy_count:
            return 'SELL'
        elif 'HOLD' in signals:
            return 'HOLD'
        else:
            return 'NEUTRAL'


def main():
    """Example usage"""
    # Initialize with your API keys
    sentiment = MarketSentiment(
        alpha_vantage_key='YOUR_ALPHA_VANTAGE_KEY',
        finnhub_key='YOUR_FINNHUB_KEY'
    )
    
    # Analyze a stock
    symbol = 'RELIANCE'
    analysis = sentiment.get_comprehensive_analysis(symbol)
    
    print(f"\n{'='*60}")
    print(f"Analysis for {symbol}")
    print(f"{'='*60}")
    
    # Technical Indicators
    if analysis['technical_indicators']:
        print("\nTechnical Indicators:")
        for indicator, data in analysis['technical_indicators'].items():
            print(f"  {indicator.upper()}: {data}")
    
    # Sentiment
    if analysis['sentiment']:
        print("\nSentiment:")
        for key, value in analysis['sentiment'].items():
            print(f"  {key}: {value}")
    
    # Recommendations
    if analysis['recommendations']:
        print("\nAnalyst Recommendations:")
        for key, value in analysis['recommendations'].items():
            print(f"  {key}: {value}")
    
    # Trading Signal
    signal = sentiment.analyze_signal(analysis)
    print(f"\nTrading Signal: {signal}")


if __name__ == "__main__":
    main()
