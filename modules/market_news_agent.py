#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Market News & Sentiment Agent
Fetches live news and analyzes sentiment for stocks with intelligent caching
"""

import requests
import json
from datetime import datetime, timedelta
import pandas as pd
from typing import List, Dict
import time
import os

class MarketNewsAgent:
    def __init__(self, cache_duration_minutes=30):
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.cache = {}
        self.cache_dir = "cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        
    def get_stock_news(self, symbol: str, force_refresh: bool = False) -> Dict:
        """Get news for a stock with caching"""
        cache_key = f"news_{symbol}"
        
        # Check cache
        if not force_refresh and cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data
        
        # Fetch fresh news
        news_data = self._fetch_news_from_sources(symbol)
        
        # Cache the result
        self.cache[cache_key] = (news_data, datetime.now())
        
        return news_data
    
    def _fetch_news_from_sources(self, symbol: str) -> Dict:
        """Fetch news from multiple sources"""
        news_items = []
        
        # Source 1: Yahoo Finance RSS
        yahoo_news = self._fetch_yahoo_finance_news(symbol)
        news_items.extend(yahoo_news)
        
        # Source 2: Google News (via RSS)
        google_news = self._fetch_google_news(symbol)
        news_items.extend(google_news)
        
        # Source 3: Economic Times (if available)
        et_news = self._fetch_economic_times_news(symbol)
        news_items.extend(et_news)
        
        # Analyze sentiment
        sentiment = self._analyze_sentiment(news_items)
        
        return {
            'symbol': symbol,
            'news_count': len(news_items),
            'news_items': news_items[:10],  # Top 10 news
            'sentiment': sentiment,
            'last_updated': datetime.now().isoformat()
        }
    
    def _fetch_yahoo_finance_news(self, symbol: str) -> List[Dict]:
        """Fetch news from Yahoo Finance"""
        try:
            url = f"https://finance.yahoo.com/quote/{symbol}.NS/news"
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Parse news from HTML (simplified)
                news = []
                # Add basic parsing logic here
                return news
        except:
            pass
        return []
    
    def _fetch_google_news(self, symbol: str) -> List[Dict]:
        """Fetch news from Google News RSS"""
        try:
            company_name = symbol  # You can map symbol to company name
            url = f"https://news.google.com/rss/search?q={company_name}+stock&hl=en-IN&gl=IN&ceid=IN:en"
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Parse RSS feed
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)
                
                news = []
                for item in root.findall('.//item')[:5]:
                    title = item.find('title').text if item.find('title') is not None else ""
                    link = item.find('link').text if item.find('link') is not None else ""
                    pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
                    
                    news.append({
                        'title': title,
                        'url': link,
                        'published': pub_date,
                        'source': 'Google News'
                    })
                
                return news
        except Exception as e:
            print(f"Error fetching Google News: {e}")
        return []
    
    def _fetch_economic_times_news(self, symbol: str) -> List[Dict]:
        """Fetch news from Economic Times"""
        # Placeholder for ET news
        return []
    
    def _analyze_sentiment(self, news_items: List[Dict]) -> Dict:
        """Analyze sentiment of news items"""
        if not news_items:
            return {
                'score': 0,
                'label': 'Neutral',
                'confidence': 0
            }
        
        # Simple keyword-based sentiment (can be enhanced with LLM)
        positive_keywords = ['surge', 'gain', 'profit', 'growth', 'bullish', 'upgrade', 'buy', 'strong', 'positive']
        negative_keywords = ['fall', 'loss', 'decline', 'bearish', 'downgrade', 'sell', 'weak', 'negative', 'crash']
        
        positive_count = 0
        negative_count = 0
        
        for item in news_items:
            title = item.get('title', '').lower()
            for keyword in positive_keywords:
                if keyword in title:
                    positive_count += 1
            for keyword in negative_keywords:
                if keyword in title:
                    negative_count += 1
        
        total = positive_count + negative_count
        if total == 0:
            sentiment_score = 0
            label = 'Neutral'
        else:
            sentiment_score = (positive_count - negative_count) / total
            if sentiment_score > 0.2:
                label = 'Positive'
            elif sentiment_score < -0.2:
                label = 'Negative'
            else:
                label = 'Neutral'
        
        return {
            'score': round(sentiment_score, 2),
            'label': label,
            'confidence': round(abs(sentiment_score), 2),
            'positive_mentions': positive_count,
            'negative_mentions': negative_count
        }
    
    def get_market_context(self, symbol: str, technical_indicators: Dict) -> Dict:
        """Combine technical indicators with news sentiment for stable context"""
        news_data = self.get_stock_news(symbol)
        
        # Create stable market context
        context = {
            'symbol': symbol,
            'technical_signal': technical_indicators.get('signal', 'HOLD'),
            'news_sentiment': news_data['sentiment']['label'],
            'sentiment_score': news_data['sentiment']['score'],
            'news_count': news_data['news_count'],
            'combined_signal': self._combine_signals(
                technical_indicators.get('signal', 'HOLD'),
                news_data['sentiment']['label']
            ),
            'confidence': self._calculate_confidence(technical_indicators, news_data),
            'last_updated': news_data['last_updated'],
            'top_news': news_data['news_items'][:3]
        }
        
        return context
    
    def _combine_signals(self, technical_signal: str, sentiment_label: str) -> str:
        """Combine technical and sentiment signals"""
        signal_map = {
            ('BUY', 'Positive'): 'STRONG BUY',
            ('BUY', 'Neutral'): 'BUY',
            ('BUY', 'Negative'): 'HOLD',
            ('SELL', 'Negative'): 'STRONG SELL',
            ('SELL', 'Neutral'): 'SELL',
            ('SELL', 'Positive'): 'HOLD',
            ('HOLD', 'Positive'): 'BUY',
            ('HOLD', 'Negative'): 'SELL',
            ('HOLD', 'Neutral'): 'HOLD'
        }
        
        return signal_map.get((technical_signal, sentiment_label), 'HOLD')
    
    def _calculate_confidence(self, technical_indicators: Dict, news_data: Dict) -> float:
        """Calculate confidence score for the signal"""
        # Base confidence from technical indicators
        tech_confidence = 0.5
        
        # Adjust based on news sentiment confidence
        sentiment_confidence = news_data['sentiment']['confidence']
        
        # Combined confidence
        combined = (tech_confidence + sentiment_confidence) / 2
        
        return round(combined, 2)
    
    def get_batch_market_context(self, symbols: List[str]) -> pd.DataFrame:
        """Get market context for multiple stocks"""
        contexts = []
        
        for symbol in symbols:
            try:
                # Get basic technical indicators (placeholder)
                technical_indicators = {'signal': 'HOLD'}
                
                context = self.get_market_context(symbol, technical_indicators)
                contexts.append(context)
                
                time.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
        
        return pd.DataFrame(contexts)


class SimpleLLMSentimentAnalyzer:
    """Simple LLM-based sentiment analyzer (can be enhanced with OpenAI/Anthropic)"""
    
    def analyze_news_with_llm(self, news_items: List[Dict]) -> Dict:
        """Analyze news sentiment using LLM reasoning"""
        # Prepare news text
        news_text = "\n".join([f"- {item['title']}" for item in news_items[:5]])
        
        # Simple rule-based analysis (can be replaced with actual LLM call)
        prompt = f"""
        Analyze the following news headlines for stock market sentiment:
        
        {news_text}
        
        Provide:
        1. Overall sentiment (Positive/Negative/Neutral)
        2. Key themes
        3. Market outlook
        """
        
        # Placeholder for LLM response
        # In production, call OpenAI/Anthropic API here
        
        return {
            'sentiment': 'Neutral',
            'themes': ['Market volatility', 'Sector performance'],
            'outlook': 'Mixed signals in the market'
        }


# Example usage
if __name__ == "__main__":
    agent = MarketNewsAgent(cache_duration_minutes=30)
    
    # Test with a stock
    symbol = "RELIANCE"
    news_data = agent.get_stock_news(symbol)
    
    print(f"News for {symbol}:")
    print(f"Sentiment: {news_data['sentiment']['label']} ({news_data['sentiment']['score']})")
    print(f"News count: {news_data['news_count']}")
    print(f"Last updated: {news_data['last_updated']}")
