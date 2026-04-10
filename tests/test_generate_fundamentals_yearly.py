from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from generate_fundamentals_yearly import YearlyFundamentalsGenerator


SAMPLE_HTML = """
<html>
  <body>
    <section id="profit-loss">
      <table>
        <tr><th>Particulars</th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th></tr>
        <tr><td>Sales +</td><td>100</td><td>120</td><td>150</td></tr>
        <tr><td>Other Income</td><td>5</td><td>6</td><td>7</td></tr>
        <tr><td>EPS in Rs</td><td>10</td><td>12</td><td>18</td></tr>
      </table>
    </section>
    <section id="ratios">
      <table>
        <tr><th>Particulars</th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th></tr>
        <tr><td>ROCE %</td><td>11</td><td>12</td><td>13</td></tr>
        <tr><td>Price to Book value</td><td>2</td><td>2.5</td><td>3</td></tr>
        <tr><td>Price to Sales</td><td>4</td><td>4.5</td><td>5</td></tr>
        <tr><td>Price to Cash Flow</td><td>6</td><td>6.5</td><td>7</td></tr>
        <tr><td>Book Value</td><td>50</td><td>60</td><td>72</td></tr>
        <tr><td>Interest Coverage</td><td>8</td><td>9</td><td>10</td></tr>
      </table>
    </section>
    <section id="shareholding">
      <table>
        <tr><th>Particulars</th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th></tr>
        <tr><td>Promoters +</td><td>55</td><td>56</td><td>57</td></tr>
        <tr><td>Pledged percentage</td><td>1</td><td>0</td><td>0</td></tr>
      </table>
    </section>
  </body>
</html>
"""


def test_parse_company_page_extracts_expected_yearly_metrics():
    generator = YearlyFundamentalsGenerator(request_delay=0)
    parsed = generator.parse_company_page(
        "TCS",
        SAMPLE_HTML,
        {"Sector": "Technology", "Market Cap": 1000},
    )

    assert list(parsed["year"]) == [2022, 2023, 2024]
    assert parsed.iloc[-1]["ticker"] == "TCS"
    assert parsed.iloc[-1]["sector"] == "Technology"
    assert parsed.iloc[-1]["market_cap"] == 1000
    assert parsed.iloc[-1]["sales"] == 150
    assert parsed.iloc[-1]["book_value"] == 72
    assert parsed.iloc[-1]["eps"] == 18
    assert round(parsed.iloc[-1]["sales_growth_pct"], 2) == 25.0
    assert round(parsed.iloc[-1]["book_value_growth_pct"], 2) == 20.0
    assert round(parsed.iloc[-1]["eps_growth_pct"], 2) == 50.0
    assert round(parsed.iloc[-1]["quality_turnover_pct"], 2) == round((7 / 150) * 100, 2)


def test_generate_respects_sample_and_counts_successes(monkeypatch):
    generator = YearlyFundamentalsGenerator(request_delay=0)

    monkeypatch.setattr(generator, "fetch_company_html", lambda symbol: SAMPLE_HTML)
    metadata_map = {
        "TCS": {"Sector": "Technology", "Market Cap": 1000},
        "INFY": {"Sector": "Technology", "Market Cap": 900},
    }

    output_df, summary = generator.generate(["TCS", "INFY"], metadata_map)

    assert summary.total_symbols == 2
    assert summary.successful_symbols == 2
    assert summary.failed_symbols == 0
    assert set(output_df["ticker"]) == {"TCS", "INFY"}


def test_parse_section_table_returns_empty_for_missing_section():
    generator = YearlyFundamentalsGenerator(request_delay=0)
    result = generator.parse_company_page("ABC", "<html></html>", {"Sector": "Unknown", "Market Cap": 10})

    assert result.empty
