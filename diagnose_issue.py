#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Diagnose the Last 3Q Avg Profit issue
"""

import pandas as pd

# Load the Master CSV
df = pd.read_csv('Master_company_market_trend_analysis.csv')

print("=== DIAGNOSIS ===\n")
print(f"Total rows: {len(df)}")
print(f"\nLast 3Q Avg Profit (Cr) column stats:")
print(df['Last 3Q Avg Profit (Cr)'].describe())

# Count how many have 0 values
zero_count = (df['Last 3Q Avg Profit (Cr)'] == 0).sum()
print(f"\nRows with Last 3Q Avg Profit = 0: {zero_count}/{len(df)} ({zero_count/len(df)*100:.1f}%)")

# Show some examples
print("\n=== Sample of companies with their quarterly data ===")
sample = df[['Symbol', 'Company Name', 'Net Profit (Cr)', 'Latest Quarter Profit (Cr)', 'Last 3Q Avg Profit (Cr)', 'Is Bank/Finance', 'Is PSU']].head(20)
print(sample.to_string(index=False))

# Check private companies specifically
private = df[(df['Is Bank/Finance'] == False) & (df['Is PSU'] == False)]
print(f"\n=== Private Companies Analysis ===")
print(f"Total private companies: {len(private)}")
print(f"Private companies with Last 3Q Avg = 0: {(private['Last 3Q Avg Profit (Cr)'] == 0).sum()}")

# Show which private companies would qualify if we had proper quarterly data
potential_qualifiers = private[
    (private['Net Profit (Cr)'] > 200) &
    (private['ROCE (%)'] > 20) &
    (private['Debt to Equity'] < 0.25)
]
print(f"\nPrivate companies meeting basic criteria (profit, ROCE, debt): {len(potential_qualifiers)}")
print("\nThese companies:")
print(potential_qualifiers[['Symbol', 'Company Name', 'Net Profit (Cr)', 'ROCE (%)', 'Debt to Equity', 'Latest Quarter Profit (Cr)', 'Last 3Q Avg Profit (Cr)']].to_string(index=False))
