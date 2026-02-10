#!/usr/bin/env python
# coding: utf-8

"""
Weekly Stock List Generation Script
Generates dynamic stock list based on financial screening criteria
"""

import os
import sys
import subprocess
from datetime import datetime
from modules.stock_screener import StockScreener, add_moving_averages_to_stocks, add_nse_categories_to_stocks
from modules.nse_category_fetcher import get_nse_stock_categories, save_nse_categories_to_csv
import pandas as pd

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
STOCK_LIST_FILENAME = "Master_company_market_trend_analysis.csv"
OUTPUT_STOCK_LIST_PATH = os.path.join(REPO_BASE_PATH, STOCK_LIST_FILENAME)

def generate_weekly_stock_list(output_path):
    """Generate weekly stock list with moving averages and NSE categories"""
    try:
        print("Starting comprehensive stock screening with enhancements...")
        screener = StockScreener()
        df = screener.screen_stocks()
        
        if not df.empty:
            # Load comprehensive data (all stocks, not just screened ones)
            print("Loading comprehensive stock data...")
            try:
                output_dir = os.path.join(REPO_BASE_PATH, 'output')
                csv_files = [f for f in os.listdir(output_dir) if f.startswith('comprehensive_stock_analysis_')]
                if csv_files:
                    latest_file = sorted(csv_files)[-1]
                    comprehensive_df = pd.read_csv(os.path.join(output_dir, latest_file))
                    print(f"Loaded {len(comprehensive_df)} stocks from comprehensive analysis")
                else:
                    comprehensive_df = df
            except Exception as e:
                print(f"Error loading comprehensive data: {e}")
                comprehensive_df = df
            
            # Add moving averages
            print("Adding moving averages to stocks...")
            comprehensive_df = add_moving_averages_to_stocks(comprehensive_df)
            
            # Add NSE categories
            print("Adding NSE category information...")
            comprehensive_df = add_nse_categories_to_stocks(comprehensive_df)
            
            # Save NSE categories separately
            print("Saving NSE categories mapping...")
            try:
                categories_data = get_nse_stock_categories()
                save_nse_categories_to_csv(categories_data)
                print("NSE categories saved successfully")
            except Exception as e:
                print(f"Error saving NSE categories: {e}")
            
            # Save enhanced comprehensive data
            timestamp = datetime.now().strftime('%Y%m%d')
            enhanced_filename = f'comprehensive_stock_analysis_{timestamp}.csv'
            enhanced_filepath = os.path.join(output_dir, enhanced_filename)
            
            comprehensive_df.to_csv(enhanced_filepath, index=False)
            print(f"Enhanced comprehensive data saved to: {enhanced_filename}")
            
            # Save screened stocks to main output path
            df.to_csv(output_path, index=False)
            print(f"Screened stock list saved to: {output_path}")
            
            return True, len(df), enhanced_filename
        else:
            print("No stocks found meeting criteria")
            return False, 0, None
    except Exception as e:
        print(f"Error generating stock list: {e}")
        return False, 0, None
def run_git_command(command_list, working_dir="."):
    try:
        process = subprocess.Popen(command_list, cwd=working_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate(timeout=120)
        if process.returncode == 0:
            if stdout.strip(): print(f"GIT STDOUT: {stdout.strip()}")
            return True
        else:
            print(f"GIT ERROR: Command '{' '.join(command_list)}' failed with code {process.returncode}.")
            if stdout.strip(): print(f"GIT STDOUT: {stdout.strip()}")
            if stderr.strip(): print(f"GIT STDERR: {stderr.strip()}")
            return False
    except subprocess.TimeoutExpired: 
        print(f"GIT TIMEOUT: Command '{' '.join(command_list)}' timed out.")
        return False
    except Exception as e: 
        print(f"GIT EXCEPTION: running command '{' '.join(command_list)}': {e}")
        return False

def commit_and_push_stock_list(file_to_add, commit_message, comprehensive_file=None):
    print(f"\n--- GIT OPS: Starting Git Operations for stock list ---")
    
    # Only add the main stock list file (comprehensive files are ignored by .gitignore)
    files_to_add = [file_to_add]
    
    # Add all files
    for file_path in files_to_add:
        if not os.path.exists(os.path.join(REPO_BASE_PATH, file_path)):
            print(f"GIT OPS WARNING: File '{file_path}' not found. Skipping.")
            continue
        
        if not run_git_command(["git", "add", file_path], working_dir=REPO_BASE_PATH):
            print(f"GIT OPS ERROR: Failed to 'git add {file_path}'.")
            return False
        else:
            print(f"GIT OPS: Successfully added '{file_path}' to staging.")
    
    # Check if there are changes to commit
    status_check_process = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO_BASE_PATH)
    if not status_check_process.stdout.strip():
        print("GIT OPS: No changes staged for commit. Skipping commit and push.")
        return True 

    if not run_git_command(["git", "commit", "-m", commit_message], working_dir=REPO_BASE_PATH):
        print(f"GIT OPS ERROR: Failed to 'git commit'. Aborting push.")
        return False
    print(f"GIT OPS: Successfully committed changes with message: '{commit_message}'.")

    if not run_git_command(["git", "push"], working_dir=REPO_BASE_PATH):
        print(f"GIT OPS ERROR: Failed to 'git push'.")
        return False
    print(f"GIT OPS: Successfully pushed changes to remote repository.")
    return True

# --- Main Execution ---
if __name__ == "__main__":
    print(f"WEEKLY STOCK LIST GENERATION: Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Generate the stock list using screening criteria
    success, stock_count, comprehensive_file = generate_weekly_stock_list(OUTPUT_STOCK_LIST_PATH)
    
    if success:
        print(f"WEEKLY: Successfully generated stock list with {stock_count} stocks")
        
        # Commit and push the updated stock list
        today_str = datetime.now().strftime("%Y%m%d")
        commit_message = f"Weekly stock list update {today_str} - {stock_count} stocks screened"
        
        if commit_and_push_stock_list(STOCK_LIST_FILENAME, commit_message):
            print("WEEKLY: Successfully committed and pushed stock list to GitHub.")
        else:
            print("WEEKLY ERROR: Failed to commit and push stock list to GitHub.")
            sys.exit(1)
    else:
        print("WEEKLY ERROR: Failed to generate stock list.")
        sys.exit(1)
    
    print(f"WEEKLY STOCK LIST GENERATION: Finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    sys.exit(0)