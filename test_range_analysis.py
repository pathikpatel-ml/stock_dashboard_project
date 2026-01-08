#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script to analyze stocks in range 0-200 and understand why they don't meet criteria
"""

import sys
import os
import time
import pandas as pd
from datetime import datetime
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def test_stock_range(start_idx=0, end_idx=50):  # Reduced default range
    """Test stocks in a specific range and analyze why they fail criteria"""
    print(f"Stock Range Analysis: {start_idx} to {end_idx}")
    print("=" * 60)
    
    screener = StockScreener()
    
    # Get NSE stock list
    print("Fetching NSE stock list...")
    nse_stocks = screener.get_nse_stock_list()
    
    if not nse_stocks:
        print("Failed to fetch NSE stocks")
        return
    
    print(f"Total NSE stocks: {len(nse_stocks)}")
    
    # Get stocks in range
    test_stocks = nse_stocks[start_idx:end_idx]
    print(f"Testing {len(test_stocks)} stocks from {test_stocks[0]} to {test_stocks[-1]}")
    
    results = []
    failed_fetches = 0
    start_time = time.time()
    
    for i, symbol in enumerate(test_stocks):
        elapsed = time.time() - start_time
        eta = (elapsed / (i + 1)) * (len(test_stocks) - i - 1) if i > 0 else 0
        print(f"\n[{i+1}/{len(test_stocks)}] Processing {symbol} ({((i+1)/len(test_stocks))*100:.1f}%) - ETA: {eta/60:.1f}min")
        
        try:
            # Add timeout wrapper
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("API call timed out")
            
            # Set timeout for 15 seconds
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(15)
            
            try:
                stock_data = screener.get_financial_data(symbol, max_retries=1)  # Reduced retries
            finally:
                signal.alarm(0)  # Cancel timeout
            
            if stock_data:
                # Add missing field
                stock_data['is_highest_quarter'] = stock_data['latest_quarter_profit'] > stock_data['net_profit'] / 4
                
                passes_criteria = screener.apply_screening_criteria(stock_data)
                
                result = {
                    'Symbol': symbol,
                    'Company': stock_data['company_name'],
                    'Sector': stock_data['sector'],
                    'Industry': stock_data['industry'],
                    'Market_Cap': stock_data['market_cap'],
                    'Net_Profit_Cr': round(stock_data['net_profit'], 2),
                    'ROCE_Pct': round(stock_data['roce'], 2),
                    'ROE_Pct': round(stock_data['roe'], 2),
                    'Debt_to_Equity': round(stock_data['debt_to_equity'], 4),
                    'Latest_Q_Profit_Cr': round(stock_data['latest_quarter_profit'], 2),
                    'Public_Holding_Pct': round(stock_data['public_holding'], 2),
                    'Is_Bank_Finance': stock_data['is_bank_finance'],
                    'Is_PSU': stock_data['is_psu'],
                    'Is_Highest_Quarter': stock_data['is_highest_quarter'],
                    'Passes_Criteria': passes_criteria
                }
                
                results.append(result)
                
                # Show why it failed if it didn't pass
                if not passes_criteria:
                    print(f"  FAILED - Analyzing why:")
                    analyze_failure_reason(result)
                else:
                    print(f"  PASSED - {result['Company']}")
                    
            else:
                failed_fetches += 1
                print(f"  FAILED to fetch data")
                
        except TimeoutError:
            failed_fetches += 1
            print(f"  TIMEOUT - Skipping {symbol}")
        except Exception as e:
            failed_fetches += 1
            print(f"  ERROR: {str(e)[:100]}")
        
        # Reduced rate limiting
        time.sleep(0.1)
    
    # Analysis
    print("\\n" + "=" * 60)
    print("ANALYSIS RESULTS")
    print("=" * 60)
    
    if results:
        passing_stocks = [r for r in results if r['Passes_Criteria']]
        
        print(f"Total stocks processed: {len(results)}")
        print(f"Failed API calls: {failed_fetches}")
        print(f"Stocks passing criteria: {len(passing_stocks)}")
        print(f"Success rate: {(len(passing_stocks)/len(results))*100:.2f}%")
        
        # Detailed failure analysis
        analyze_failure_patterns(results)
        
        # Save results
        save_analysis_results(results, start_idx, end_idx)
        
    else:
        print("No results to analyze")

def analyze_failure_reason(stock_data):
    """Analyze why a specific stock failed the criteria"""
    if stock_data['Is_Bank_Finance']:
        # Bank/Finance criteria
        net_profit_ok = stock_data['Net_Profit_Cr'] > 1000
        roe_ok = stock_data['ROE_Pct'] > 10
        highest_quarter_ok = stock_data['Is_Highest_Quarter']
        
        print(f"    Bank/Finance Stock:")
        print(f"    - Net Profit > 1000 Cr: {'✓' if net_profit_ok else '✗'} ({stock_data['Net_Profit_Cr']} Cr)")
        print(f"    - ROE > 10%: {'✓' if roe_ok else '✗'} ({stock_data['ROE_Pct']}%)")
        print(f"    - Highest Quarter: {'✓' if highest_quarter_ok else '✗'}")
        
    else:
        # Non-bank criteria
        net_profit_ok = stock_data['Net_Profit_Cr'] > 200
        roce_ok = stock_data['ROCE_Pct'] > 20
        debt_ok = stock_data['Debt_to_Equity'] < 0.25
        highest_quarter_ok = stock_data['Is_Highest_Quarter']
        
        print(f"    Non-Bank Stock:")
        print(f"    - Net Profit > 200 Cr: {'✓' if net_profit_ok else '✗'} ({stock_data['Net_Profit_Cr']} Cr)")
        print(f"    - ROCE > 20%: {'✓' if roce_ok else '✗'} ({stock_data['ROCE_Pct']}%)")
        print(f"    - Debt/Equity < 0.25: {'✓' if debt_ok else '✗'} ({stock_data['Debt_to_Equity']})")
        print(f"    - Highest Quarter: {'✓' if highest_quarter_ok else '✗'}")
        
        if not stock_data['Is_PSU']:
            public_holding_ok = stock_data['Public_Holding_Pct'] > 30
            print(f"    - Public Holding > 30%: {'✓' if public_holding_ok else '✗'} ({stock_data['Public_Holding_Pct']}%)")

def analyze_failure_patterns(results):
    """Analyze common patterns in why stocks fail"""
    print("\\nFAILURE PATTERN ANALYSIS:")
    print("-" * 40)
    
    failed_stocks = [r for r in results if not r['Passes_Criteria']]
    
    if not failed_stocks:
        print("No failed stocks to analyze")
        return
    
    # Count failure reasons
    failure_reasons = {
        'low_net_profit': 0,
        'low_roce': 0,
        'low_roe': 0,
        'high_debt': 0,
        'low_public_holding': 0,
        'not_highest_quarter': 0
    }
    
    for stock in failed_stocks:
        if stock['Is_Bank_Finance']:
            if stock['Net_Profit_Cr'] <= 1000:
                failure_reasons['low_net_profit'] += 1
            if stock['ROE_Pct'] <= 10:
                failure_reasons['low_roe'] += 1
        else:
            if stock['Net_Profit_Cr'] <= 200:
                failure_reasons['low_net_profit'] += 1
            if stock['ROCE_Pct'] <= 20:
                failure_reasons['low_roce'] += 1
            if stock['Debt_to_Equity'] >= 0.25:
                failure_reasons['high_debt'] += 1
            if not stock['Is_PSU'] and stock['Public_Holding_Pct'] <= 30:
                failure_reasons['low_public_holding'] += 1
        
        if not stock['Is_Highest_Quarter']:
            failure_reasons['not_highest_quarter'] += 1
    
    print(f"Common failure reasons (out of {len(failed_stocks)} failed stocks):")
    for reason, count in failure_reasons.items():
        if count > 0:
            pct = (count / len(failed_stocks)) * 100
            print(f"  - {reason.replace('_', ' ').title()}: {count} ({pct:.1f}%)")
    
    # Sector analysis
    print("\\nSECTOR ANALYSIS:")
    print("-" * 20)
    sectors = {}
    for stock in results:
        sector = stock['Sector']
        if sector not in sectors:
            sectors[sector] = {'total': 0, 'passed': 0}
        sectors[sector]['total'] += 1
        if stock['Passes_Criteria']:
            sectors[sector]['passed'] += 1
    
    for sector, data in sorted(sectors.items(), key=lambda x: x[1]['total'], reverse=True):
        if data['total'] > 1:  # Only show sectors with multiple stocks
            rate = (data['passed'] / data['total']) * 100
            print(f"  {sector}: {data['passed']}/{data['total']} ({rate:.1f}%)")

def save_analysis_results(results, start_idx, end_idx):
    """Save analysis results to CSV"""
    if not results:
        return
    
    df = pd.DataFrame(results)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'range_analysis_{start_idx}_{end_idx}_{timestamp}.csv'
    
    output_dir = os.path.join(os.path.dirname(__file__), 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, filename)
    df.to_csv(filepath, index=False)
    
    print(f"\\nResults saved to: {filepath}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Test stock range analysis')
    parser.add_argument('--start', type=int, default=0, help='Start index (default: 0)')
    parser.add_argument('--end', type=int, default=50, help='End index (default: 50)')
    parser.add_argument('--quick', action='store_true', help='Quick test with first 10 stocks')
    
    args = parser.parse_args()
    
    if args.quick:
        print("Running quick test with first 10 stocks...")
        test_stock_range(0, 10)
    else:
        test_stock_range(args.start, args.end)