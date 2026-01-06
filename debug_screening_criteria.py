#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Debug Script to Analyze Why Only 30 Stocks Pass Screening Criteria
"""

import pandas as pd
import numpy as np

def analyze_screening_bottlenecks():
    """Analyze the comprehensive data to find screening bottlenecks"""
    
    # Note: You'll need to download the comprehensive CSV from GitHub Actions
    # For now, let's create a sample analysis based on typical patterns
    
    print("SCREENING CRITERIA ANALYSIS")
    print("=" * 50)
    
    # Simulate analysis based on typical NSE stock patterns
    print("\nCRITERIA BREAKDOWN ANALYSIS:")
    print("-" * 30)
    
    print("\n1. HIGHEST QUARTER CHECK:")
    print("   - This is likely the biggest filter")
    print("   - Many stocks may not have their latest quarter as the highest in 12 quarters")
    print("   - Estimated failure rate: 60-70%")
    
    print("\n2. BANK/FINANCE STOCKS (Net Profit > 1000 Cr + ROE > 10%):")
    print("   - Net Profit > 1000 Cr: ~50-100 banks/finance companies qualify")
    print("   - ROE > 10%: Most major banks should pass this")
    print("   - Combined with highest quarter: ~15-25 banks expected")
    
    print("\n3. NON-BANK STOCKS (Net Profit > 200 Cr + ROCE > 20% + Debt/Equity < 0.25):")
    print("   - Net Profit > 200 Cr: ~300-500 companies")
    print("   - ROCE > 20%: This is very stringent, maybe 10-20% pass")
    print("   - Debt/Equity < 0.25: ~40-60% pass")
    print("   - Public Holding < 30% (private): Very restrictive")
    print("   - Combined: ~5-15 companies expected")
    
    print("\n4. POTENTIAL ISSUES:")
    print("   a) ROCE calculation might be too conservative")
    print("   b) Public holding < 30% is very restrictive for private companies")
    print("   c) Highest quarter check is eliminating many good stocks")
    
    print("\n5. RECOMMENDATIONS:")
    print("   a) Relax ROCE from 20% to 15%")
    print("   b) Increase public holding threshold from 30% to 50%")
    print("   c) Use 95% of max quarter instead of 100% for highest quarter check")
    print("   d) Consider market cap weighting for criteria")

def create_relaxed_criteria_test():
    """Create a test with relaxed criteria to see impact"""
    
    print("\n" + "=" * 50)
    print("RELAXED CRITERIA SIMULATION")
    print("=" * 50)
    
    print("\nORIGINAL CRITERIA:")
    print("- Banks: Net Profit > 1000 Cr, ROE > 10%, Highest Quarter")
    print("- Non-Banks: Net Profit > 200 Cr, ROCE > 20%, Debt/Equity < 0.25, Public < 30%, Highest Quarter")
    print("- Result: 30 stocks (1.35%)")
    
    print("\nRELAXED CRITERIA OPTION 1:")
    print("- Banks: Net Profit > 500 Cr, ROE > 8%, Highest Quarter")
    print("- Non-Banks: Net Profit > 100 Cr, ROCE > 15%, Debt/Equity < 0.5, Public < 50%, Highest Quarter")
    print("- Expected: 80-120 stocks (3.5-5%)")
    
    print("\nRELAXED CRITERIA OPTION 2:")
    print("- Banks: Net Profit > 1000 Cr, ROE > 10%, Top 3 quarters in 12")
    print("- Non-Banks: Net Profit > 200 Cr, ROCE > 15%, Debt/Equity < 0.5, Public < 50%, Top 3 quarters in 12")
    print("- Expected: 100-150 stocks (4.5-6.5%)")

def suggest_criteria_modifications():
    """Suggest specific modifications to increase eligible stocks"""
    
    print("\n" + "=" * 50)
    print("RECOMMENDED CRITERIA MODIFICATIONS")
    print("=" * 50)
    
    modifications = [
        {
            "change": "ROCE Threshold",
            "from": "20%",
            "to": "15%",
            "impact": "Could increase non-bank eligibility by 50-100%",
            "justification": "20% ROCE is very stringent, 15% is still excellent"
        },
        {
            "change": "Public Holding",
            "from": "< 30%",
            "to": "< 50%",
            "impact": "Could double private company eligibility",
            "justification": "30% is too restrictive, many good companies have higher public holding"
        },
        {
            "change": "Highest Quarter Logic",
            "from": "Must be absolute highest",
            "to": "Top 3 in last 12 quarters OR >= 95% of highest",
            "impact": "Could increase eligibility by 200-300%",
            "justification": "Allows for minor quarterly fluctuations while maintaining growth trend"
        },
        {
            "change": "Bank Net Profit",
            "from": "1000 Cr",
            "to": "500 Cr",
            "impact": "Could add 10-15 more banks",
            "justification": "Include mid-size banks with good fundamentals"
        },
        {
            "change": "Debt/Equity Ratio",
            "from": "< 0.25",
            "to": "< 0.5",
            "impact": "Could increase eligibility by 30-50%",
            "justification": "0.25 is very conservative, 0.5 is still healthy"
        }
    ]
    
    for i, mod in enumerate(modifications, 1):
        print(f"\n{i}. {mod['change']}:")
        print(f"   From: {mod['from']}")
        print(f"   To: {mod['to']}")
        print(f"   Impact: {mod['impact']}")
        print(f"   Why: {mod['justification']}")

if __name__ == "__main__":
    analyze_screening_bottlenecks()
    create_relaxed_criteria_test()
    suggest_criteria_modifications()
    
    print("\n" + "=" * 50)
    print("NEXT STEPS:")
    print("=" * 50)
    print("1. Download comprehensive_stock_analysis CSV from GitHub Actions")
    print("2. Analyze actual data to confirm bottlenecks")
    print("3. Implement relaxed criteria in stock_screener.py")
    print("4. Test with new criteria and compare results")
    print("5. Find optimal balance between quality and quantity")