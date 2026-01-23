import re
from bs4 import BeautifulSoup

def extract_de_from_screener_html(html_content):
    """
    Updated parser based on the actual HTML structure from screener.in
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Look for li elements containing "Debt to equity"
    debt_equity_items = soup.find_all('li', class_='flex flex-space-between')
    
    for item in debt_equity_items:
        name_span = item.find('span', class_='name')
        if name_span and 'debt to equity' in name_span.get_text().lower().strip():
            value_span = item.find('span', class_='number')
            if value_span:
                try:
                    return float(value_span.get_text().strip())
                except ValueError:
                    continue
    
    # Fallback: Look for any element with data-source containing debt or equity
    for item in debt_equity_items:
        data_source = item.get('data-source', '')
        if 'debt' in data_source.lower() or 'equity' in data_source.lower():
            value_span = item.find('span', class_='number')
            if value_span:
                try:
                    return float(value_span.get_text().strip())
                except ValueError:
                    continue
    
    return None

# Test with your HTML snippet
test_html = '''
<li class="flex flex-space-between" data-source="quick-ratio">
    <span class="name">
        Debt to equity
    </span>
    <span class="nowrap value">
        <span class="number">0.85</span>
    </span>
</li>
'''

result = extract_de_from_screener_html(test_html)
print(f"Extracted D/E ratio: {result}")