# modules/stock_name_resolver.py
import yfinance as yf
from functools import lru_cache
import requests
import time

class StockNameResolver:
    """Resolve stock symbols to full company names with caching"""
    
    def __init__(self):
        self.cache = {}
        
    @lru_cache(maxsize=500)
    def get_stock_name(self, symbol):
        """Get full company name for a stock symbol"""
        try:
            # Check cache first
            if symbol in self.cache:
                return self.cache[symbol]
            
            # Try yfinance first (faster)
            try:
                ticker = yf.Ticker(f"{symbol}.NS")  # NSE format
                info = ticker.info
                name = info.get('longName') or info.get('shortName')
                if name and name != symbol:
                    self.cache[symbol] = name
                    return name
            except:
                pass
            
            # Fallback to BSE format
            try:
                ticker = yf.Ticker(f"{symbol}.BO")  # BSE format
                info = ticker.info
                name = info.get('longName') or info.get('shortName')
                if name and name != symbol:
                    self.cache[symbol] = name
                    return name
            except:
                pass
            
            # If all fails, return symbol
            return symbol
            
        except Exception as e:
            print(f"Error resolving name for {symbol}: {e}")
            return symbol
    
    def get_display_name(self, symbol, max_length=25):
        """Get display name with length limit"""
        full_name = self.get_stock_name(symbol)
        if len(full_name) > max_length:
            return full_name[:max_length-3] + "..."
        return full_name

# Global instance
stock_resolver = StockNameResolver()