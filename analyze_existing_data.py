#!/usr/bin/env python
# -*- coding: utf-8 -*-

import pandas as pd
import os
from modules.stock_screener import StockScreener

def analyze_latest_csv():
    """Analyze the latest screened stocks CSV file"""
    output_dir = "output"
    
    # Find the latest CSV file
    csv_files = [f for f in os.listdir(output_dir) if f.startswith('screened_stocks_') and f.endswith('.csv')]
    if not csv_files:
        print("No screened stocks CSV files found")
        return
    
    latest_file = max(csv_files)
    filepath = os.path.join(output_dir, latest_file)
    
    print(f"Analyzing: {filepath}")
    
    # Read and analyze the data
    df = pd.read_csv(filepath)
    
    print(f"\n=== ANALYSIS OF {latest_file} ===")
    print(f"Total stocks: {len(df)}")
    
    # Sector breakdown
    print("\nSector breakdown:")
    sector_counts = df['Sector'].value_counts()
    for sector, count in sector_counts.items():
        print(f"  {sector}: {count}")
    
    # Bank vs Non-bank
    bank_count = df['Is Bank/Finance'].sum()
    print(f"\nBank/Finance stocks: {bank_count}")
    print(f"Non-bank stocks: {len(df) - bank_count}")
    
    # PSU vs Private
    psu_count = df['Is PSU'].sum()
    print(f"\nPSU stocks: {psu_count}")
    print(f"Private stocks: {len(df) - psu_count}")
    
    # Top 10 by market cap
    print("\nTop 10 by Market Cap:")
    top_10 = df.nlargest(10, 'Market Cap')[['Symbol', 'Company Name', 'Market Cap', 'Net Profit (Cr)']]
    for idx, row in top_10.iterrows():
        print(f"  {row['Symbol']} - {row['Company Name']} (₹{row['Market Cap']:,.0f})")

if __name__ == "__main__":
    analyze_latest_csv()