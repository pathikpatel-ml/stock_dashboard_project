import requests
from bs4 import BeautifulSoup
import re

def debug_screener_access(symbol):
    """Debug screener.in access for a specific symbol"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    print(f"Testing URL: {url}")
    
    try:
        response = session.get(url, timeout=15)
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print(f"Content Length: {len(response.content)}")
            
            # Check if we got actual content or a redirect/block page
            soup = BeautifulSoup(response.content, 'html.parser')
            title = soup.find('title')
            print(f"Page Title: {title.text if title else 'No title found'}")
            
            # Look for common blocking indicators
            if any(keyword in response.text.lower() for keyword in ['blocked', 'captcha', 'access denied', 'rate limit']):
                print("[WARNING] Possible blocking detected in content")
            
            # Look for debt to equity specifically
            text_content = soup.get_text().lower()
            if 'debt' in text_content and 'equity' in text_content:
                print("[SUCCESS] Found debt/equity related content")
                
                # Try to find the actual ratio
                patterns = [
                    r'debt\s*to\s*equity[:\s]*([0-9]+\.?[0-9]*)',
                    r'debt/equity[:\s]*([0-9]+\.?[0-9]*)',
                    r'd/e[:\s]*([0-9]+\.?[0-9]*)'
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, text_content)
                    if matches:
                        print(f"[SUCCESS] Found D/E ratio using pattern '{pattern}': {matches}")
                        return
                
                print("[FAIL] Found debt/equity content but couldn't extract ratio")
            else:
                print("[FAIL] No debt/equity content found")
                
            # Show a sample of the content
            print(f"\nFirst 500 characters of content:")
            print(response.text[:500])
            
        else:
            print(f"[FAIL] Failed to access page: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"[ERROR] Error accessing screener: {e}")

if __name__ == "__main__":
    # Test with a few symbols
    test_symbols = ['RELIANCE', 'TCS', 'INFY']
    
    for symbol in test_symbols:
        print(f"\n{'='*60}")
        print(f"DEBUGGING SCREENER ACCESS FOR {symbol}")
        print(f"{'='*60}")
        debug_screener_access(symbol)
        print()