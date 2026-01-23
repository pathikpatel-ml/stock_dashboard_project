import requests
import yfinance as yf
import pandas as pd
from bs4 import BeautifulSoup
import re
import time
from datetime import datetime

class EnhancedDEParser:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract_de_from_screener(self, symbol):
        """Enhanced D/E extraction matching actual screener.in HTML structure"""
        try:
            url = f"https://www.screener.in/company/{symbol}/consolidated/"
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                return None
                
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Method 1: Look for li elements with "Debt to equity" (actual structure)
            debt_equity_items = soup.find_all('li', class_='flex flex-space-between')
            for item in debt_equity_items:
                name_span = item.find('span', class_='name')
                if name_span and 'debt to equity' in name_span.get_text().lower().strip():
                    value_span = item.find('span', class_='number')
                    if value_span:
                        try:
                            return float(value_span.get_text().strip())
                        except ValueError:
                            continue
            
            # Method 2: Look for any li with data-source containing debt/equity
            for item in debt_equity_items:
                data_source = item.get('data-source', '')
                if 'debt' in data_source.lower() or 'equity' in data_source.lower():
                    name_span = item.find('span', class_='name')
                    if name_span and 'debt' in name_span.get_text().lower():
                        value_span = item.find('span', class_='number')
                        if value_span:
                            try:
                                return float(value_span.get_text().strip())
                            except ValueError:
                                continue
            
            # Method 3: Look in tables for debt to equity
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        if 'debt' in label and ('equity' in label or 'capital' in label):
                            value_text = cells[1].get_text(strip=True)
                            numbers = re.findall(r'([0-9]+\.?[0-9]*)', value_text)
                            if numbers:
                                return float(numbers[0])
                
        except Exception as e:
            print(f"Screener error for {symbol}: {e}")
        
        return None
    
    def extract_de_from_yfinance(self, symbol):
        """Fallback D/E extraction from yfinance"""
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            info = ticker.info
            
            # Try different D/E ratio keys
            de_keys = ['debtToEquity', 'totalDebtToEquity', 'debt_to_equity']
            for key in de_keys:
                if key in info and info[key] is not None:
                    return float(info[key])
            
            # Calculate from balance sheet if available
            try:
                bs = ticker.balance_sheet
                if not bs.empty and len(bs.columns) > 0:
                    latest = bs.iloc[:, 0]  # Most recent quarter
                    
                    # Look for debt items
                    debt_items = ['Total Debt', 'Long Term Debt', 'Short Long Term Debt', 'Current Debt']
                    total_debt = 0
                    for item in debt_items:
                        if item in latest.index:
                            total_debt += latest[item] if pd.notna(latest[item]) else 0
                    
                    # Look for equity
                    equity_items = ['Total Stockholder Equity', 'Stockholders Equity']
                    total_equity = 0
                    for item in equity_items:
                        if item in latest.index:
                            total_equity = latest[item] if pd.notna(latest[item]) else 0
                            break
                    
                    if total_debt > 0 and total_equity > 0:
                        return round(total_debt / total_equity, 2)
            except:
                pass
                
        except Exception as e:
            print(f"YFinance error for {symbol}: {e}")
        
        return None
    
    def get_debt_to_equity(self, symbol):
        """Get D/E with screener primary, yfinance fallback"""
        # Try screener first
        de_ratio = self.extract_de_from_screener(symbol)
        if de_ratio is not None:
            return de_ratio, 'screener'
        
        # Fallback to yfinance
        de_ratio = self.extract_de_from_yfinance(symbol)
        if de_ratio is not None:
            return de_ratio, 'yfinance'
        
        return None, 'failed'

def test_enhanced_de_parser():
    """Test the enhanced D/E parser"""
    test_stocks = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
                   'SBIN', 'ITC', 'WIPRO', 'MARUTI', 'SUNPHARMA',
                   'ADANIPORTS', 'ASIANPAINT', 'AXISBANK', 'BAJFINANCE', 'BHARTIARTL']
    
    parser = EnhancedDEParser()
    results = []
    
    print("ENHANCED DEBT-TO-EQUITY PARSER TEST")
    print("=" * 50)
    print(f"Testing {len(test_stocks)} stocks for improved D/E extraction\n")
    
    screener_success = 0
    yfinance_success = 0
    total_success = 0
    
    for i, symbol in enumerate(test_stocks, 1):
        print(f"[{i}/{len(test_stocks)}] Testing {symbol}...")
        
        de_ratio, source = parser.get_debt_to_equity(symbol)
        
        if de_ratio is not None:
            total_success += 1
            if source == 'screener':
                screener_success += 1
            elif source == 'yfinance':
                yfinance_success += 1
            print(f"  D/E: {de_ratio} (source: {source})")
        else:
            print(f"  D/E: Not found")
        
        results.append({
            'Symbol': symbol,
            'Debt_to_Equity': de_ratio,
            'Source': source
        })
        
        time.sleep(0.5)  # Rate limiting
    
    # Save results
    df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"enhanced_de_results_{timestamp}.csv"
    df.to_csv(filename, index=False)
    
    print("\n" + "=" * 50)
    print("ENHANCED D/E EXTRACTION RESULTS")
    print("=" * 50)
    print(f"Total stocks tested: {len(test_stocks)}")
    print(f"Screener.in success: {screener_success} ({screener_success/len(test_stocks)*100:.1f}%)")
    print(f"YFinance fallback: {yfinance_success} ({yfinance_success/len(test_stocks)*100:.1f}%)")
    print(f"Total success rate: {total_success} ({total_success/len(test_stocks)*100:.1f}%)")
    print(f"\nResults saved to: {filename}")
    
    return df

if __name__ == "__main__":
    test_enhanced_de_parser()