#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test script to debug comprehensive file generation
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener
import pandas as pd
from datetime import datetime

def test_comprehensive_generation():
    """Test the comprehensive file generation with a small sample"""
    print("Testing comprehensive file generation...")
    
    screener = StockScreener()
    
    # Test with just a few stocks to debug
    test_symbols = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK']
    
    all_processed_stocks = []
    screened_stocks = []
    
    for symbol in test_symbols:
        print(f"Processing {symbol}...")
        
        stock_data = screener.get_financial_data(symbol)
        
        if stock_data:
            passes_criteria = screener.apply_screening_criteria(stock_data)
            
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
                'Public Holding (%)': round(stock_data['public_holding'], 2),
                'Is Bank/Finance': stock_data['is_bank_finance'],
                'Is PSU': stock_data['is_psu'],
                'Is Highest Quarter': stock_data.get('is_highest_quarter', False),
                'Passes Criteria': passes_criteria,
                'Screening Date': datetime.now().strftime('%Y-%m-%d')
            }
            all_processed_stocks.append(all_stock_record)
            
            if passes_criteria:
                screened_stocks.append(all_stock_record)
    
    print(f"\nProcessed {len(all_processed_stocks)} stocks")
    print(f"Stocks passing criteria: {len(screened_stocks)}")
    
    # Save comprehensive data
    if all_processed_stocks:
        all_df = pd.DataFrame(all_processed_stocks)
        all_df = all_df.sort_values('Market Cap', ascending=False)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        comprehensive_filename = f'comprehensive_stock_analysis_{timestamp}.csv'
        
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)
        
        comprehensive_filepath = os.path.join(output_dir, comprehensive_filename)
        all_df.to_csv(comprehensive_filepath, index=False)
        print(f"\nCOMPREHENSIVE DATA saved to: {comprehensive_filepath}")
        
        # Display the data
        print("\nComprehensive data preview:")
        print(all_df[['Symbol', 'Company Name', 'Net Profit (Cr)', 'ROCE (%)', 'ROE (%)', 'Passes Criteria']].to_string(index=False))
        
        return comprehensive_filepath
    else:
        print("No data to save!")
        return None

if __name__ == "__main__":
    test_comprehensive_generation()