#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Comprehensive Test for Screener.in HTML Parsing
Extract accurate debt-to-equity and public holding data
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import pandas as pd
from datetime import datetime
import json

class ScreenerHTMLParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def extract_financial_data_from_html(self, symbol, max_retries=3):
        """Extract financial data from Screener.in HTML"""
        url = f"https://www.screener.in/company/{symbol}/"
        
        for attempt in range(max_retries):
            try:
                print(f"\nAttempt {attempt + 1}: Fetching {symbol} from {url}")
                
                response = self.session.get(url, timeout=15)
                print(f"Response status: {response.status_code}")
                
                if response.status_code != 200:
                    print(f"HTTP Error: {response.status_code}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    return None
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Initialize data structure
                data = {
                    'symbol': symbol,
                    'company_name': 'N/A',
                    'debt_to_equity': 0,
                    'public_holding': 0,
                    'market_cap': 0,
                    'pe_ratio': 0,
                    'book_value': 0,
                    'dividend_yield': 0,
                    'roce': 0,
                    'roe': 0,
                    'net_profit': 0,
                    'sales': 0,
                    'parsing_success': False,
                    'data_sources': []
                }
                
                # Extract company name
                try:
                    title_tag = soup.find('title')
                    if title_tag:
                        title_text = title_tag.get_text()
                        # Extract company name from title (format: "Company Name Share Price | Screener")
                        if '|' in title_text:
                            data['company_name'] = title_text.split('|')[0].replace('Share Price', '').strip()
                        data['data_sources'].append('title')
                except:
                    pass
                
                # Method 1: Extract from ratios table
                print("Method 1: Searching ratios table...")
                ratios_section = soup.find('section', {'id': 'ratios'})
                if ratios_section:
                    print("Found ratios section")
                    
                    # Look for debt to equity in ratios table
                    debt_equity_patterns = [
                        'Debt to equity',
                        'Debt/Equity',
                        'D/E Ratio',
                        'Debt-to-Equity'
                    ]
                    
                    for pattern in debt_equity_patterns:
                        debt_row = ratios_section.find('li', string=re.compile(pattern, re.IGNORECASE))
                        if not debt_row:
                            # Try finding in span or other elements
                            debt_row = ratios_section.find(string=re.compile(pattern, re.IGNORECASE))
                            if debt_row:
                                debt_row = debt_row.parent
                        
                        if debt_row:
                            print(f"Found debt-to-equity row with pattern: {pattern}")
                            # Look for the value in the same row or next sibling
                            value_span = debt_row.find_next('span', class_='number')
                            if value_span:
                                debt_text = value_span.get_text().strip()
                                debt_value = self._parse_number(debt_text)
                                if debt_value is not None:
                                    data['debt_to_equity'] = debt_value
                                    data['data_sources'].append(f'ratios_table_{pattern}')
                                    print(f"Extracted D/E from ratios: {debt_value}")
                                    break
                
                # Method 2: Extract from peer comparison table
                print("Method 2: Searching peer comparison...")
                peer_table = soup.find('table', class_='data-table')
                if peer_table:
                    print("Found peer comparison table")
                    headers = peer_table.find('thead')
                    if headers:
                        header_cells = headers.find_all('th')
                        debt_col_idx = None
                        
                        for idx, header in enumerate(header_cells):
                            header_text = header.get_text().strip().lower()
                            if any(term in header_text for term in ['debt', 'equity', 'd/e']):
                                debt_col_idx = idx
                                print(f"Found D/E column at index {idx}: {header_text}")
                                break
                        
                        if debt_col_idx is not None:
                            tbody = peer_table.find('tbody')
                            if tbody:
                                first_row = tbody.find('tr')
                                if first_row:
                                    cells = first_row.find_all('td')
                                    if len(cells) > debt_col_idx:
                                        debt_text = cells[debt_col_idx].get_text().strip()
                                        debt_value = self._parse_number(debt_text)
                                        if debt_value is not None and data['debt_to_equity'] == 0:
                                            data['debt_to_equity'] = debt_value
                                            data['data_sources'].append('peer_table')
                                            print(f"Extracted D/E from peer table: {debt_value}")
                
                # Method 3: Extract from shareholding pattern
                print("Method 3: Searching shareholding pattern...")
                shareholding_patterns = [
                    'Public',
                    'Retail',
                    'Individual',
                    'Non-promoter'
                ]
                
                # Look for shareholding section
                shareholding_section = soup.find('section', {'id': 'shareholding'})
                if not shareholding_section:
                    # Try alternative selectors
                    shareholding_section = soup.find('div', class_=re.compile('shareholding', re.IGNORECASE))
                
                if shareholding_section:
                    print("Found shareholding section")
                    
                    # Look for public holding percentage
                    for pattern in shareholding_patterns:
                        public_element = shareholding_section.find(string=re.compile(pattern, re.IGNORECASE))
                        if public_element:
                            print(f"Found public holding element with pattern: {pattern}")
                            # Look for percentage in nearby elements
                            parent = public_element.parent
                            for _ in range(3):  # Check parent and grandparents
                                if parent:
                                    # Look for percentage in the same element or siblings
                                    percentage_text = parent.get_text()
                                    percentage_match = re.search(r'(\d+\.?\d*)%', percentage_text)
                                    if percentage_match:
                                        public_holding = float(percentage_match.group(1))
                                        if 10 <= public_holding <= 100:  # Reasonable range
                                            data['public_holding'] = public_holding
                                            data['data_sources'].append(f'shareholding_{pattern}')
                                            print(f"Extracted public holding: {public_holding}%")
                                            break
                                    parent = parent.parent
                            if data['public_holding'] > 0:
                                break
                
                # Method 4: Extract from key metrics/highlights
                print("Method 4: Searching key metrics...")
                highlights = soup.find_all('div', class_=re.compile('highlight|metric|key', re.IGNORECASE))
                for highlight in highlights:
                    text = highlight.get_text().lower()
                    
                    # Look for debt to equity
                    if 'debt' in text and 'equity' in text and data['debt_to_equity'] == 0:
                        debt_match = re.search(r'(\d+\.?\d*)', text)
                        if debt_match:
                            debt_value = float(debt_match.group(1))
                            if 0 <= debt_value <= 10:  # Reasonable D/E range
                                data['debt_to_equity'] = debt_value
                                data['data_sources'].append('highlights_debt')
                                print(f"Extracted D/E from highlights: {debt_value}")
                    
                    # Look for public holding
                    if 'public' in text and '%' in text and data['public_holding'] == 0:
                        public_match = re.search(r'(\d+\.?\d*)%', text)
                        if public_match:
                            public_holding = float(public_match.group(1))
                            if 10 <= public_holding <= 100:
                                data['public_holding'] = public_holding
                                data['data_sources'].append('highlights_public')
                                print(f"Extracted public holding from highlights: {public_holding}%")
                
                # Method 5: Extract additional financial metrics
                print("Method 5: Extracting additional metrics...")
                
                # Market cap
                market_cap_element = soup.find(string=re.compile('Market Cap', re.IGNORECASE))
                if market_cap_element:
                    parent = market_cap_element.parent
                    for _ in range(3):
                        if parent:
                            text = parent.get_text()
                            # Look for crore values
                            crore_match = re.search(r'(\d+,?\d*\.?\d*)\s*Cr', text, re.IGNORECASE)
                            if crore_match:
                                market_cap_text = crore_match.group(1).replace(',', '')
                                try:
                                    data['market_cap'] = float(market_cap_text) * 10000000  # Convert crores to actual value
                                    data['data_sources'].append('market_cap')
                                    print(f"Extracted market cap: {data['market_cap']}")
                                    break
                                except:
                                    pass
                            parent = parent.parent
                
                # PE Ratio
                pe_element = soup.find(string=re.compile('P/E|PE Ratio', re.IGNORECASE))
                if pe_element:
                    parent = pe_element.parent
                    for _ in range(3):
                        if parent:
                            pe_match = re.search(r'(\d+\.?\d*)', parent.get_text())
                            if pe_match:
                                pe_value = float(pe_match.group(1))
                                if 1 <= pe_value <= 1000:  # Reasonable PE range
                                    data['pe_ratio'] = pe_value
                                    data['data_sources'].append('pe_ratio')
                                    print(f"Extracted PE ratio: {pe_value}")
                                    break
                            parent = parent.parent
                
                # ROCE and ROE
                for metric in ['ROCE', 'ROE']:
                    metric_element = soup.find(string=re.compile(metric, re.IGNORECASE))
                    if metric_element:
                        parent = metric_element.parent
                        for _ in range(3):
                            if parent:
                                metric_match = re.search(r'(\d+\.?\d*)%?', parent.get_text())
                                if metric_match:
                                    metric_value = float(metric_match.group(1))
                                    if -100 <= metric_value <= 200:  # Reasonable range
                                        data[metric.lower()] = metric_value
                                        data['data_sources'].append(metric.lower())
                                        print(f"Extracted {metric}: {metric_value}%")
                                        break
                                parent = parent.parent
                
                # Check if we got meaningful data
                if data['debt_to_equity'] > 0 or data['public_holding'] > 0 or len(data['data_sources']) > 1:
                    data['parsing_success'] = True
                
                print(f"Parsing result for {symbol}:")
                print(f"  Company: {data['company_name']}")
                print(f"  Debt/Equity: {data['debt_to_equity']}")
                print(f"  Public Holding: {data['public_holding']}%")
                print(f"  Market Cap: {data['market_cap']}")
                print(f"  Data sources: {data['data_sources']}")
                print(f"  Success: {data['parsing_success']}")
                
                return data
                
            except requests.exceptions.RequestException as e:
                print(f"Request error for {symbol}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
            except Exception as e:
                print(f"Parsing error for {symbol}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
        
        print(f"Failed to extract data for {symbol} after {max_retries} attempts")
        return None
    
    def _parse_number(self, text):
        """Parse number from text, handling various formats"""
        if not text:
            return None
        
        try:
            # Remove common non-numeric characters
            cleaned = re.sub(r'[^\d.-]', '', text.strip())
            if cleaned and cleaned != '-':
                return float(cleaned)
        except:
            pass
        
        return None
    
    def test_multiple_stocks(self, symbols, delay=2):
        """Test parsing for multiple stocks"""
        results = []
        
        print(f"Testing HTML parsing for {len(symbols)} stocks...")
        print("=" * 60)
        
        for i, symbol in enumerate(symbols):
            print(f"\n[{i+1}/{len(symbols)}] Testing {symbol}")
            print("-" * 40)
            
            data = self.extract_financial_data_from_html(symbol)
            if data:
                results.append(data)
            
            # Rate limiting
            if i < len(symbols) - 1:
                print(f"Waiting {delay} seconds before next request...")
                time.sleep(delay)
        
        return results
    
    def analyze_results(self, results):
        """Analyze parsing results"""
        if not results:
            print("No results to analyze")
            return
        
        print("\n" + "=" * 60)
        print("PARSING ANALYSIS RESULTS")
        print("=" * 60)
        
        total_stocks = len(results)
        successful_parses = sum(1 for r in results if r['parsing_success'])
        debt_equity_found = sum(1 for r in results if r['debt_to_equity'] > 0)
        public_holding_found = sum(1 for r in results if r['public_holding'] > 0)
        
        print(f"Total stocks tested: {total_stocks}")
        print(f"Successful parses: {successful_parses} ({successful_parses/total_stocks*100:.1f}%)")
        print(f"Debt/Equity found: {debt_equity_found} ({debt_equity_found/total_stocks*100:.1f}%)")
        print(f"Public holding found: {public_holding_found} ({public_holding_found/total_stocks*100:.1f}%)")
        
        # Data source analysis
        all_sources = []
        for result in results:
            all_sources.extend(result['data_sources'])
        
        if all_sources:
            print(f"\nData source frequency:")
            source_counts = {}
            for source in all_sources:
                source_counts[source] = source_counts.get(source, 0) + 1
            
            for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
                print(f"  {source}: {count}")
        
        # Show successful extractions
        print(f"\nSuccessful extractions:")
        for result in results:
            if result['parsing_success']:
                print(f"  {result['symbol']}: D/E={result['debt_to_equity']}, Public={result['public_holding']}%, Sources={result['data_sources']}")
        
        # Save results to CSV
        df = pd.DataFrame(results)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'screener_html_test_results_{timestamp}.csv'
        df.to_csv(filename, index=False)
        print(f"\nResults saved to: {filename}")
        
        return df

def main():
    """Main test function"""
    parser = ScreenerHTMLParser()
    
    # Test with a variety of stocks
    test_symbols = [
        'RELIANCE',    # Large cap
        'TCS',         # IT sector
        'HDFCBANK',    # Banking
        'INFY',        # IT
        'ICICIBANK',   # Banking
        'SBIN',        # PSU Bank
        'ITC',         # FMCG
        'WIPRO',       # IT
        'MARUTI',      # Auto
        'SUNPHARMA'    # Pharma
    ]
    
    print("SCREENER.IN HTML PARSER COMPREHENSIVE TEST")
    print("=" * 50)
    print(f"Testing with {len(test_symbols)} stocks")
    print("This will test debt-to-equity and public holding extraction")
    print("\nStarting test...")
    
    # Run the test
    results = parser.test_multiple_stocks(test_symbols, delay=3)
    
    # Analyze results
    if results:
        df = parser.analyze_results(results)
        
        print("\n" + "=" * 50)
        print("TEST COMPLETED")
        print("=" * 50)
        print("Check the CSV file for detailed results")
        print("If successful, this parsing method can replace yfinance for D/E and public holding")
    else:
        print("No results obtained. Check internet connection and try again.")

if __name__ == "__main__":
    main()