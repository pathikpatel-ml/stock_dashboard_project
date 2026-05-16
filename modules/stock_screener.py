#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Stock Screener Module for Dynamic Stock Selection
Based on financial criteria for different sectors
"""

import pandas as pd
import yfinance as yf
import requests
import time
import numpy as np
from datetime import datetime, timedelta
import sys
import os
import warnings
from bs4 import BeautifulSoup
import re
from modules.nse_category_fetcher import get_nse_stock_categories
from modules.ma_calculator import calculate_moving_averages

# Suppress yfinance warnings
warnings.filterwarnings('ignore')

# Fix Windows console encoding issues
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')


FULL_UNIVERSE_FILENAME = "NSE_EQ_All_Stocks_Analysis.csv"

KNOWN_PSU_SYMBOLS = {
    'BHEL', 'BPCL', 'COALINDIA', 'CONCOR', 'GAIL', 'HAL', 'HPCL', 'HUDCO', 'IOC',
    'IRCON', 'IRCTC', 'IRFC', 'IREDA', 'LICI', 'NBCC', 'NLCINDIA', 'NMDC', 'NTPC',
    'OIL', 'ONGC', 'PFC', 'POWERGRID', 'RAILTEL', 'RCF', 'RECLTD', 'SAIL', 'SBI', 'SBIN',
    'SBICARD', 'SBILIFE', 'SCI', 'UNIONBANK'
}

PSU_NAME_KEYWORDS = (
    'bharat', 'coal india', 'grid corporation', 'government of india', 'indian oil',
    'indian railway', 'national aluminium', 'national thermal', 'nhpc', 'oil and natural gas',
    'power finance', 'power grid', 'railtel', 'rural electrification', 'shipping corporation',
    'state bank of india'
)

class StockScreener:
    def __init__(self):
        self.base_url = "https://www.screener.in/api/company/search/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def get_nse_stock_list(self):
        """Fetch comprehensive NSE stock list from NSE India website"""
        try:
            print("Fetching all NSE-listed stocks...")
            
            # Try to fetch from NSE API
            url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                from io import StringIO
                df = pd.read_csv(StringIO(response.text))
                nse_symbols = df['SYMBOL'].tolist()
                nse_symbols = [s.strip() for s in nse_symbols if isinstance(s, str)]
                print(f"Fetched {len(nse_symbols)} stocks from NSE")
                return sorted(list(set(nse_symbols)))
            except Exception:
                pass

            universe_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), FULL_UNIVERSE_FILENAME)
            if os.path.exists(universe_path):
                try:
                    universe_df = pd.read_csv(universe_path, usecols=['Symbol'])
                    nse_symbols = universe_df['Symbol'].dropna().astype(str).str.strip().unique().tolist()
                    if nse_symbols:
                        print(f"Using {len(nse_symbols)} stocks from committed universe file")
                        return sorted(nse_symbols)
                except Exception:
                    pass
            
            # Fallback: Comprehensive list of major NSE stocks
            print("Using comprehensive fallback list...")
            nse_symbols = [
                # Nifty 50
                'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'HINDUNILVR', 'ICICIBANK', 'SBIN', 'BHARTIARTL',
                'ITC', 'KOTAKBANK', 'LT', 'ASIANPAINT', 'AXISBANK', 'MARUTI', 'SUNPHARMA', 'ULTRACEMCO',
                'TITAN', 'WIPRO', 'NESTLEIND', 'POWERGRID', 'NTPC', 'BAJFINANCE', 'HCLTECH', 'COALINDIA',
                'ONGC', 'TATASTEEL', 'GRASIM', 'ADANIENT', 'JSWSTEEL', 'INDUSINDBK', 'BAJAJFINSV',
                'BAJAJ-AUTO', 'CIPLA', 'DRREDDY', 'EICHERMOT', 'GAIL', 'HEROMOTOCO', 'HINDALCO',
                'HINDPETRO', 'IBULHSGFIN', 'IOC', 'M&M', 'DIVISLAB', 'TECHM', 'TATACONSUM', 'TATAMOTORS',
                'UPL', 'VEDL', 'APOLLOHOSP', 'BRITANNIA',
                # Nifty Next 50
                'BANDHANBNK', 'BERGEPAINT', 'BOSCHLTD', 'BPCL', 'CANBK', 'CHOLAFIN', 'COLPAL', 'DABUR',
                'DALBHARAT', 'DEEPAKNTR', 'FEDERALBNK', 'GODREJCP', 'HAVELLS', 'HDFCAMC', 'HDFCLIFE',
                'ICICIPRULI', 'IDFCFIRSTB', 'IGL', 'INDIGO', 'INDUSTOWER', 'JINDALSTEL', 'JUBLFOOD',
                'LALPATHLAB', 'LUPIN', 'MARICO', 'MCDOWELL-N', 'MFSL', 'MRF', 'MUTHOOTFIN', 'NAUKRI',
                'NMDC', 'PAGEIND', 'PEL', 'PETRONET', 'PIDILITIND', 'PNB', 'RAMCOCEM', 'RBLBANK',
                'RECLTD', 'SAIL', 'SHREECEM', 'SIEMENS', 'SRF', 'SRTRANSFIN', 'TORNTPHARM', 'TRENT',
                'TVSMOTOR', 'UBL', 'VOLTAS', 'ZEEL',
                # Additional major stocks
                'ABCAPITAL', 'ABFRL', 'ACC', 'ADANIPORTS', 'ADANIPOWER', 'AJANTPHARM', 'ALKEM', 'AMBUJACEM',
                'APOLLOTYRE', 'ASHOKLEY', 'ASTRAL', 'AUBANK', 'AUROPHARMA', 'BALKRISIND', 'BALRAMCHIN',
                'BATAINDIA', 'BEL', 'BHARATFORG', 'BIOCON', 'CANFINHOME', 'CHAMBLFERT', 'COFORGE',
                'COROMANDEL', 'CROMPTON', 'CUB', 'CUMMINSIND', 'DIXON', 'DLF', 'ESCORTS', 'EXIDEIND',
                'FORTIS', 'GLENMARK', 'GMRINFRA', 'GODREJPROP', 'GUJGASLTD', 'HAL', 'ICICIGI', 'IDEA',
                'INDHOTEL', 'IRCTC', 'JKCEMENT', 'JSWENERGY', 'KAJARIACER', 'LTTS', 'MANAPPURAM',
                'MAXHEALTH', 'MPHASIS', 'NATIONALUM', 'NAVINFLUOR', 'OBEROIRLTY', 'OFSS', 'OIL',
                'PERSISTENT', 'PFIZER', 'PIIND', 'POLYCAB', 'PRESTIGE', 'PVR', 'SBILIFE', 'SHRIRAMFIN',
                'SUNTV', 'TATACHEM', 'TATACOMM', 'TATAELXSI', 'TATAPOWER', 'TORNTPOWER', 'TVSMOTOR',
                'UNIONBANK', 'WHIRLPOOL', 'ZYDUSLIFE'
            ]
            
            print(f"Using {len(nse_symbols)} stocks from fallback list")
            return sorted(list(set(nse_symbols)))
            
        except Exception as e:
            print(f"Error: {e}. Using minimal list.")
            return ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK']

    def classify_company_flags(self, symbol, company_name, sector, industry):
        symbol_upper = str(symbol).strip().upper()
        company_name_l = str(company_name).strip().lower()
        sector_l = str(sector).strip().lower()
        industry_l = str(industry).strip().lower()
        combined = f"{sector_l} {industry_l}"

        is_bank_finance = any(
            keyword in combined for keyword in ['bank', 'finance', 'financial', 'insurance', 'mutual fund', 'credit']
        )
        is_psu = (
            symbol_upper in KNOWN_PSU_SYMBOLS
            or any(keyword in company_name_l for keyword in PSU_NAME_KEYWORDS)
            or ('public sector' in combined)
        )
        return is_bank_finance, is_psu
    
    def get_screener_data(self, symbol):
        """Fetch ROCE, ROE, public holding, and D/E from Screener.in."""
        url = f"https://www.screener.in/company/{symbol}/"
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                return None
            soup = BeautifulSoup(response.content, 'html.parser')
            roce, roe     = self._parse_key_ratios_ul(soup)
            public_holding = self._parse_shareholding_latest(soup)
            debt_to_equity = self._parse_balance_sheet_de(soup)
            return {
                'roce': roce,
                'roe': roe,
                'public_holding': public_holding,
                'debt_to_equity': debt_to_equity,
            }
        except Exception as e:
            print(f"Error fetching Screener data for {symbol}: {e}")
            return None

    def _parse_key_ratios_ul(self, soup):
        """
        Parse ROCE and ROE from the company-ratios <ul> at the top of every
        Screener.in company page.  Each <li> contains two <span>s:
          <span class="name">ROCE<span ...>?</span></span>
          <span class="number">76.7 %</span>
        """
        roce = roe = 0.0
        for ul in soup.find_all('ul'):
            text = ul.get_text()
            if 'ROCE' not in text or 'ROE' not in text:
                continue
            for li in ul.find_all('li'):
                spans = li.find_all('span')
                if len(spans) < 2:
                    continue
                name = spans[0].get_text(strip=True).rstrip('?').lower().strip()
                raw  = re.sub(r'[%,\s]', '', spans[-1].get_text(strip=True))
                try:
                    val = float(raw)
                except ValueError:
                    continue
                if name == 'roce':
                    roce = val
                elif name == 'roe':
                    roe = val
            break   # only the first matching ul is the key-ratios bar
        return roce, roe

    def _parse_shareholding_latest(self, soup):
        """
        Return the LATEST quarter's 'Public' holding % from the
        #shareholding section table.  Columns go oldest → newest (left → right),
        so we iterate cells in reverse to get the most recent non-empty value.
        """
        section = soup.find('section', id='shareholding')
        if not section:
            return 0.0
        for table in section.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                label = cells[0].get_text(strip=True).lower().rstrip('+').strip()
                if label != 'public':
                    continue
                for cell in reversed(cells[1:]):
                    raw = cell.get_text(strip=True).replace('%', '').replace(',', '').strip()
                    try:
                        val = float(raw)
                        if 0 < val <= 100:
                            return val
                    except ValueError:
                        continue
        return 0.0

    def _parse_balance_sheet_de(self, soup):
        """
        Calculate D/E from the Screener.in balance sheet section:
          D/E = Borrowings / (Share Capital + Reserves)
        Uses the latest (rightmost) column values.
        """
        section = soup.find('section', id='balance-sheet')
        if not section:
            return 0.0

        def latest_positive(cells):
            for cell in reversed(cells[1:]):
                raw = cell.get_text(strip=True).replace(',', '').strip()
                try:
                    v = float(raw)
                    if v > 0:
                        return v
                except ValueError:
                    continue
            return None

        borrowings = share_capital = reserves = None
        for table in section.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                label = cells[0].get_text(strip=True).lower().strip()
                if 'borrowing' in label and borrowings is None:
                    borrowings = latest_positive(cells) or 0.0
                elif label in ('share capital', 'equity share capital') and share_capital is None:
                    share_capital = latest_positive(cells) or 0.0
                elif label in ('reserves', 'reserves & surplus', 'other equity') and reserves is None:
                    reserves = latest_positive(cells) or 0.0

        equity = (share_capital or 0.0) + (reserves or 0.0)
        if equity > 0 and borrowings is not None:
            return round(borrowings / equity, 4)
        return 0.0

    def get_financial_data(self, symbol, max_retries=3):
        """Get financial data for a stock using yfinance with retry logic"""
        for attempt in range(max_retries + 1):
            try:
                # Configure yfinance session with timeout
                ticker = yf.Ticker(f"{symbol}.NS")
                if hasattr(ticker, 'session'):
                    ticker.session.timeout = 10  # Reduced timeout to 10 seconds
                
                # Get financial data with timeout handling
                info = ticker.info
                financials = ticker.financials
                quarterly_financials = ticker.quarterly_financials
            
                # Extract key metrics
                data = {
                    'symbol': symbol,
                    'company_name': info.get('longName', symbol),
                    'sector': info.get('sector', 'Unknown'),
                    'industry': info.get('industry', 'Unknown'),
                    'market_cap': info.get('marketCap', 0),
                    'net_profit': 0,
                    'roce': 0,
                    'roe': 0,
                    'debt_to_equity': 0,
                    'latest_quarter_profit': 0,
                    'last_3q_profits': [],
                    'public_holding': info.get('floatShares', 0) / info.get('sharesOutstanding', 1) * 100 if info.get('sharesOutstanding') else 0,
                    'is_bank_finance': False,
                    'is_psu': False
                }
                
                # Determine if it's a bank/finance company
                sector = data['sector'].lower()
                industry = data['industry'].lower()
                company_name = data['company_name'].lower()
                
                data['is_bank_finance'], data['is_psu'] = self.classify_company_flags(
                    symbol=symbol,
                    company_name=data['company_name'],
                    sector=data['sector'],
                    industry=data['industry'],
                )
                
                # Get net profit (annual) - try multiple possible row names
                net_profit_rows = ['Net Income', 'Net Income From Continuing Operation Net Minority Interest', 'Normalized Income']
                for row_name in net_profit_rows:
                    if not financials.empty and row_name in financials.index:
                        net_profit_series = financials.loc[row_name]
                        if not net_profit_series.empty and not pd.isna(net_profit_series.iloc[0]):
                            data['net_profit'] = abs(net_profit_series.iloc[0]) / 10000000  # Convert to crores
                            break
                
                # Get latest quarter profit and last 3 quarters individual profits
                quarterly_profit_rows = ['Net Income', 'Net Income From Continuing Operation Net Minority Interest', 'Normalized Income']
                quarterly_profits = []
                
                for row_name in quarterly_profit_rows:
                    if not quarterly_financials.empty and row_name in quarterly_financials.index:
                        quarterly_profit_series = quarterly_financials.loc[row_name]
                        if not quarterly_profit_series.empty:
                            # Get up to 4 quarters (current + last 3)
                            for i in range(min(4, len(quarterly_profit_series))):
                                if not pd.isna(quarterly_profit_series.iloc[i]):
                                    quarterly_profits.append(abs(quarterly_profit_series.iloc[i]) / 10000000)
                            break
                
                # Set latest quarter profit and store last 3 quarters as list
                if quarterly_profits:
                    data['latest_quarter_profit'] = quarterly_profits[0]  # Most recent quarter
                    if len(quarterly_profits) >= 4:
                        # Store last 3 quarters (excluding current quarter 0)
                        data['last_3q_profits'] = quarterly_profits[1:4]
                    else:
                        # If less than 4 quarters available, use available data
                        data['last_3q_profits'] = quarterly_profits[1:] if len(quarterly_profits) > 1 else []
                else:
                    data['last_3q_profits'] = []
                
                # ROE: yfinance as initial value (Screener.in overrides below)
                roe_yf = info.get('returnOnEquity')
                data['roe']  = round(roe_yf * 100, 2) if roe_yf is not None else 0.0
                data['roce'] = 0.0  # Set authoritatively from Screener.in below

                # D/E fallback from yfinance (stored as ratio × 100 in yfinance)
                yf_de_raw = info.get('debtToEquity')
                yf_debt_to_equity = round(yf_de_raw / 100, 4) if yf_de_raw else 0.0

                # Screener.in is the authoritative source for ROCE, ROE, public holding, D/E
                screener_data = self.get_screener_data(symbol)
                if screener_data:
                    if screener_data.get('roce', 0) > 0:
                        data['roce'] = screener_data['roce']
                    if screener_data.get('roe', 0) > 0:
                        data['roe'] = screener_data['roe']
                    if screener_data.get('public_holding', 0) > 0:
                        data['public_holding'] = screener_data['public_holding']
                    sc_de = screener_data.get('debt_to_equity', 0)
                    data['debt_to_equity'] = sc_de if sc_de > 0 else yf_debt_to_equity
                else:
                    data['debt_to_equity'] = yf_debt_to_equity
                
                return data
            
            except Exception as e:
                if attempt < max_retries:
                    print(f"\nAttempt {attempt + 1} failed for {symbol}, retrying in 3 seconds...")
                    time.sleep(3)  # Increased wait before retry
                    continue
                else:
                    print(f"\nSkipping {symbol} after {max_retries + 1} attempts: {str(e)[:100]}")
                    return None
        
        return None
    
    def check_existing_comprehensive_data(self):
        """Check if there's a recent comprehensive CSV file (within 1 week) with correct format"""
        try:
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
            if not os.path.exists(output_dir):
                return None
            
            # Find all comprehensive CSV files
            csv_files = [f for f in os.listdir(output_dir) if f.startswith('comprehensive_stock_analysis_') and f.endswith('.csv')]
            
            if not csv_files:
                return None
            
            # Get the most recent file
            latest_file = sorted(csv_files)[-1]
            file_path = os.path.join(output_dir, latest_file)
            
            # Check file age
            file_time = os.path.getmtime(file_path)
            current_time = time.time()
            age_days = (current_time - file_time) / (24 * 3600)
            
            if age_days <= 7:  # Within 1 week
                # Verify the CSV has the correct format (new column structure)
                try:
                    df_check = pd.read_csv(file_path, nrows=1)
                    if 'Last 3Q Profits (Cr)' in df_check.columns:
                        print(f"Found recent comprehensive data: {latest_file} (Age: {age_days:.1f} days)")
                        return file_path
                    else:
                        print(f"Existing data has old format. Will fetch fresh data.")
                        return None
                except:
                    return None
            else:
                print(f"Existing comprehensive data is too old: {age_days:.1f} days")
                return None
                
        except Exception as e:
            print(f"Error checking existing data: {e}")
            return None
    
    def load_existing_comprehensive_data(self, file_path):
        """Load existing comprehensive CSV data"""
        try:
            df = pd.read_csv(file_path)
            print(f"Loaded {len(df)} stocks from existing comprehensive data")
            return df
        except Exception as e:
            print(f"Error loading existing data: {e}")
            return None
    
    def _save_checkpoint(self, all_processed_stocks, processed_count, final=False):
        """Save checkpoint data"""
        try:
            if all_processed_stocks:
                all_df = pd.DataFrame(all_processed_stocks)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                
                if final:
                    filename = f'interrupted_stock_analysis_{timestamp}.csv'
                    print(f"\nSaving interrupted progress...")
                else:
                    filename = f'checkpoint_stock_analysis_{processed_count}_{timestamp}.csv'
                    print(f"\nCheckpoint: Saved progress for {processed_count} stocks")
                
                output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
                os.makedirs(output_dir, exist_ok=True)
                
                filepath = os.path.join(output_dir, filename)
                all_df.to_csv(filepath, index=False)
                
                if final:
                    print(f"Progress saved to: {filepath}")
                    
        except Exception as e:
            print(f"Error saving checkpoint: {e}")
    
    def apply_screening_criteria(self, stock_data):
        """Apply screening criteria based on sector"""
        if not stock_data:
            return False
        
        try:
            if stock_data.get('is_psu'):
                return False

            if stock_data['is_bank_finance']:
                # Bank and Finance criteria
                # Net profit > 1000 cr, ROE > 10%
                return (stock_data['net_profit'] > 1000 and 
                       stock_data['roe'] > 10)
            else:
                # Non-PSU non-financial criteria
                last_3q = stock_data.get('last_3q_profits', [])
                profit_exceeds_all_quarters = all(stock_data['net_profit'] > q_profit for q_profit in last_3q) if last_3q else False
                
                base_criteria = (stock_data['net_profit'] > 200 and 
                               stock_data['roce'] > 20 and
                               profit_exceeds_all_quarters)
                enhanced_criteria = stock_data['public_holding'] < 30
                return base_criteria and enhanced_criteria
                       
        except Exception as e:
            print(f"Error applying criteria: {e}")
            return False
    
    def screen_stocks(self, checkpoint_interval=50):
        """Main screening function with checkpoint system"""
        print("Starting stock screening process...")
        
        # Check for existing comprehensive data first
        existing_data_path = self.check_existing_comprehensive_data()
        if existing_data_path:
            print("Using existing comprehensive data...")
            all_df = self.load_existing_comprehensive_data(existing_data_path)
            if all_df is not None:
                # Re-apply screening criteria to existing data
                screened_stocks = []
                for _, row in all_df.iterrows():
                    stock_data = {
                        'symbol': row['Symbol'],
                        'company_name': row['Company Name'],
                        'sector': row['Sector'],
                        'industry': row['Industry'],
                        'market_cap': row['Market Cap'],
                        'net_profit': row['Net Profit (Cr)'],
                        'roce': row['ROCE (%)'],
                        'roe': row['ROE (%)'],
                        'debt_to_equity': row['Debt to Equity'],
                        'latest_quarter_profit': row['Latest Quarter Profit (Cr)'],
                        'last_3q_profits': [float(x.strip()) for x in str(row['Last 3Q Profits (Cr)']).split(',') if x.strip() and x.strip() != 'N/A'] if pd.notna(row['Last 3Q Profits (Cr)']) and str(row['Last 3Q Profits (Cr)']) != 'N/A' else [],
                        'public_holding': row['Public Holding (%)'],
                        'is_bank_finance': row['Is Bank/Finance'],
                        'is_psu': row['Is PSU']
                    }
                    
                    if self.apply_screening_criteria(stock_data):
                        screened_stocks.append({
                            'Symbol': stock_data['symbol'],
                            'Company Name': stock_data['company_name'],
                            'Sector': stock_data['sector'],
                            'Industry': stock_data['industry'],
                            'Market Cap': stock_data['market_cap'],
                            'Net Profit (Cr)': stock_data['net_profit'],
                            'ROCE (%)': stock_data['roce'],
                            'ROE (%)': stock_data['roe'],
                            'Debt to Equity': stock_data['debt_to_equity'],
                            'Latest Quarter Profit (Cr)': stock_data['latest_quarter_profit'],
                            'Last 3Q Profits (Cr)': ', '.join([str(round(q, 2)) for q in stock_data.get('last_3q_profits', [])]) if stock_data.get('last_3q_profits') else 'N/A',
                            'Public Holding (%)': stock_data['public_holding'],
                            'Is Bank/Finance': stock_data['is_bank_finance'],
                            'Is PSU': stock_data['is_psu'],
                            'Screening Date': datetime.now().strftime('%Y-%m-%d')
                        })
                
                print(f"Found {len(screened_stocks)} stocks meeting updated criteria from existing data.")
                return pd.DataFrame(screened_stocks)
        
        # If no existing data or loading failed, proceed with fresh screening
        
        # Get NSE stock list
        nse_symbols = self.get_nse_stock_list()
        if not nse_symbols:
            print("Failed to get NSE stock list")
            return pd.DataFrame()
        
        screened_stocks = []
        all_processed_stocks = []  # Store ALL stocks with their data
        total_stocks = len(nse_symbols)
        
        print(f"Screening {total_stocks} stocks...")
        print(f"Progress will be saved every {checkpoint_interval} stocks")
        
        for i, symbol in enumerate(nse_symbols):
            try:
                sys.stdout.write(f"\rProcessing [{i+1}/{total_stocks}] {symbol} ({((i+1)/total_stocks)*100:.1f}%)")
                sys.stdout.flush()
                
                # Get financial data
                stock_data = self.get_financial_data(symbol)
                
                if stock_data:
                    # Add screening result to the data
                    passes_criteria = self.apply_screening_criteria(stock_data)
                    
                    # Store ALL stocks with complete data
                    all_stock_record = {
                        'Symbol': stock_data['symbol'],
                        'Company Name': stock_data['company_name'],
                        'Sector': stock_data['sector'],
                        'Industry': stock_data['industry'],
                        'Market Cap': stock_data['market_cap'],
                        'Net Profit (Cr)': round(stock_data['net_profit'], 2),
                        'ROCE (%)': round(stock_data['roce'], 2),
                        'ROE (%)': round(stock_data['roe'], 2),
                        'Debt to Equity': round(stock_data['debt_to_equity'], 4),
                        'Latest Quarter Profit (Cr)': round(stock_data['latest_quarter_profit'], 2),
                        'Last 3Q Profits (Cr)': ', '.join([str(round(q, 2)) for q in stock_data.get('last_3q_profits', [])]) if stock_data.get('last_3q_profits') else 'N/A',
                        'Public Holding (%)': round(stock_data['public_holding'], 2),
                        'Is Bank/Finance': stock_data['is_bank_finance'],
                        'Is PSU': stock_data['is_psu'],
                        'Passes Criteria': passes_criteria,
                        'Screening Date': datetime.now().strftime('%Y-%m-%d')
                    }
                    all_processed_stocks.append(all_stock_record)
                    
                    # Only add to screened_stocks if it passes criteria
                    if passes_criteria:
                        screened_stocks.append({
                            'Symbol': stock_data['symbol'],
                            'Company Name': stock_data['company_name'],
                            'Sector': stock_data['sector'],
                            'Industry': stock_data['industry'],
                            'Market Cap': stock_data['market_cap'],
                            'Net Profit (Cr)': round(stock_data['net_profit'], 2),
                            'ROCE (%)': round(stock_data['roce'], 2),
                            'ROE (%)': round(stock_data['roe'], 2),
                            'Debt to Equity': round(stock_data['debt_to_equity'], 4),
                            'Latest Quarter Profit (Cr)': round(stock_data['latest_quarter_profit'], 2),
                            'Last 3Q Profits (Cr)': ', '.join([str(round(q, 2)) for q in stock_data.get('last_3q_profits', [])]) if stock_data.get('last_3q_profits') else 'N/A',
                            'Public Holding (%)': round(stock_data['public_holding'], 2),
                            'Is Bank/Finance': stock_data['is_bank_finance'],
                            'Is PSU': stock_data['is_psu'],
                            'Screening Date': datetime.now().strftime('%Y-%m-%d')
                        })
                
                # Save checkpoint every N stocks
                if (i + 1) % checkpoint_interval == 0 and all_processed_stocks:
                    self._save_checkpoint(all_processed_stocks, i + 1)
                
                # Rate limiting to avoid overwhelming Screener.in
                time.sleep(1.5)  # Increased delay for Screener.in requests
                
            except KeyboardInterrupt:
                print(f"\n\nScript interrupted by user at {symbol}")
                print(f"Processed {len(all_processed_stocks)} stocks so far")
                if all_processed_stocks:
                    self._save_checkpoint(all_processed_stocks, i + 1, final=True)
                break
            except Exception as e:
                print(f"\nError processing {symbol}: {str(e)[:100]}")
                continue
        
        print(f"\n\nScreening completed. Found {len(screened_stocks)} stocks meeting criteria.")
        
        # Save ALL processed stocks to comprehensive CSV
        if all_processed_stocks:
            all_df = pd.DataFrame(all_processed_stocks)
            all_df = all_df.sort_values('Market Cap', ascending=False)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            comprehensive_filename = f'comprehensive_stock_analysis_{timestamp}.csv'
            
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
            os.makedirs(output_dir, exist_ok=True)
            
            comprehensive_filepath = os.path.join(output_dir, comprehensive_filename)
            all_df.to_csv(comprehensive_filepath, index=False)
            print(f"\nCOMPREHENSIVE DATA saved to: {comprehensive_filepath}")
            print(f"Total stocks analyzed: {len(all_processed_stocks)}")
            print(f"Stocks passing criteria: {len(screened_stocks)}")
            print(f"Success rate: {(len(screened_stocks)/len(all_processed_stocks))*100:.2f}%")
        
        # Convert to DataFrame for regular processing
        df = pd.DataFrame(screened_stocks)
        
        if not df.empty:
            # Sort by market cap descending
            df = df.sort_values('Market Cap', ascending=False)
            
            # Save to CSV with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'screened_stocks_{timestamp}.csv'
            
            # Create output directory if it doesn't exist
            output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
            os.makedirs(output_dir, exist_ok=True)
            
            filepath = os.path.join(output_dir, filename)
            df.to_csv(filepath, index=False)
            print(f"Results saved to: {filepath}")
            
            # Display summary
            print("\n=== SCREENING SUMMARY ===")
            print(f"Total stocks screened: {total_stocks}")
            print(f"Stocks meeting criteria: {len(screened_stocks)}")
            print(f"Success rate: {(len(screened_stocks)/total_stocks)*100:.2f}%")
            
            # Show sector breakdown
            if 'Sector' in df.columns:
                print("\nSector breakdown:")
                sector_counts = df['Sector'].value_counts()
                for sector, count in sector_counts.items():
                    print(f"  {sector}: {count}")
            
            # Show top 10 by market cap
            print("\nTop 10 stocks by Market Cap:")
            top_10 = df.head(10)[['Symbol', 'Company Name', 'Market Cap', 'Net Profit (Cr)']]
            print(top_10.to_string(index=False))
        
        return df
    
    def analyze_comprehensive_data(self, csv_file_path):
        """Analyze comprehensive stock data from CSV file"""
        try:
            df = pd.read_csv(csv_file_path)
            
            print(f"\n=== COMPREHENSIVE DATA ANALYSIS ===")
            print(f"Total stocks analyzed: {len(df)}")
            print(f"Stocks passing criteria: {df['Passes Criteria'].sum()}")
            print(f"Success rate: {(df['Passes Criteria'].sum()/len(df))*100:.2f}%")
            
            # Sector analysis
            print("\nSector breakdown:")
            sector_counts = df['Sector'].value_counts()
            for sector, count in sector_counts.head(10).items():
                passed = df[(df['Sector'] == sector) & (df['Passes Criteria'])].shape[0]
                print(f"  {sector}: {count} total, {passed} passed ({(passed/count)*100:.1f}%)")
            
            # Top performers
            passed_stocks = df[df['Passes Criteria']].sort_values('Market Cap', ascending=False)
            if not passed_stocks.empty:
                print(f"\nTop 10 stocks that passed criteria:")
                for idx, row in passed_stocks.head(10).iterrows():
                    print(f"  {row['Symbol']} - {row['Company Name']} (Market Cap: {row['Market Cap']:,.0f})")
            
            return df
            
        except Exception as e:
            print(f"Error analyzing data: {e}")
            return None
    
    def get_stock_recommendations(self, max_stocks=20):
        """Get stock recommendations based on screening criteria"""
        df = self.screen_stocks()
        
        if df.empty:
            print("No stocks found meeting the criteria.")
            return df
        
        # Limit to max_stocks
        recommendations = df.head(max_stocks)
        
        print(f"\n=== TOP {len(recommendations)} STOCK RECOMMENDATIONS ===")
        for idx, row in recommendations.iterrows():
            print(f"\n{idx+1}. {row['Symbol']} - {row['Company Name']}")
            print(f"   Sector: {row['Sector']}")
            print(f"   Market Cap: Rs.{row['Market Cap']:,.0f}")
            print(f"   Net Profit: Rs.{row['Net Profit (Cr)']} Cr")
            if row['Is Bank/Finance']:
                print(f"   ROE: {row['ROE (%)']}%")
            else:
                print(f"   ROCE: {row['ROCE (%)']}%")
                print(f"   Debt/Equity: {row['Debt to Equity']}")
        
        return recommendations


