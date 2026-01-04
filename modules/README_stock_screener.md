# Stock Screener Module

## Overview
The Stock Screener module provides dynamic stock selection based on financial criteria for different sectors. It screens NSE stocks and identifies investment opportunities based on fundamental analysis.

## Features
- **Dynamic Sector-Based Screening**: Different criteria for banks/finance vs other sectors
- **Quarterly Performance Check**: Ensures latest quarter profit is highest in last 12 quarters
- **Comprehensive Financial Analysis**: Analyzes profit, ROCE, ROE, and debt ratios
- **Automated Report Generation**: Saves results to CSV with timestamps
- **Real-time Data**: Uses yfinance for up-to-date financial information

## Screening Criteria

### Bank and Finance Companies
- Net Profit > ₹1000 Crores
- ROE > 10%
- Latest quarter profit is highest in last 12 quarters

### Other Sectors (Private & PSU)
- Net Profit > ₹200 Crores  
- ROCE > 20%
- Debt to Equity < 0.25
- Latest quarter profit is highest in last 12 quarters

## Usage

### Basic Usage
```python
from modules.stock_screener import StockScreener

# Create screener instance
screener = StockScreener()

# Get stock recommendations (top 20)
recommendations = screener.get_stock_recommendations(max_stocks=20)

# Or run full screening
results = screener.screen_stocks()
```

### Command Line Usage
```bash
# Run the screener
python modules/stock_screener.py

# Test with sample stocks
python test_screener.py
```

## Output
- **Console Output**: Real-time progress and summary statistics
- **CSV Report**: Detailed results saved to `output/screened_stocks_YYYYMMDD_HHMMSS.csv`
- **Sector Analysis**: Breakdown of stocks by sector
- **Top Recommendations**: Ranked by market capitalization

## Output Columns
- Symbol: Stock symbol
- Company Name: Full company name
- Sector: Business sector
- Industry: Specific industry
- Market Cap: Market capitalization
- Net Profit (Cr): Annual net profit in crores
- ROCE (%): Return on Capital Employed
- ROE (%): Return on Equity
- Debt to Equity: Debt to equity ratio
- Latest Quarter Profit (Cr): Most recent quarter profit
- Is Bank/Finance: Boolean flag for sector classification
- Screening Date: Date of analysis

## Stock Universe
The screener analyzes major NSE stocks including:
- Nifty 50 components
- Major mid-cap stocks
- Sector leaders
- Total: ~100+ stocks

## Dependencies
- pandas: Data manipulation
- yfinance: Financial data retrieval
- numpy: Numerical computations
- requests: HTTP requests
- datetime: Date/time handling

## Error Handling
- Network connectivity issues
- Missing financial data
- API rate limiting
- Data parsing errors

## Performance
- Processing time: ~2-5 minutes for full screening
- Rate limiting: 0.1 second delay between API calls
- Memory usage: Minimal (processes one stock at a time)

## Limitations
- Depends on yfinance data availability
- Some financial metrics may be approximated
- Quarterly data may have delays
- Limited to NSE stocks only

## Future Enhancements
- BSE stock support
- Custom screening criteria
- Technical analysis integration
- Portfolio optimization
- Real-time alerts