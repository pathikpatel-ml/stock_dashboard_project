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

# Fix Windows console encoding issues
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

class StockScreener:
    def __init__(self):
        self.base_url = "https://www.screener.in/api/company/search/"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
    def get_nse_stock_list(self):
        """Fetch comprehensive NSE stock list from NSE India website"""
        try:
            print("Fetching all NSE-listed stocks...")
            
            # Try to fetch from NSE API
            url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
            headers = {'User-Agent': 'Mozilla/5.0'}
            
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    from io import StringIO
                    df = pd.read_csv(StringIO(response.text))
                    nse_symbols = df['SYMBOL'].tolist()
                    nse_symbols = [s.strip() for s in nse_symbols if isinstance(s, str)]
                    print(f"Fetched {len(nse_symbols)} stocks from NSE")
                    return sorted(list(set(nse_symbols)))
            except:
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
    
    def get_financial_data(self, symbol):
        """Get financial data for a stock using yfinance"""
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            
            # Get financial data
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
                'public_holding': info.get('floatShares', 0) / info.get('sharesOutstanding', 1) * 100 if info.get('sharesOutstanding') else 0,
                'is_bank_finance': False,
                'is_psu': False
            }
            
            # Determine if it's a bank/finance company
            sector = data['sector'].lower()
            industry = data['industry'].lower()
            company_name = data['company_name'].lower()
            
            data['is_bank_finance'] = any(keyword in sector + industry for keyword in 
                                        ['bank', 'finance', 'financial', 'insurance', 'mutual fund'])
            
            # Determine if it's a PSU (Public Sector Undertaking)
            psu_keywords = ['bharat', 'indian', 'national', 'state bank', 'oil india', 'coal india', 
                           'ntpc', 'ongc', 'sail', 'bhel', 'gail', 'ioc', 'bpcl', 'hpcl']
            data['is_psu'] = any(keyword in company_name for keyword in psu_keywords) or \
                            any(keyword in symbol.lower() for keyword in ['sbi', 'pnb', 'boi', 'canara'])
            
            # Get net profit (annual)
            if not financials.empty and 'Net Income' in financials.index:
                net_profit_series = financials.loc['Net Income']
                if not net_profit_series.empty:
                    data['net_profit'] = abs(net_profit_series.iloc[0]) / 10000000  # Convert to crores
            
            # Get latest quarter profit
            if not quarterly_financials.empty and 'Net Income' in quarterly_financials.index:
                quarterly_profit_series = quarterly_financials.loc['Net Income']
                if not quarterly_profit_series.empty:
                    data['latest_quarter_profit'] = abs(quarterly_profit_series.iloc[0]) / 10000000  # Convert to crores
                    
                    # Check if latest quarter is highest in last 12 quarters
                    if len(quarterly_profit_series) >= 4:
                        last_12_quarters = quarterly_profit_series.head(min(12, len(quarterly_profit_series)))
                        max_quarter = max(abs(x) / 10000000 for x in last_12_quarters)
                        data['is_highest_quarter'] = data['latest_quarter_profit'] >= max_quarter * 0.95
                    else:
                        data['is_highest_quarter'] = False
            
            # Calculate ROCE and ROE from info
            data['roce'] = info.get('returnOnAssets', 0) * 100  # Approximate ROCE with ROA
            data['roe'] = info.get('returnOnEquity', 0) * 100
            
            # Get debt to equity ratio
            data['debt_to_equity'] = info.get('debtToEquity', 0) / 100 if info.get('debtToEquity') else 0
            
            return data
            
        except Exception as e:
            print(f"Error getting financial data for {symbol}: {e}")
            return None
    
    def apply_screening_criteria(self, stock_data):
        """Apply screening criteria based on sector"""
        if not stock_data:
            return False
        
        try:
            # Check if latest quarter profit is highest in last 12 quarters
            if not stock_data.get('is_highest_quarter', False):
                return False
            
            if stock_data['is_bank_finance']:
                # Bank and Finance criteria
                # Net profit > 1000 cr, ROE > 10%
                return (stock_data['net_profit'] > 1000 and 
                       stock_data['roe'] > 10)
            else:
                # Private sector criteria: Net profit > 200 cr, ROCE > 20%, Debt to Equity < 0.25%, Public holding < 30%
                # PSU criteria: Net profit > 200 cr, ROCE > 20%, Debt to Equity < 0.25% (no public holding requirement)
                base_criteria = (stock_data['net_profit'] > 200 and 
                               stock_data['roce'] > 20 and 
                               stock_data['debt_to_equity'] < 0.0025)
                
                if stock_data['is_psu']:
                    return base_criteria
                else:
                    # Private sector - additional public holding criteria
                    return base_criteria and stock_data['public_holding'] < 30
                       
        except Exception as e:
            print(f"Error applying criteria: {e}")
            return False
    
    def screen_stocks(self):
        """Main screening function"""
        print("Starting stock screening process...")
        
        # Get NSE stock list
        nse_symbols = self.get_nse_stock_list()
        if not nse_symbols:
            print("Failed to get NSE stock list")
            return pd.DataFrame()
        
        screened_stocks = []
        total_stocks = len(nse_symbols)
        
        print(f"Screening {total_stocks} stocks...")
        
        for i, symbol in enumerate(nse_symbols):
            try:
                sys.stdout.write(f"\rProcessing [{i+1}/{total_stocks}] {symbol} ({((i+1)/total_stocks)*100:.1f}%)")
                sys.stdout.flush()
                
                # Get financial data
                stock_data = self.get_financial_data(symbol)
                
                if stock_data and self.apply_screening_criteria(stock_data):
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
                        'Public Holding (%)': round(stock_data['public_holding'], 2),
                        'Is Bank/Finance': stock_data['is_bank_finance'],
                        'Is PSU': stock_data['is_psu'],
                        'Screening Date': datetime.now().strftime('%Y-%m-%d')
                    })
                
                # Rate limiting to avoid overwhelming the API
                time.sleep(0.1)
                
            except Exception as e:
                print(f"\nError processing {symbol}: {e}")
                continue
        
        print(f"\n\nScreening completed. Found {len(screened_stocks)} stocks meeting criteria.")
        
        # Convert to DataFrame
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


def main():
    """Main function to run the stock screener"""
    screener = StockScreener()
    
    print("Stock Screener - Dynamic Stock Selection")
    print("=======================================")
    print("\nCriteria:")
    print("- Latest quarter profit should be highest in last 12 quarters")
    print("- Bank/Finance: Net profit > Rs.1000 Cr, ROE > 10%")
    print("- Private Sector: Net profit > Rs.200 Cr, ROCE > 20%, Debt/Equity < 0.25, Public holding > 30%")
    print("- PSU: Net profit > Rs.200 Cr, ROCE > 20%, Debt/Equity < 0.25")
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