def add_moving_averages_to_stocks(df):
    """
    Add moving averages to stock dataframe
    """
    if df.empty:
        return df
    
    df_with_ma = df.copy()
    ma_columns = ['MA10', 'MA50', 'MA100', 'MA200']
    
    # Initialize MA columns
    for col in ma_columns:
        df_with_ma[col] = np.nan
    if 'Current_Price' not in df_with_ma.columns:
        df_with_ma['Current_Price'] = np.nan
    
    symbols = df_with_ma['Symbol'].dropna().astype(str).str.upper().str.strip().tolist()
    symbol_to_indices = {}
    for idx, symbol in zip(df_with_ma.index, symbols):
        symbol_to_indices.setdefault(symbol, []).append(idx)

    batch_size = 100
    total_batches = max(1, (len(symbol_to_indices) + batch_size - 1) // batch_size)
    print(f"Calculating moving averages for all stocks in {total_batches} batches...")

    unique_symbols = list(symbol_to_indices.keys())
    for batch_num, start in enumerate(range(0, len(unique_symbols), batch_size), start=1):
        batch_symbols = unique_symbols[start:start + batch_size]
        print(
            f"MA batch {batch_num}/{total_batches}: "
            f"processing {len(batch_symbols)} symbols "
            f"({start + 1}-{start + len(batch_symbols)} of {len(unique_symbols)})"
        )
        ticker_symbols = [f"{symbol}.NS" for symbol in batch_symbols]

        try:
            batch_data = yf.download(
                tickers=ticker_symbols,
                period="1y",
                auto_adjust=False,
                progress=False,
                group_by="ticker",
                threads=True,
            )
        except Exception as e:
            print(f"Error downloading MA batch {batch_num}: {e}")
            continue

        if batch_data is None or batch_data.empty:
            continue

        for symbol in batch_symbols:
            ticker_symbol = f"{symbol}.NS"
            try:
                price_frame = None
                if isinstance(batch_data.columns, pd.MultiIndex):
                    try:
                        price_frame = batch_data[ticker_symbol]
                    except KeyError:
                        price_frame = None
                elif len(batch_symbols) == 1:
                    price_frame = batch_data

                if price_frame is None or 'Close' not in price_frame.columns:
                    continue

                close_series = pd.to_numeric(price_frame['Close'], errors='coerce').dropna()
                if close_series.empty:
                    continue

                ma_values = {
                    'Current_Price': round(close_series.iloc[-1], 2),
                }
                for period in [10, 50, 100, 200]:
                    if len(close_series) >= period:
                        ma_values[f'MA{period}'] = round(close_series.rolling(window=period).mean().iloc[-1], 2)

                for idx in symbol_to_indices.get(symbol, []):
                    for key, value in ma_values.items():
                        df_with_ma.loc[idx, key] = value
            except Exception as e:
                print(f"Error calculating MA for {symbol}: {e}")
                continue
    
    return df_with_ma

def add_nse_categories_to_stocks(df):
    """
    Add NSE category information to stocks
    """
    if df.empty:
        return df
    
    try:
        categories_data = get_nse_stock_categories()
        df_with_categories = df.copy()
        df_with_categories['NSE_Categories'] = ''
        
        for idx, row in df_with_categories.iterrows():
            symbol = row['Symbol']
            if symbol in categories_data:
                df_with_categories.loc[idx, 'NSE_Categories'] = ','.join(categories_data[symbol])
        
        return df_with_categories
    except Exception as e:
        print(f"Error adding NSE categories: {e}")
        return df

def get_current_market_price(symbol):
    """
    Get current market price for a symbol
    """
    try:
        ticker = yf.Ticker(f"{symbol}.NS")
        data = ticker.history(period="2d")
        if not data.empty:
            return data['Close'].iloc[-1]
    except Exception as e:
        print(f"Error fetching price for {symbol}: {e}")
    return None
    """Main function to run the stock screener"""
    screener = StockScreener()
    
    print("Stock Screener - Dynamic Stock Selection")
    print("=======================================")
    print("\nCriteria:")
    print("- Bank/Finance: Net profit > Rs.1000 Cr, ROE > 10%")
    print("- Private Sector: Net profit > Rs.200 Cr, ROCE > 20%, Net profit > Each of Last 3Q")
    print("  + Enhanced: Public Holding < 30%")
    print("- PSU Sector: Excluded from shortlist")
    print("\nStarting screening process...\n")
    
    try:
        recommendations = screener.get_stock_recommendations(max_stocks=20)
        
        if not recommendations.empty:
            print("\n" + "="*50)
            print("Screening completed successfully!")
            print(f"Found {len(recommendations)} recommended stocks.")
            print("Check the output folder for detailed CSV report.")
        else:
            print("\nNo stocks found meeting the criteria.")
            print("Consider adjusting the screening parameters.")
            
    except KeyboardInterrupt:
        print("\n\nScreening interrupted by user.")
    except Exception as e:
        print(f"\nError during screening: {e}")
        print("Please check your internet connection and try again.")


if __name__ == "__main__":
    main()
