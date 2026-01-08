#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Analyze what criteria are blocking private companies from qualifying
"""

import pandas as pd
import os

def analyze_screening_criteria():
    """Analyze comprehensive data to see what's blocking private companies"""
    
    # Load the comprehensive CSV
    csv_path = os.path.join('output', 'comprehensive_stock_analysis_20260108_165913.csv')
    
    if not os.path.exists(csv_path):
        print("Comprehensive CSV not found!")
        return
    
    df = pd.read_csv(csv_path)
    print(f"Total stocks analyzed: {len(df)}")
    
    # Separate by company type
    banks = df[df['Is Bank/Finance'] == True]
    non_banks = df[df['Is Bank/Finance'] == False]
    private_companies = non_banks[non_banks['Is PSU'] == False]
    psu_companies = non_banks[non_banks['Is PSU'] == True]
    
    print(f"\nBreakdown:")
    print(f"Banks/Finance: {len(banks)}")
    print(f"Private Companies: {len(private_companies)}")
    print(f"PSU Companies: {len(psu_companies)}")
    
    # Check what's passing
    banks_passing = banks[banks['Passes Criteria'] == True]
    private_passing = private_companies[private_companies['Passes Criteria'] == True]
    psu_passing = psu_companies[psu_companies['Passes Criteria'] == True]
    
    print(f"\nPassing Criteria:")
    print(f"Banks/Finance: {len(banks_passing)}/{len(banks)} ({len(banks_passing)/len(banks)*100:.1f}%)")
    print(f"Private Companies: {len(private_passing)}/{len(private_companies)} ({len(private_passing)/len(private_companies)*100:.1f}%)")
    print(f"PSU Companies: {len(psu_passing)}/{len(psu_companies)} ({len(psu_passing)/len(psu_companies)*100:.1f}%)")
    
    # Analyze private companies criteria failures
    print(f"\n=== PRIVATE COMPANIES ANALYSIS ===")
    
    # Check each criteria for private companies
    print(f"\nPrivate companies failing each criteria:")
    
    # Net profit > 200
    profit_fail = private_companies[private_companies['Net Profit (Cr)'] <= 200]
    print(f"Net Profit <= 200 Cr: {len(profit_fail)}/{len(private_companies)} ({len(profit_fail)/len(private_companies)*100:.1f}%)")
    
    # ROCE > 20
    roce_fail = private_companies[private_companies['ROCE (%)'] <= 20]
    print(f"ROCE <= 20%: {len(roce_fail)}/{len(private_companies)} ({len(roce_fail)/len(private_companies)*100:.1f}%)")
    
    # Debt to Equity < 0.25
    debt_fail = private_companies[private_companies['Debt to Equity'] >= 0.25]
    print(f"Debt/Equity >= 0.25: {len(debt_fail)}/{len(private_companies)} ({len(debt_fail)/len(private_companies)*100:.1f}%)")
    
    # Check if Last 3Q Avg Profit column exists
    if 'Last 3Q Avg Profit (Cr)' in private_companies.columns:
        # Net profit > Last 3Q Avg
        quarterly_fail = private_companies[
            (private_companies['Net Profit (Cr)'] <= private_companies['Last 3Q Avg Profit (Cr)']) |
            (private_companies['Last 3Q Avg Profit (Cr)'] == 0)
        ]
        print(f"Net Profit <= Last 3Q Avg: {len(quarterly_fail)}/{len(private_companies)} ({len(quarterly_fail)/len(private_companies)*100:.1f}%)")
    else:
        print("Last 3Q Avg Profit column not found - this might be the issue!")
    
    # Show companies that meet basic criteria but fail quarterly comparison
    basic_criteria = private_companies[
        (private_companies['Net Profit (Cr)'] > 200) &
        (private_companies['ROCE (%)'] > 20) &
        (private_companies['Debt to Equity'] < 0.25)
    ]
    
    print(f"\nPrivate companies meeting basic criteria: {len(basic_criteria)}")
    
    if len(basic_criteria) > 0:
        print("\nTop 10 private companies meeting basic criteria:")
        top_basic = basic_criteria.nlargest(10, 'Market Cap')[['Symbol', 'Company Name', 'Net Profit (Cr)', 'ROCE (%)', 'Debt to Equity', 'Passes Criteria']]
        print(top_basic.to_string(index=False))
        
        # Check if they have quarterly data
        if 'Last 3Q Avg Profit (Cr)' in basic_criteria.columns:
            print(f"\nQuarterly data analysis for these companies:")
            quarterly_analysis = basic_criteria[['Symbol', 'Net Profit (Cr)', 'Last 3Q Avg Profit (Cr)', 'Passes Criteria']].head(10)
            quarterly_analysis['Quarterly Growth'] = quarterly_analysis['Net Profit (Cr)'] > quarterly_analysis['Last 3Q Avg Profit (Cr)']
            print(quarterly_analysis.to_string(index=False))

if __name__ == "__main__":
    analyze_screening_criteria()