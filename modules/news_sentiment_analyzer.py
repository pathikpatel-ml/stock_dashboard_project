"""
News Sentiment Analyzer Module

A comprehensive news fetching and sentiment analysis module for stock market analysis.
Integrates with NewsAPI for news retrieval and uses TextBlob/VADER for sentiment analysis.
Includes caching mechanisms, error handling, and market sentiment scoring.

Author: Stock Dashboard Project
Date: 2026-01-01
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import hashlib
from pathlib import Path
from functools import lru_cache
import pickle

try:
    import requests
except ImportError:
    raise ImportError("requests library required. Install with: pip install requests")

try:
    from textblob import TextBlob
except ImportError:
    TextBlob = None
    logging.warning("TextBlob not installed. Install with: pip install textblob")

try:
    from nltk.sentiment import SentimentIntensityAnalyzer
    import nltk
    try:
        nltk.data.find('sentiment/vader_lexicon.zip')
    except LookupError:
        try:
            nltk.download('vader_lexicon', quiet=True)
        except Exception as e:
            logging.warning(f"Failed to download NLTK VADER lexicon: {e}")
except ImportError:
    SentimentIntensityAnalyzer = None
    logging.warning("NLTK VADER not available. Install with: pip install nltk")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NewsFetcherError(Exception):
    """Base exception for news fetching errors."""
    pass


class NewsAPIError(NewsFetcherError):
    """Exception for NewsAPI-specific errors."""
    pass


class SentimentAnalysisError(NewsFetcherError):
    """Exception for sentiment analysis errors."""
    pass


class CacheManager:
    """Manages caching of news and sentiment data."""

    def __init__(self, cache_dir: str = ".cache", ttl_minutes: int = 60):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for cache storage
            ttl_minutes: Time to live for cache entries in minutes
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.ttl_minutes = ttl_minutes

    def _get_cache_path(self, key: str) -> Path:
        """Generate cache file path for a key."""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        try:
            cache_path = self._get_cache_path(key)
            if not cache_path.exists():
                return None

            with open(cache_path, 'rb') as f:
                timestamp, data = pickle.load(f)

            if datetime.now() - timestamp > timedelta(minutes=self.ttl_minutes):
                cache_path.unlink()
                return None

            logger.debug(f"Cache hit for key: {key}")
            return data

        except Exception as e:
            logger.warning(f"Cache retrieval error for key {key}: {e}")
            return None

    def set(self, key: str, value: Any) -> bool:
        """
        Store value in cache.

        Args:
            key: Cache key
            value: Value to cache

        Returns:
            True if successful, False otherwise
        """
        try:
            cache_path = self._get_cache_path(key)
            with open(cache_path, 'wb') as f:
                pickle.dump((datetime.now(), value), f)
            logger.debug(f"Cache set for key: {key}")
            return True
        except Exception as e:
            logger.warning(f"Cache write error for key {key}: {e}")
            return False

    def clear(self) -> None:
        """Clear all cache entries."""
        try:
            for cache_file in self.cache_dir.glob("*.cache"):
                cache_file.unlink()
            logger.info("Cache cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")


class SentimentAnalyzer:
    """Performs sentiment analysis using multiple algorithms."""

    def __init__(self):
        """Initialize sentiment analyzers."""
        self.vader_available = SentimentIntensityAnalyzer is not None
        self.textblob_available = TextBlob is not None

        if self.vader_available:
            self.vader = SentimentIntensityAnalyzer()
        if not self.vader_available and not self.textblob_available:
            logger.warning("No sentiment analysis libraries available")

    def analyze_textblob(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment using TextBlob.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with polarity and subjectivity scores
        """
        if not self.textblob_available:
            raise SentimentAnalysisError("TextBlob not available")

        try:
            blob = TextBlob(text)
            return {
                "polarity": blob.sentiment.polarity,  # -1 to 1
                "subjectivity": blob.sentiment.subjectivity  # 0 to 1
            }
        except Exception as e:
            raise SentimentAnalysisError(f"TextBlob analysis failed: {e}")

    def analyze_vader(self, text: str) -> Dict[str, float]:
        """
        Analyze sentiment using VADER (Valence Aware Dictionary and sEntiment Reasoner).

        Args:
            text: Text to analyze

        Returns:
            Dictionary with sentiment scores (neg, neu, pos, compound)
        """
        if not self.vader_available:
            raise SentimentAnalysisError("VADER not available")

        try:
            scores = self.vader.polarity_scores(text)
            return {
                "negative": scores['neg'],
                "neutral": scores['neu'],
                "positive": scores['pos'],
                "compound": scores['compound']  # -1 to 1
            }
        except Exception as e:
            raise SentimentAnalysisError(f"VADER analysis failed: {e}")

    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment using available methods.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with sentiment scores from available methods
        """
        if not text or not isinstance(text, str):
            raise SentimentAnalysisError("Invalid input text")

        results = {}

        # Try VADER first (more reliable for financial news)
        if self.vader_available:
            try:
                results['vader'] = self.analyze_vader(text)
            except SentimentAnalysisError as e:
                logger.warning(f"VADER analysis failed: {e}")

        # Try TextBlob as fallback
        if self.textblob_available:
            try:
                results['textblob'] = self.analyze_textblob(text)
            except SentimentAnalysisError as e:
                logger.warning(f"TextBlob analysis failed: {e}")

        if not results:
            raise SentimentAnalysisError("No sentiment analysis methods available")

        return results

    def get_sentiment_label(self, compound_score: float) -> str:
        """
        Convert compound sentiment score to label.

        Args:
            compound_score: Score between -1 and 1

        Returns:
            Sentiment label: 'very_negative', 'negative', 'neutral', 'positive', 'very_positive'
        """
        if compound_score >= 0.5:
            return "very_positive"
        elif compound_score >= 0.05:
            return "positive"
        elif compound_score <= -0.5:
            return "very_negative"
        elif compound_score <= -0.05:
            return "negative"
        else:
            return "neutral"


class NewsAPIPatcher:
    """Handles NewsAPI integration."""

    BASE_URL = "https://newsapi.org/v2"
    
    def __init__(self, api_key: str = None):
        """
        Initialize NewsAPI patcher.

        Args:
            api_key: NewsAPI key (defaults to NEWSAPI_KEY environment variable)

        Raises:
            NewsAPIError: If no API key is provided or found
        """
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        if not self.api_key:
            raise NewsAPIError(
                "NewsAPI key not provided. Set NEWSAPI_KEY environment variable "
                "or pass api_key parameter. Get key from https://newsapi.org"
            )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "StockDashboard/1.0"})

    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make request to NewsAPI.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            JSON response

        Raises:
            NewsAPIError: If request fails
        """
        url = f"{self.BASE_URL}/{endpoint}"
        params['apiKey'] = self.api_key

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data.get('status') != 'ok':
                raise NewsAPIError(f"API Error: {data.get('message', 'Unknown error')}")

            return data

        except requests.exceptions.Timeout:
            raise NewsAPIError("NewsAPI request timeout (10s)")
        except requests.exceptions.ConnectionError:
            raise NewsAPIError("Failed to connect to NewsAPI")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise NewsAPIError("Invalid NewsAPI key")
            elif e.response.status_code == 426:
                raise NewsAPIError("NewsAPI plan upgrade required")
            raise NewsAPIError(f"HTTP Error {e.response.status_code}: {e}")
        except json.JSONDecodeError:
            raise NewsAPIError("Invalid JSON response from NewsAPI")
        except Exception as e:
            raise NewsAPIError(f"Request failed: {e}")

    def search_everything(
        self,
        q: str,
        sort_by: str = "publishedAt",
        language: str = "en",
        page_size: int = 100,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for news articles.

        Args:
            q: Search query
            sort_by: Sort order (relevancy, publishedAt, popularity)
            language: Language code
            page_size: Number of articles to retrieve (max 100)
            from_date: From date (YYYY-MM-DD format)
            to_date: To date (YYYY-MM-DD format)

        Returns:
            List of article dictionaries

        Raises:
            NewsAPIError: If search fails
        """
        if not q or not isinstance(q, str):
            raise NewsAPIError("Invalid search query")

        params = {
            'q': q,
            'sortBy': sort_by,
            'language': language,
            'pageSize': min(page_size, 100)
        }

        if from_date:
            params['from'] = from_date
        if to_date:
            params['to'] = to_date

        try:
            logger.info(f"Searching news for: {q}")
            data = self._make_request('everything', params)
            articles = data.get('articles', [])
            logger.info(f"Retrieved {len(articles)} articles")
            return articles

        except NewsAPIError:
            raise
        except Exception as e:
            raise NewsAPIError(f"Search failed: {e}")

    def get_top_headlines(
        self,
        category: Optional[str] = None,
        q: Optional[str] = None,
        country: str = "us",
        page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get top headlines.

        Args:
            category: News category (business, health, etc.)
            q: Search query
            country: Country code
            page_size: Number of articles

        Returns:
            List of article dictionaries

        Raises:
            NewsAPIError: If request fails
        """
        params = {
            'pageSize': min(page_size, 100),
            'country': country
        }

        if category:
            params['category'] = category
        if q:
            params['q'] = q

        try:
            logger.info("Fetching top headlines")
            data = self._make_request('top-headlines', params)
            articles = data.get('articles', [])
            return articles

        except NewsAPIError:
            raise
        except Exception as e:
            raise NewsAPIError(f"Failed to fetch headlines: {e}")


class NewsSentimentAnalyzer:
    """Main class for news fetching and sentiment analysis."""

    def __init__(
        self,
        newsapi_key: str = None,
        cache_ttl_minutes: int = 60,
        use_cache: bool = True
    ):
        """
        Initialize News Sentiment Analyzer.

        Args:
            newsapi_key: NewsAPI key (optional, uses env var if not provided)
            cache_ttl_minutes: Cache time to live in minutes
            use_cache: Whether to use caching

        Raises:
            NewsFetcherError: If initialization fails
        """
        try:
            self.newsapi = NewsAPIPatcher(newsapi_key)
            self.sentiment = SentimentAnalyzer()
            self.use_cache = use_cache

            if use_cache:
                self.cache = CacheManager(ttl_minutes=cache_ttl_minutes)
            else:
                self.cache = None

            logger.info("NewsSentimentAnalyzer initialized successfully")

        except Exception as e:
            raise NewsFetcherError(f"Initialization failed: {e}")

    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate cache key from parameters."""
        key_parts = [prefix] + [f"{k}={v}" for k, v in sorted(kwargs.items())]
        return "|".join(key_parts)

    def fetch_news(
        self,
        query: str,
        use_cache: bool = True,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page_size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Fetch news articles for a query.

        Args:
            query: Search query (e.g., stock ticker or company name)
            use_cache: Use cache if available
            from_date: From date (YYYY-MM-DD)
            to_date: To date (YYYY-MM-DD)
            page_size: Number of articles to fetch

        Returns:
            List of articles

        Raises:
            NewsFetcherError: If fetching fails
        """
        try:
            cache_key = self._generate_cache_key(
                "news",
                query=query,
                from_date=from_date,
                to_date=to_date
            )

            # Try cache
            if use_cache and self.cache:
                cached = self.cache.get(cache_key)
                if cached:
                    return cached

            # Fetch from API
            articles = self.newsapi.search_everything(
                q=query,
                page_size=page_size,
                from_date=from_date,
                to_date=to_date
            )

            # Cache results
            if self.cache:
                self.cache.set(cache_key, articles)

            return articles

        except NewsAPIError:
            raise
        except Exception as e:
            raise NewsFetcherError(f"News fetching failed: {e}")

    def analyze_article_sentiment(
        self,
        article: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze sentiment of a single article.

        Args:
            article: Article dictionary with 'title' and 'description'

        Returns:
            Dictionary with sentiment analysis results

        Raises:
            SentimentAnalysisError: If analysis fails
        """
        try:
            title = article.get('title', '')
            description = article.get('description', '')

            # Combine title and description for analysis
            text = f"{title}. {description}".strip()

            if not text:
                raise SentimentAnalysisError("No text to analyze in article")

            sentiment_scores = self.sentiment.analyze(text)

            # Extract compound score from VADER if available
            compound = None
            if 'vader' in sentiment_scores:
                compound = sentiment_scores['vader'].get('compound', 0)

            # Determine sentiment label
            sentiment_label = (
                self.sentiment.get_sentiment_label(compound)
                if compound is not None
                else "unknown"
            )

            return {
                'article': article,
                'text': text,
                'sentiment_scores': sentiment_scores,
                'compound_score': compound,
                'sentiment_label': sentiment_label,
                'analyzed_at': datetime.now().isoformat()
            }

        except SentimentAnalysisError:
            raise
        except Exception as e:
            raise SentimentAnalysisError(f"Article sentiment analysis failed: {e}")

    def analyze_news_sentiment(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        Fetch and analyze sentiment for news articles.

        Args:
            query: Search query
            from_date: From date (YYYY-MM-DD)
            to_date: To date (YYYY-MM-DD)
            page_size: Number of articles to fetch

        Returns:
            Dictionary with articles and sentiment analysis

        Raises:
            NewsFetcherError: If operation fails
        """
        try:
            # Fetch articles
            articles = self.fetch_news(
                query=query,
                from_date=from_date,
                to_date=to_date,
                page_size=page_size
            )

            if not articles:
                logger.warning(f"No articles found for query: {query}")
                return {
                    'query': query,
                    'total_articles': 0,
                    'articles_analyzed': [],
                    'market_sentiment_score': 0,
                    'sentiment_distribution': {}
                }

            # Analyze each article
            analyzed_articles = []
            for article in articles:
                try:
                    analyzed = self.analyze_article_sentiment(article)
                    analyzed_articles.append(analyzed)
                except SentimentAnalysisError as e:
                    logger.warning(f"Failed to analyze article: {e}")
                    continue

            # Calculate market sentiment score
            market_sentiment = self._calculate_market_sentiment(analyzed_articles)

            return {
                'query': query,
                'total_articles': len(articles),
                'articles_analyzed': len(analyzed_articles),
                'articles': analyzed_articles,
                'market_sentiment_score': market_sentiment['score'],
                'sentiment_distribution': market_sentiment['distribution'],
                'timestamp': datetime.now().isoformat()
            }

        except NewsFetcherError:
            raise
        except Exception as e:
            raise NewsFetcherError(f"News sentiment analysis failed: {e}")

    def _calculate_market_sentiment(
        self,
        analyzed_articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate overall market sentiment from articles.

        Args:
            analyzed_articles: List of analyzed articles

        Returns:
            Dictionary with sentiment score and distribution
        """
        if not analyzed_articles:
            return {'score': 0, 'distribution': {}}

        compound_scores = []
        sentiment_counts = {
            'very_positive': 0,
            'positive': 0,
            'neutral': 0,
            'negative': 0,
            'very_negative': 0
        }

        for article in analyzed_articles:
            compound = article.get('compound_score')
            if compound is not None:
                compound_scores.append(compound)

            label = article.get('sentiment_label')
            if label in sentiment_counts:
                sentiment_counts[label] += 1

        # Calculate average sentiment score
        avg_sentiment = (
            sum(compound_scores) / len(compound_scores)
            if compound_scores
            else 0
        )

        # Normalize to 0-100 scale
        sentiment_score = ((avg_sentiment + 1) / 2) * 100

        # Calculate distribution percentages
        total = len(analyzed_articles)
        distribution = {
            k: (v / total) * 100 for k, v in sentiment_counts.items()
        }

        return {
            'score': round(sentiment_score, 2),
            'average_compound': round(avg_sentiment, 4),
            'distribution': {k: round(v, 2) for k, v in distribution.items()}
        }

    def get_sentiment_summary(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a summary of sentiment analysis results.

        Args:
            query: Search query
            from_date: From date (YYYY-MM-DD)
            to_date: To date (YYYY-MM-DD)

        Returns:
            Summary dictionary

        Raises:
            NewsFetcherError: If operation fails
        """
        try:
            results = self.analyze_news_sentiment(
                query=query,
                from_date=from_date,
                to_date=to_date
            )

            return {
                'query': query,
                'analyzed_articles': results['articles_analyzed'],
                'market_sentiment_score': results['market_sentiment_score'],
                'sentiment_distribution': results['sentiment_distribution'],
                'timestamp': results['timestamp']
            }

        except NewsFetcherError:
            raise


def main():
    """Example usage of NewsSentimentAnalyzer."""
    try:
        # Initialize analyzer
        analyzer = NewsSentimentAnalyzer(use_cache=True)

        # Example: Analyze sentiment for a stock
        query = "Apple Inc AAPL"
        print(f"\nAnalyzing sentiment for: {query}\n")

        results = analyzer.get_sentiment_summary(query)

        print(f"Query: {results['query']}")
        print(f"Articles Analyzed: {results['analyzed_articles']}")
        print(f"Market Sentiment Score: {results['market_sentiment_score']}/100")
        print(f"\nSentiment Distribution:")
        for sentiment, percentage in results['sentiment_distribution'].items():
            print(f"  {sentiment}: {percentage:.2f}%")

    except NewsFetcherError as e:
        logger.error(f"Error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
