#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Enhanced Screener.in HTML Parser - Focused on 100% data extraction
Targets debt-to-equity and public holding with multiple fallback methods
"""

import requests
import re
from bs4 import BeautifulSoup
import time
import pandas as pd

class EnhancedScreenerParser:
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

    def extract_debt_to_equity(self, soup, symbol):
        """Extract debt-to-equity with multiple methods"""
        methods = [
            self._extract_de_from_ratios_table,
            self._extract_de_from_balance_sheet,
            self._extract_de_from_key_metrics,
            self._extract_de_from_text_patterns,
            self._extract_de_from_financial_section
        ]
        
        for method in methods:
            try:
                result = method(soup, symbol)
                if result and result > 0:
                    return result
            except:
                continue
        return 0

    def _extract_de_from_ratios_table(self, soup, symbol):
        """Method 1: Extract from ratios table"""
        ratios_section = soup.find('section', {'id': 'ratios'})
        if ratios_section:
            # Look for debt-to-equity in various formats
            patterns = [
                r'debt.*equity.*?(\d+\.?\d*)',
                r'debt/equity.*?(\d+\.?\d*)',
                r'd/e.*?(\d+\.?\d*)',
                r'debt.*to.*equity.*?(\d+\.?\d*)'
            ]
            text = ratios_section.get_text().lower()
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return float(match.group(1))
        return None

    def _extract_de_from_balance_sheet(self, soup, symbol):
        """Method 2: Calculate from balance sheet data"""
        # Look for balance sheet section
        balance_sheet = soup.find('section', {'id': 'balance-sheet'}) or soup.find('div', class_=re.compile('balance'))
        if balance_sheet:
            text = balance_sheet.get_text()
            # Extract total debt and equity values
            debt_match = re.search(r'total.*debt.*?(\d+\.?\d*)', text.lower())
            equity_match = re.search(r'total.*equity.*?(\d+\.?\d*)', text.lower())
            if debt_match and equity_match:
                debt = float(debt_match.group(1))
                equity = float(equity_match.group(1))
                if equity > 0:
                    return debt / equity
        return None

    def _extract_de_from_key_metrics(self, soup, symbol):
        """Method 3: Extract from key metrics section"""
        metrics = soup.find_all('div', class_=re.compile('metric|ratio|key'))
        for metric in metrics:
            text = metric.get_text().lower()
            if 'debt' in text and 'equity' in text:
                numbers = re.findall(r'(\d+\.?\d*)', text)
                if numbers:
                    return float(numbers[-1])  # Take last number found
        return None

    def _extract_de_from_text_patterns(self, soup, symbol):
        """Method 4: Search entire page for D/E patterns"""
        page_text = soup.get_text().lower()
        patterns = [
            r'debt.*equity.*ratio.*?(\d+\.?\d*)',
            r'debt.*to.*equity.*?(\d+\.?\d*)',
            r'd/e.*ratio.*?(\d+\.?\d*)',
            r'debt.*equity.*?(\d+\.?\d*)',
            r'leverage.*ratio.*?(\d+\.?\d*)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, page_text)
            if matches:
                # Return the most reasonable value (not too high)
                for match in matches:
                    val = float(match)
                    if 0 < val < 50:  # Reasonable D/E range
                        return val
        return None

    def _extract_de_from_financial_section(self, soup, symbol):
        """Method 5: Extract from financial highlights"""
        financial_sections = soup.find_all(['section', 'div'], class_=re.compile('financial|highlight|summary'))
        for section in financial_sections:
            rows = section.find_all(['tr', 'div'])
            for row in rows:
                text = row.get_text().lower()
                if 'debt' in text and ('equity' in text or 'ratio' in text):
                    numbers = re.findall(r'(\d+\.?\d*)', text)
                    if numbers:
                        val = float(numbers[-1])
                        if 0 < val < 50:
                            return val
        return None

    def extract_public_holding(self, soup, symbol):
        """Extract public holding with enhanced methods"""
        methods = [
            self._extract_ph_from_shareholding,
            self._extract_ph_from_ownership,
            self._extract_ph_from_text_patterns,
            self._extract_ph_from_tables,
            self._extract_ph_from_investor_section
        ]
        
        for method in methods:
            try:
                result = method(soup, symbol)
                if result and result > 0:
                    return result
            except:
                continue
        return 0

    def _extract_ph_from_shareholding(self, soup, symbol):
        """Method 1: Extract from shareholding pattern"""
        shareholding = soup.find('section', {'id': 'shareholding'}) or soup.find('div', class_=re.compile('shareholding|ownership'))
        if shareholding:
            # Look for public holding patterns
            patterns = [
                r'public.*?(\d+\.?\d*)%',
                r'retail.*?(\d+\.?\d*)%',
                r'individual.*?(\d+\.?\d*)%',
                r'others.*?(\d+\.?\d*)%'
            ]
            text = shareholding.get_text().lower()
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    val = float(match.group(1))
                    if 0 < val <= 100:
                        return val
        return None

    def _extract_ph_from_ownership(self, soup, symbol):
        """Method 2: Extract from ownership structure"""
        ownership_sections = soup.find_all(['section', 'div'], class_=re.compile('ownership|investor'))
        for section in ownership_sections:
            text = section.get_text().lower()
            # Look for public/retail percentages
            public_match = re.search(r'public.*?(\d+\.?\d*)%', text)
            if public_match:
                return float(public_match.group(1))
            
            # Calculate from promoter holding
            promoter_match = re.search(r'promoter.*?(\d+\.?\d*)%', text)
            if promoter_match:
                promoter = float(promoter_match.group(1))
                return 100 - promoter  # Public = 100 - Promoter
        return None

    def _extract_ph_from_text_patterns(self, soup, symbol):
        """Method 3: Search page for public holding patterns"""
        page_text = soup.get_text().lower()
        patterns = [
            r'public.*holding.*?(\d+\.?\d*)%',
            r'retail.*holding.*?(\d+\.?\d*)%',
            r'public.*share.*?(\d+\.?\d*)%',
            r'non.*promoter.*?(\d+\.?\d*)%'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, page_text)
            if match:
                val = float(match.group(1))
                if 0 < val <= 100:
                    return val
        return None

    def _extract_ph_from_tables(self, soup, symbol):
        """Method 4: Extract from data tables"""
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    header = cells[0].get_text().lower()
                    if 'public' in header or 'retail' in header:
                        value_text = cells[1].get_text()
                        numbers = re.findall(r'(\d+\.?\d*)', value_text)
                        if numbers:
                            val = float(numbers[0])
                            if 0 < val <= 100:
                                return val
        return None

    def _extract_ph_from_investor_section(self, soup, symbol):
        """Method 5: Extract from investor information"""
        investor_sections = soup.find_all(['div', 'section'], class_=re.compile('investor|share'))
        for section in investor_sections:
            # Look for percentage values near "public" keywords
            text = section.get_text()
            sentences = text.split('.')
            for sentence in sentences:
                if 'public' in sentence.lower():
                    numbers = re.findall(r'(\d+\.?\d*)%', sentence)
                    if numbers:
                        val = float(numbers[0])
                        if 0 < val <= 100:
                            return val
        return None

    def get_stock_data(self, symbol):
        """Get comprehensive stock data"""
        url = f"https://www.screener.in/company/{symbol}/"
        
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract data
            debt_to_equity = self.extract_debt_to_equity(soup, symbol)
            public_holding = self.extract_public_holding(soup, symbol)
            
            # Get company name
            title_tag = soup.find('title')
            company_name = title_tag.text.strip() if title_tag else symbol
            
            return {
                'symbol': symbol,
                'company_name': company_name,
                'debt_to_equity': debt_to_equity,
                'public_holding': public_holding,
                'success': True
            }
            
        except Exception as e:
            print(f"Error fetching {symbol}: {e}")
            return {
                'symbol': symbol,
                'company_name': symbol,
                'debt_to_equity': 0,
                'public_holding': 0,
                'success': False
            }

def test_enhanced_parser():
    """Test the enhanced parser"""
    parser = EnhancedScreenerParser()
    test_stocks = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 'SBIN', 'ITC', 'WIPRO', 'MARUTI', 'SUNPHARMA']
    
    print("ENHANCED SCREENER PARSER TEST")
    print("=" * 50)
    print(f"Testing {len(test_stocks)} stocks for 100% data extraction")
    print()
    
    results = []
    de_found = 0
    ph_found = 0
    
    for i, symbol in enumerate(test_stocks, 1):
        print(f"[{i}/{len(test_stocks)}] Testing {symbol}...")
        
        data = parser.get_stock_data(symbol)
        if data:
            results.append(data)
            if data['debt_to_equity'] > 0:
                de_found += 1
            if data['public_holding'] > 0:
                ph_found += 1
            
            print(f"  D/E: {data['debt_to_equity']}, Public: {data['public_holding']}%")
        
        time.sleep(2)  # Rate limiting
    
    print("\n" + "=" * 50)
    print("ENHANCED RESULTS")
    print("=" * 50)
    print(f"Total stocks tested: {len(results)}")
    print(f"Debt/Equity found: {de_found} ({de_found/len(results)*100:.1f}%)")
    print(f"Public holding found: {ph_found} ({ph_found/len(results)*100:.1f}%)")
    
    # Save results
    df = pd.DataFrame(results)
    filename = f"enhanced_parser_results_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(filename, index=False)
    print(f"\nResults saved to: {filename}")
    
    return results

if __name__ == "__main__":
    test_enhanced_parser()