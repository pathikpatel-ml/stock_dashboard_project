#!/usr/bin/env python
# coding: utf-8

"""
Diagnostic script to check yfinance data and screening logic
"""

import yfinance as yf
import pandas as pd
from datetime import datetime

def test_single_stock_detailed(symbol):
    """Detailed analysis of a single stock"""
    print(f"\n{'='*70}")
    print(f"DETAILED ANALYSIS: {symbol}")
    print(f"{'='*70}")
    
    ticker = yf.Ticker(f"{symbol}.NS")
    info = ticker.info
    financials = ticker.financials
    quarterly_financials = ticker.quarterly_financials
    
    print(f"\n1. BASIC INFO:")
    print(f"   Company: {info.get('longName', 'N/A')}")
    print(f"   Sector: {info.get('sector', 'N/A')}")
    print(f"   Industry: {info.get('industry', 'N/A')}")
    print(f"   Market Cap: ₹{info.get('marketCap', 0):,}")
    
    print(f"\n2. FINANCIAL RATIOS FROM INFO:")
    print(f"   ROE: {info.get('returnOnEquity', 'N/A')}")
    print(f"   ROA: {info.get('returnOnAssets', 'N/A')}")
    print(f"   Debt to Equity: {info.get('debtToEquity', 'N/A')}")
    print(f"   Profit Margins: {info.get('profitMargins', 'N/A')}")
    
    print(f"\n3. ANNUAL FINANCIALS:")
    if not financials.empty:
        print(f"   Available columns: {financials.columns.tolist()}")
        print(f"   Available rows: {financials.index.tolist()[:10]}")
        if 'Net Income' in financials.index:
            net_income = financials.loc['Net Income']
            print(f"   Net Income (latest): ₹{abs(net_income.iloc[0])/10000000:.2f} Cr")
        else:
            print("   ⚠ Net Income not found in financials")
    else:
        print("   ⚠ Annual financials not available")
    
    print(f"\n4. QUARTERLY FINANCIALS:")
    if not quarterly_financials.empty:
        print(f"   Available columns: {quarterly_financials.columns.tolist()}")
        print(f"   Available rows: {quarterly_financials.index.tolist()[:10]}")
        if 'Net Income' in quarterly_financials.index:
            quarterly_income = quarterly_financials.loc['Net Income']
            print(f"   Number of quarters available: {len(quarterly_income)}")
            print(f"   Latest quarter: ₹{abs(quarterly_income.iloc[0])/10000000:.2f} Cr")
            
            # Check quarterly trend
            if len(quarterly_income) >= 4:
                last_12 = quarterly_income.head(min(12, len(quarterly_income)))
                values = [abs(x)/10000000 for x in last_12]
                print(f"   Last 12 quarters (Cr): {[f'{v:.2f}' for v in values]}")
                print(f"   Max in 12 quarters: ₹{max(values):.2f} Cr")
                print(f"   Latest is highest: {values[0] >= max(values) * 0.95}")
        else:
            print("   ⚠ Net Income not found in quarterly financials")
    else:
        print("   ⚠ Quarterly financials not available")
    
    print(f"\n5. SCREENING CRITERIA CHECK:")
    is_bank = any(kw in info.get('sector', '').lower() + info.get('industry', '').lower() 
                  for kw in ['bank', 'finance', 'financial', 'insurance'])
    print(f"   Is Bank/Finance: {is_bank}")
    
    if is_bank:
        print(f"   Bank Criteria:")
        print(f"     - Net Profit > 1000 Cr")
        print(f"     - ROE > 10%")
    else:
        print(f"   Non-Bank Criteria:")
        print(f"     - Net Profit > 200 Cr")
        print(f"     - ROCE > 20%")
        print(f"     - Debt/Equity < 0.25")

def check_nse_stocks_availability():
    """Check how many NSE stocks are actually available on yfinance"""
    print(f"\n{'='*70}")
    print("CHECKING NSE STOCKS AVAILABILITY ON YFINANCE")
    print(f"{'='*70}")
    
    # Sample of NSE stocks
    test_stocks = [
        'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'HINDUNILVR', 'ICICIBANK', 'SBIN',
        'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT', 'ASIANPAINT', 'AXISBANK', 'MARUTI',
        'SUNPHARMA', 'ULTRACEMCO', 'TITAN', 'WIPRO', 'NESTLEIND', 'POWERGRID'
    ]
    
    available = 0
    has_financials = 0
    has_quarterly = 0
    
    for symbol in test_stocks:
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            info = ticker.info
            
            if info and 'longName' in info:
                available += 1
                
                financials = ticker.financials
                if not financials.empty and 'Net Income' in financials.index:
                    has_financials += 1
                
                quarterly = ticker.quarterly_financials
                if not quarterly.empty and 'Net Income' in quarterly.index:
                    has_quarterly += 1
                    
                print(f"✓ {symbol}: Available | Financials: {not financials.empty} | Quarterly: {not quarterly.empty}")
            else:
                print(f"✗ {symbol}: Not available")
        except Exception as e:
            print(f"✗ {symbol}: Error - {e}")
    
    print(f"\nSummary:")
    print(f"  Available on yfinance: {available}/{len(test_stocks)}")
    print(f"  Has annual financials: {has_financials}/{len(test_stocks)}")
    print(f"  Has quarterly financials: {has_quarterly}/{len(test_stocks)}")

