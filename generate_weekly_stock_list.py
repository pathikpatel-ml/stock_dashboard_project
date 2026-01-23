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
from modules.stock_screener import StockScreener

# --- Configuration ---
REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
STOCK_LIST_FILENAME = "Master_company_market_trend_analysis.csv"
OUTPUT_STOCK_LIST_PATH = os.path.join(REPO_BASE_PATH, STOCK_LIST_FILENAME)

def generate_weekly_stock_list(output_path):
    """Generate weekly stock list using the StockScreener"""
    try:
        screener = StockScreener()
        df = screener.screen_stocks()
        
        if not df.empty:
            # Save to the specified output path
            df.to_csv(output_path, index=False)
            print(f"Stock list saved to: {output_path}")
            
            # Find the latest comprehensive CSV file
            output_dir = os.path.join(REPO_BASE_PATH, 'output')
            if os.path.exists(output_dir):
                csv_files = [f for f in os.listdir(output_dir) if f.startswith('comprehensive_stock_analysis')]
                if csv_files:
                    latest_comprehensive = sorted(csv_files)[-1]
                    return True, len(df), latest_comprehensive
            
            return True, len(df), None
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