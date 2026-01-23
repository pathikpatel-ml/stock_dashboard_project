#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Research script to test different stock data APIs
"""

import requests
import time
import json

def test_screener_in_api():
    """Test current Screener.in API endpoints"""
    print("=== Testing Screener.in API ===")
    
    # Test different endpoint patterns
    endpoints_to_test = [
        "https://www.screener.in/api/company/search/?q=RELIANCE",
        "https://screener.in/api/company/search/?q=RELIANCE", 
        "https://www.screener.in/company/search/?q=RELIANCE",
        "https://screener.in/company/search/?q=RELIANCE"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for endpoint in endpoints_to_test:
        try:
            print(f"\nTesting: {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Response type: {type(data)}")
                    if isinstance(data, list) and len(data) > 0:
                        print(f"First result keys: {list(data[0].keys())}")
                    elif isinstance(data, dict):
                        print(f"Response keys: {list(data.keys())}")
                    return True
                except:
                    print("Response is not JSON")
            else:
                print(f"Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"Error: {e}")
    
    return False

def test_alpha_vantage_api():
    """Test Alpha Vantage API (requires API key)"""
    print("\n=== Testing Alpha Vantage API ===")
    
    # Note: Alpha Vantage requires API key, testing without key to see response
    test_urls = [
        "https://www.alphavantage.co/query?function=OVERVIEW&symbol=RELIANCE.BSE&apikey=demo",
        "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=RELIANCE.BSE&apikey=demo"
    ]
    
    for url in test_urls:
        try:
            print(f"\nTesting: {url}")
            response = requests.get(url, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Response keys: {list(data.keys())}")
                    if 'Note' in data:
                        print(f"API Note: {data['Note']}")
                    elif 'Error Message' in data:
                        print(f"API Error: {data['Error Message']}")
                    else:
                        print("API seems to work (need valid API key)")
                        return True
                except:
                    print("Response is not JSON")
            
        except Exception as e:
            print(f"Error: {e}")
    
    return False

def test_nse_api():
    """Test NSE India API endpoints"""
    print("\n=== Testing NSE India API ===")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br'
    }
    
    test_urls = [
        "https://www.nseindia.com/api/quote-equity?symbol=RELIANCE",
        "https://www.nseindia.com/api/equity-stockIndices?index=NIFTY%2050",
        "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    ]
    
    for url in test_urls:
        try:
            print(f"\nTesting: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                if 'csv' in url:
                    print("CSV data available")
                    return True
                else:
                    try:
                        data = response.json()
                        print(f"Response keys: {list(data.keys())}")
                        return True
                    except:
                        print("Response is not JSON")
            
        except Exception as e:
            print(f"Error: {e}")
    
    return False

def test_yahoo_finance_api():
    """Test Yahoo Finance API endpoints"""
    print("\n=== Testing Yahoo Finance API ===")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    test_urls = [
        "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS",
        "https://query2.finance.yahoo.com/v10/finance/quoteSummary/RELIANCE.NS?modules=summaryDetail,financialData"
    ]
    
    for url in test_urls:
        try:
            print(f"\nTesting: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"Response structure available")
                    return True
                except:
                    print("Response is not JSON")
            
        except Exception as e:
            print(f"Error: {e}")
    
    return False

def test_bse_api():
    """Test BSE API endpoints"""
    print("\n=== Testing BSE API ===")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    test_urls = [
        "https://api.bseindia.com/BseIndiaAPI/api/StockReachGraph/w?scripcode=500325&flag=0",
        "https://www.bseindia.com/corporates/List_Scrips.html"
    ]
    
    for url in test_urls:
        try:
            print(f"\nTesting: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                print("BSE endpoint accessible")
                return True
            
        except Exception as e:
            print(f"Error: {e}")
    
    return False

if __name__ == "__main__":
    print("Stock Data API Research")
    print("=" * 50)
    
    apis_working = []
    
    if test_screener_in_api():
        apis_working.append("Screener.in")
    
    if test_alpha_vantage_api():
        apis_working.append("Alpha Vantage")
    
    if test_nse_api():
        apis_working.append("NSE India")
    
    if test_yahoo_finance_api():
        apis_working.append("Yahoo Finance")
    
    if test_bse_api():
        apis_working.append("BSE")
    
    print(f"\n" + "=" * 50)
    print("SUMMARY:")
    print(f"Working APIs: {apis_working}")
    
    if not apis_working:
        print("No APIs are currently accessible. May need API keys or different approach.")
    else:
        print(f"Recommended: Use {apis_working[0]} for implementation")