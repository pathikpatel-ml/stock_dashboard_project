def extract_de_ratio_from_screener(html_content):
    """
    Robust D/E ratio extractor for screener.in based on actual HTML analysis
    """
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Method 1: Look for exact text match (most reliable)
    debt_equity_patterns = [
        r'debt\s+to\s+equity',
        r'debt-to-equity', 
        r'd/e\s+ratio',
        r'debt\s+equity\s+ratio',
        r'total\s+debt/equity'
    ]
    
    for pattern in debt_equity_patterns:
        # Find elements containing the pattern
        elements = soup.find_all(string=re.compile(pattern, re.IGNORECASE))
        
        for elem in elements:
            parent = elem.parent
            if not parent:
                continue
                
            # Look for the value in the same structure
            # Check if parent is a span with class 'name'
            if parent.get('class') and 'name' in parent.get('class'):
                # Look for sibling or parent's sibling with number
                container = parent.parent
                if container:
                    number_span = container.find('span', class_='number')
                    if number_span:
                        try:
                            value = float(number_span.get_text().strip())
                            return value
                        except ValueError:
                            continue
    
    # Method 2: Fallback - look in all financial data items
    li_elements = soup.find_all('li', class_='flex flex-space-between')
    
    for li in li_elements:
        name_span = li.find('span', class_='name')
        number_span = li.find('span', class_='number')
        
        if name_span and number_span:
            name_text = name_span.get_text().strip().lower()
            
            # Simple text matching for D/E ratio
            if 'debt to equity' in name_text or 'debt-to-equity' in name_text:
                try:
                    value = float(number_span.get_text().strip())
                    return value
                except ValueError:
                    continue
    
    return None

# Test function
def test_parser():
    test_html = """
    <li class="flex flex-space-between" data-source="quick-ratio">
    <span class="name">Debt to equity</span>
    <span class="nowrap value">
    <span class="number">0.85</span>
    </span>
    </li>
    """
    
    result = extract_de_ratio_from_screener(test_html)
    print(f"Extracted D/E ratio: {result}")
    return result

if __name__ == "__main__":
    test_parser()