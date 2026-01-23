#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Detailed test of Screener.in API to understand the correct endpoints
"""

import requests
import json
import time

def test_screener_search_and_details():
    """Test the complete flow of Screener.in API"""
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    symbol = "RELIANCE"
    
    try:
        # Step 1: Search for company
        search_url = f"https://www.screener.in/api/company/search/?q={symbol}"
        print(f"Step 1: Searching for {symbol}")
        print(f"URL: {search_url}")
        
        search_response = requests.get(search_url, headers=headers, timeout=10)
        print(f"Search Status: {search_response.status_code}")
        
        if search_response.status_code == 200:
            search_data = search_response.json()
            print(f"Search Results: {len(search_data)} companies found")
            
            if search_data:
                for i, company in enumerate(search_data[:3]):  # Show first 3 results
                    print(f"  {i+1}. ID: {company.get('id')}, Name: {company.get('name')}, URL: {company.get('url')}")
                
                # Step 2: Try to get company details using different URL patterns
                company_id = search_data[0]['id']
                company_name = search_data[0]['name']
                company_url = search_data[0]['url']
                
                print(f"\nStep 2: Testing different detail endpoints for {company_name} (ID: {company_id})")
                
                # Test various endpoint patterns
                detail_urls = [
                    f"https://www.screener.in/api/company/{company_id}/",
                    f"https://www.screener.in/api/company/{company_id}",
                    f"https://screener.in/api/company/{company_id}/",
                    f"https://www.screener.in{company_url}",
                    f"https://www.screener.in/company/{company_id}/",
                    f"https://www.screener.in/api{company_url}",
                ]
                
                for url in detail_urls:
                    print(f"\nTesting: {url}")
                    try:
                        detail_response = requests.get(url, headers=headers, timeout=10)
                        print(f"Status: {detail_response.status_code}")
                        
                        if detail_response.status_code == 200:
                            try:
                                detail_data = detail_response.json()
                                print(f"SUCCESS! Response keys: {list(detail_data.keys())}")
                                
                                # Look for financial data
                                if 'ratios' in detail_data:
                                    print(f"Ratios available: {list(detail_data['ratios'].keys())}")
                                if 'shareholding' in detail_data:
                                    print(f"Shareholding available: {list(detail_data['shareholding'].keys())}")
                                if 'financials' in detail_data:
                                    print(f"Financials available")
                                
                                return True, url, detail_data
                                
                            except json.JSONDecodeError:
                                print("Response is not JSON")
                                # Check if it's HTML page
                                if 'html' in detail_response.text.lower()[:100]:
                                    print("Received HTML page instead of JSON")
                        else:
                            print(f"Error response: {detail_response.text[:100]}")
                            
                    except Exception as e:
                        print(f"Request error: {e}")
                
                print("\nStep 3: Trying to access web page directly and look for data")
                web_url = f"https://www.screener.in{company_url}"
                print(f"Web URL: {web_url}")
                
                web_response = requests.get(web_url, headers=headers, timeout=10)
                print(f"Web Status: {web_response.status_code}")
                
                if web_response.status_code == 200:
                    # Look for JSON data in the HTML
                    content = web_response.text
                    if 'window.companyData' in content:
                        print("Found window.companyData in HTML - data is embedded in page")
                    if 'ratios' in content.lower():
                        print("Found 'ratios' text in HTML")
                    if 'debt' in content.lower():
                        print("Found 'debt' text in HTML")
        
        return False, None, None
        
    except Exception as e:
        print(f"Error in test: {e}")
        return False, None, None

if __name__ == "__main__":
    print("Detailed Screener.in API Test")
    print("=" * 50)
    
    success, working_url, data = test_screener_search_and_details()
    
    if success:
        print(f"\n✓ SUCCESS: Working URL found: {working_url}")
        print("This URL can be used for implementation")
    else:
        print("\n✗ No working detail endpoint found")
        print("May need to scrape HTML or use alternative approach")