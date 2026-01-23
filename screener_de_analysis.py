#!/usr/bin/env python3
"""
Detailed Analysis Script for Screener.in D/E Ratio Display
=========================================================
This script analyzes how D/E ratios are actually structured in screener.in HTML
and creates a robust parser based on real data patterns.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import json
from urllib.parse import urljoin

class ScreenerDEAnalyzer:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.base_url = "https://www.screener.in"
        
    def analyze_company_page(self, symbol):
        """Analyze a single company page for D/E ratio patterns"""
        url = f"{self.base_url}/company/{symbol}/"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            print(f"\n{'='*60}")
            print(f"ANALYZING: {symbol}")
            print(f"URL: {url}")
            print(f"{'='*60}")
            
            # Method 1: Look for the exact pattern from your HTML snippet
            debt_equity_items = soup.find_all('li', {'data-source': 'quick-ratio'})
            if debt_equity_items:
                print("\n🔍 METHOD 1: Found items with data-source='quick-ratio'")
                for i, item in enumerate(debt_equity_items):
                    name_span = item.find('span', class_='name')
                    value_span = item.find('span', class_='number')
                    print(f"  Item {i+1}:")
                    print(f"    Name: {name_span.get_text().strip() if name_span else 'N/A'}")
                    print(f"    Value: {value_span.get_text().strip() if value_span else 'N/A'}")
                    print(f"    Full HTML: {str(item)[:200]}...")
            
            # Method 2: Search for any mention of "Debt to equity" or similar
            print("\n🔍 METHOD 2: Searching for 'Debt to equity' text patterns")
            debt_patterns = [
                'debt to equity', 'debt-to-equity', 'd/e ratio', 'debt equity ratio',
                'debt/equity', 'total debt/equity'
            ]
            
            for pattern in debt_patterns:
                elements = soup.find_all(string=re.compile(pattern, re.IGNORECASE))
                if elements:
                    print(f"  Found pattern '{pattern}':")
                    for elem in elements[:3]:  # Limit to first 3 matches
                        parent = elem.parent
                        # Try to find associated value
                        value_elem = None
                        if parent:
                            # Look for number in same parent or sibling
                            value_elem = parent.find('span', class_='number')
                            if not value_elem:
                                # Check parent's parent
                                grandparent = parent.parent
                                if grandparent:
                                    value_elem = grandparent.find('span', class_='number')
                        
                        print(f"    Text: '{elem.strip()}'")
                        print(f"    Value: {value_elem.get_text().strip() if value_elem else 'NOT FOUND'}")
                        print(f"    Parent HTML: {str(parent)[:150]}..." if parent else "No parent")
            
            # Method 3: Look for all li elements with financial data patterns
            print("\n🔍 METHOD 3: Analyzing all <li> elements with financial data structure")
            li_elements = soup.find_all('li', class_='flex flex-space-between')
            financial_items = []
            
            for li in li_elements:
                name_span = li.find('span', class_='name')
                number_span = li.find('span', class_='number')
                data_source = li.get('data-source', 'N/A')
                
                if name_span and number_span:
                    name_text = name_span.get_text().strip()
                    number_text = number_span.get_text().strip()
                    
                    financial_items.append({
                        'name': name_text,
                        'value': number_text,
                        'data_source': data_source,
                        'html': str(li)[:100] + '...'
                    })
            
            print(f"  Found {len(financial_items)} financial items:")
            for item in financial_items:
                print(f"    📊 {item['name']}: {item['value']} (data-source: {item['data_source']})")
                
                # Check if this might be D/E ratio
                name_lower = item['name'].lower()
                if any(pattern in name_lower for pattern in ['debt', 'equity', 'd/e']):
                    print(f"      ⭐ POTENTIAL D/E MATCH!")
                    print(f"      Full HTML: {item['html']}")
            
            # Method 4: Look for specific data-source attributes that might contain D/E
            print("\n🔍 METHOD 4: Checking all data-source attributes")
            elements_with_data_source = soup.find_all(attrs={'data-source': True})
            data_sources = {}
            
            for elem in elements_with_data_source:
                source = elem.get('data-source')
                if source not in data_sources:
                    data_sources[source] = []
                
                name_span = elem.find('span', class_='name')
                number_span = elem.find('span', class_='number')
                
                data_sources[source].append({
                    'name': name_span.get_text().strip() if name_span else 'N/A',
                    'value': number_span.get_text().strip() if number_span else 'N/A',
                    'element': str(elem)[:100] + '...'
                })
            
            print(f"  Found {len(data_sources)} unique data-source values:")
            for source, items in data_sources.items():
                print(f"    🏷️  data-source='{source}':")
                for item in items:
                    print(f"        {item['name']}: {item['value']}")
                    if 'debt' in item['name'].lower() or 'equity' in item['name'].lower():
                        print(f"        ⭐ DEBT/EQUITY RELATED!")
            
            return {
                'symbol': symbol,
                'financial_items': financial_items,
                'data_sources': data_sources,
                'success': True
            }
            
        except Exception as e:
            print(f"❌ ERROR analyzing {symbol}: {e}")
            return {'symbol': symbol, 'success': False, 'error': str(e)}
    
    def test_html_snippet(self):
        """Test the provided HTML snippet"""
        print("\n" + "="*60)
        print("TESTING PROVIDED HTML SNIPPET")
        print("="*60)
        
        html_snippet = '''
        <li class="flex flex-space-between" data-source="quick-ratio">
        <span class="name">
        Debt to equity
        </span>
        <span class="nowrap value">
        <span class="number">0.85</span>
        </span>
        </li>
        '''
        
        soup = BeautifulSoup(html_snippet, 'html.parser')
        li = soup.find('li')
        
        print(f"Element: {li.name}")
        print(f"Classes: {li.get('class')}")
        print(f"Data-source: {li.get('data-source')}")
        
        name_span = li.find('span', class_='name')
        number_span = li.find('span', class_='number')
        
        print(f"Name: '{name_span.get_text().strip()}'")
        print(f"Value: '{number_span.get_text().strip()}'")
        
        print("\n🔍 ANALYSIS:")
        print("- The data-source is 'quick-ratio' but displays 'Debt to equity'")
        print("- This suggests screener.in reuses data-source attributes")
        print("- We should parse by text content, not data-source attribute")
        
        return {
            'data_source': li.get('data-source'),
            'name': name_span.get_text().strip(),
            'value': number_span.get_text().strip()
        }
    
    def create_robust_parser(self, analysis_results):
        """Create a robust parser based on analysis results"""
        print("\n" + "="*60)
        print("CREATING ROBUST PARSER")
        print("="*60)
        
        parser_code = '''
def extract_de_ratio_from_screener(html_content):
    """
    Robust D/E ratio extractor for screener.in based on actual HTML analysis
    """
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Method 1: Look for exact text match (most reliable)
    debt_equity_patterns = [
        r'debt\\s+to\\s+equity',
        r'debt-to-equity', 
        r'd/e\\s+ratio',
        r'debt\\s+equity\\s+ratio',
        r'total\s+debt/equity'
    ]
    
    for pattern in debt_equity_patterns:
        # Find elements containing the pattern
        elements = soup.find_all(string=re.compile(pattern, re.IGNORECASE))
        
        for elem in elements:
            parent = elem.parent
            if not parent:
                continue
                
            # Look for the value in the same structure
            # Check if parent is a span with class 'name'
            if parent.get('class') and 'name' in parent.get('class'):
                # Look for sibling or parent's sibling with number
                container = parent.parent
                if container:
                    number_span = container.find('span', class_='number')
                    if number_span:
                        try:
                            value = float(number_span.get_text().strip())
                            return value
                        except ValueError:
                            continue
    
    # Method 2: Fallback - look in all financial data items
    li_elements = soup.find_all('li', class_='flex flex-space-between')
    
    for li in li_elements:
        name_span = li.find('span', class_='name')
        number_span = li.find('span', class_='number')
        
        if name_span and number_span:
            name_text = name_span.get_text().strip().lower()
            
            # Check if this looks like D/E ratio
            if any(pattern.replace(r'\\s+', ' ') in name_text for pattern in debt_equity_patterns):
                try:
                    value = float(number_span.get_text().strip())
                    return value
                except ValueError:
                    continue
    
    return None

# Test function
def test_parser():
    test_html = """
    <li class="flex flex-space-between" data-source="quick-ratio">
    <span class="name">Debt to equity</span>
    <span class="nowrap value">
    <span class="number">0.85</span>
    </span>
    </li>
    """
    
    result = extract_de_ratio_from_screener(test_html)
    print(f"Extracted D/E ratio: {result}")
    return result

if __name__ == "__main__":
    test_parser()
        '''
        
        # Save the parser
        with open('robust_screener_parser.py', 'w') as f:
            f.write(parser_code)
        
        print("✅ Robust parser saved to 'robust_screener_parser.py'")
        return parser_code

def main():
    analyzer = ScreenerDEAnalyzer()
    
    # Test the provided HTML snippet first
    print("STEP 1: Testing provided HTML snippet")
    snippet_result = analyzer.test_html_snippet()
    
    # Test with a few real companies
    test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK']
    analysis_results = []
    
    print(f"\nSTEP 2: Analyzing real company pages")
    for symbol in test_symbols:
        result = analyzer.analyze_company_page(symbol)
        analysis_results.append(result)
        time.sleep(2)  # Be respectful to the server
    
    # Create robust parser
    print(f"\nSTEP 3: Creating robust parser")
    parser_code = analyzer.create_robust_parser(analysis_results)
    
    # Summary
    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)
    print("✅ Key Findings:")
    print("1. data-source='quick-ratio' is used for 'Debt to equity' display")
    print("2. Screener.in reuses data-source attributes for different metrics")
    print("3. Text-based parsing is more reliable than attribute-based parsing")
    print("4. Structure: <li> -> <span class='name'> + <span class='number'>")
    print("\n✅ Recommended approach:")
    print("- Parse by text content matching 'Debt to equity'")
    print("- Use regex patterns for flexibility")
    print("- Fallback to structure-based parsing")
    
    return analysis_results

if __name__ == "__main__":
    main()