def analyze_screening_strictness():
    """Analyze why screening might be too strict"""
    print(f"\n{'='*70}")
    print("ANALYZING SCREENING CRITERIA STRICTNESS")
    print(f"{'='*70}")
    
    test_stocks = ['RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY', 'WIPRO', 'SBIN']
    
    results = {
        'has_data': 0,
        'has_quarterly': 0,
        'highest_quarter': 0,
        'meets_profit': 0,
        'meets_roe_roce': 0,
        'meets_debt': 0,
        'passes_all': 0
    }
    
    for symbol in test_stocks:
        print(f"\n{symbol}:")
        try:
            ticker = yf.Ticker(f"{symbol}.NS")
            info = ticker.info
            financials = ticker.financials
            quarterly = ticker.quarterly_financials
            
            if not info or 'longName' not in info:
                print("  ✗ No data available")
                continue
            
            results['has_data'] += 1
            
            # Check quarterly data
            if quarterly.empty or 'Net Income' not in quarterly.index:
                print("  ✗ No quarterly financials")
                continue
            
            results['has_quarterly'] += 1
            
            # Get values
            quarterly_income = quarterly.loc['Net Income']
            latest_q = abs(quarterly_income.iloc[0]) / 10000000
            
            # Check highest quarter
            if len(quarterly_income) >= 4:
                last_12 = quarterly_income.head(min(12, len(quarterly_income)))
                max_q = max(abs(x) / 10000000 for x in last_12)
                is_highest = latest_q >= max_q * 0.95
                print(f"  Latest Q: ₹{latest_q:.2f} Cr | Max: ₹{max_q:.2f} Cr | Highest: {is_highest}")
                
                if is_highest:
                    results['highest_quarter'] += 1
                else:
                    print("  ✗ Failed: Not highest quarter")
                    continue
            else:
                print("  ✗ Failed: Less than 4 quarters data")
                continue
            
            # Check profit
            net_profit = 0
            if not financials.empty and 'Net Income' in financials.index:
                net_profit = abs(financials.loc['Net Income'].iloc[0]) / 10000000
            
            is_bank = any(kw in info.get('sector', '').lower() + info.get('industry', '').lower() 
                         for kw in ['bank', 'finance', 'financial', 'insurance'])
            
            profit_threshold = 1000 if is_bank else 200
            if net_profit > profit_threshold:
                results['meets_profit'] += 1
                print(f"  ✓ Net Profit: ₹{net_profit:.2f} Cr (>{profit_threshold})")
            else:
                print(f"  ✗ Net Profit: ₹{net_profit:.2f} Cr (<{profit_threshold})")
                continue
            
            # Check ROE/ROCE
            roe = info.get('returnOnEquity', 0) * 100
            roa = info.get('returnOnAssets', 0) * 100
            
            if is_bank:
                if roe > 10:
                    results['meets_roe_roce'] += 1
                    print(f"  ✓ ROE: {roe:.2f}% (>10%)")
                else:
                    print(f"  ✗ ROE: {roe:.2f}% (<10%)")
                    continue
            else:
                if roa > 20:
                    results['meets_roe_roce'] += 1
                    print(f"  ✓ ROCE/ROA: {roa:.2f}% (>20%)")
                else:
                    print(f"  ✗ ROCE/ROA: {roa:.2f}% (<20%)")
                    continue
            
            # Check debt
            if not is_bank:
                debt_eq = info.get('debtToEquity', 0) / 100 if info.get('debtToEquity') else 0
                if debt_eq < 0.25:
                    results['meets_debt'] += 1
                    print(f"  ✓ Debt/Equity: {debt_eq:.4f} (<0.25)")
                else:
                    print(f"  ✗ Debt/Equity: {debt_eq:.4f} (>0.25)")
                    continue
            else:
                results['meets_debt'] += 1
            
            results['passes_all'] += 1
            print(f"  ✓✓✓ PASSES ALL CRITERIA")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print(f"\n{'='*70}")
    print("SCREENING FUNNEL:")
    print(f"{'='*70}")
    print(f"Total tested: {len(test_stocks)}")
    print(f"Has data: {results['has_data']} ({results['has_data']/len(test_stocks)*100:.1f}%)")
    print(f"Has quarterly data: {results['has_quarterly']} ({results['has_quarterly']/len(test_stocks)*100:.1f}%)")
    print(f"Highest quarter: {results['highest_quarter']} ({results['highest_quarter']/len(test_stocks)*100:.1f}%)")
    print(f"Meets profit: {results['meets_profit']} ({results['meets_profit']/len(test_stocks)*100:.1f}%)")
    print(f"Meets ROE/ROCE: {results['meets_roe_roce']} ({results['meets_roe_roce']/len(test_stocks)*100:.1f}%)")
    print(f"Meets debt: {results['meets_debt']} ({results['meets_debt']/len(test_stocks)*100:.1f}%)")
    print(f"PASSES ALL: {results['passes_all']} ({results['passes_all']/len(test_stocks)*100:.1f}%)")

def main():
    print("\n" + "="*70)
    print("YFINANCE DATA DIAGNOSTIC TOOL")
    print("="*70)
    
    # Test detailed analysis
    test_single_stock_detailed('RELIANCE')
    test_single_stock_detailed('HDFCBANK')
    test_single_stock_detailed('TCS')
    
    # Check availability
    check_nse_stocks_availability()
    
    # Analyze strictness
    analyze_screening_strictness()
    
    print("\n" + "="*70)
    print("DIAGNOSTIC COMPLETE")
    print("="*70)

if __name__ == "__main__":
    main()
