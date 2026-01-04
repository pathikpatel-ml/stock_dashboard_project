#!/usr/bin/env python
"""
Cron Job Test Script
Simulates the automated weekly stock screening process
"""

import os
import sys
import time
from datetime import datetime

# Add modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from stock_screener import StockScreener

def simulate_cron_job():
    """Simulate the cron job execution"""
    print("=" * 60)
    print("CRON JOB SIMULATION - Weekly Stock Screening")
    print("=" * 60)
    print(f"Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Simulating: Weekly stock screening cron job")
    print("=" * 60)
    
    try:
        # Initialize screener
        screener = StockScreener()
        
        # Override stock list for faster testing
        test_stocks = [
            'RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'ICICIBANK', 
            'SBIN', 'ONGC', 'NTPC', 'WIPRO', 'LT',
            'BHARTIARTL', 'ITC', 'KOTAKBANK', 'ASIANPAINT', 'MARUTI'
        ]
        
        original_method = screener.get_nse_stock_list
        screener.get_nse_stock_list = lambda: test_stocks
        
        print(f"Starting screening of {len(test_stocks)} test stocks...")
        print("This simulates the weekly automated process...")
        
        # Run screening
        start_time = time.time()
        df = screener.screen_stocks()
        end_time = time.time()
        
        execution_time = end_time - start_time
        
        print(f"\nCRON JOB RESULTS:")
        print(f"Execution Time: {execution_time:.2f} seconds")
        print(f"Stocks Screened: {len(test_stocks)}")
        print(f"Stocks Meeting Criteria: {len(df) if not df.empty else 0}")
        
        if not df.empty:
            print(f"\nSelected Stocks:")
            for idx, row in df.iterrows():
                category = "PSU" if row['Is PSU'] else ("Bank" if row['Is Bank/Finance'] else "Private")
                print(f"  {row['Symbol']} ({category}) - ₹{row['Net Profit (Cr)']} Cr profit")
            
            # Show CSV file location
            output_files = [f for f in os.listdir('output') if f.startswith('screened_stocks_')]
            if output_files:
                latest_file = max(output_files)
                print(f"\nCSV Report Generated: output/{latest_file}")
        else:
            print("\nNo stocks met the screening criteria.")
        
        # Restore original method
        screener.get_nse_stock_list = original_method
        
        print("\n" + "=" * 60)
        print("CRON JOB SIMULATION COMPLETED SUCCESSFULLY")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\nCRON JOB ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_cron_schedule():
    """Show the cron schedule information"""
    print("\n" + "=" * 60)
    print("CRON JOB SCHEDULE INFORMATION")
    print("=" * 60)
    print("GitHub Actions Workflow: weekly_stock_screening.yml")
    print("Schedule: Every Sunday at 6:00 AM IST (00:30 UTC)")
    print("Cron Expression: '30 0 * * 0'")
    print("Manual Trigger: Available via workflow_dispatch")
    print("\nWhat the cron job does:")
    print("1. Fetches latest NSE stock list")
    print("2. Applies financial screening criteria:")
    print("   - Private Sector: Net profit > ₹200 Cr, ROCE > 20%, Debt/Equity < 0.25, Public holding > 30%")
    print("   - PSU: Net profit > ₹200 Cr, ROCE > 20%, Debt/Equity < 0.25")
    print("   - Banks: Net profit > ₹1000 Cr, ROE > 10%")
    print("3. Generates CSV report with selected stocks")
    print("4. Commits results to GitHub repository")
    print("=" * 60)

def main():
    """Main function"""
    print("Stock Screener - Cron Job Testing")
    
    # Show schedule info
    show_cron_schedule()
    
    # Simulate cron job
    success = simulate_cron_job()
    
    if success:
        print("\n✓ Cron job simulation completed successfully!")
        print("The automated weekly screening would work as expected.")
    else:
        print("\n✗ Cron job simulation failed!")
        print("Check the error messages above for issues.")

if __name__ == "__main__":
    main()