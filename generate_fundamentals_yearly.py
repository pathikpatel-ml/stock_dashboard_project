#!/usr/bin/env python

import argparse
import os
import re
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4 import FeatureNotFound

from modules.stock_screener import StockScreener


REPO_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_FILE = "stock_fundamentals_yearly.csv"
UNIVERSE_FILE = "NSE_EQ_All_Stocks_Analysis.csv"


@dataclass
class GenerationSummary:
    total_symbols: int = 0
    successful_symbols: int = 0
    failed_symbols: int = 0
    output_rows: int = 0


class YearlyFundamentalsGenerator:
    def __init__(self, request_delay=0.4, timeout=20):
        self.request_delay = request_delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
                )
            }
        )

    def load_symbol_metadata(self):
        universe_path = os.path.join(REPO_BASE_PATH, UNIVERSE_FILE)
        if os.path.exists(universe_path):
            universe_df = pd.read_csv(universe_path, usecols=["Symbol", "Sector", "Market Cap"])
            universe_df["Symbol"] = universe_df["Symbol"].astype(str).str.upper().str.strip()
            universe_df["Sector"] = universe_df["Sector"].fillna("Unknown").astype(str).str.strip()
            universe_df["Market Cap"] = pd.to_numeric(universe_df["Market Cap"], errors="coerce")
            universe_df = universe_df.dropna(subset=["Symbol"]).drop_duplicates(subset=["Symbol"], keep="last")
            return universe_df.set_index("Symbol").to_dict("index")

        screener = StockScreener()
        return {
            symbol: {"Sector": "Unknown", "Market Cap": np.nan}
            for symbol in screener.get_nse_stock_list()
        }

    def get_symbol_universe(self, metadata_map):
        if metadata_map:
            return sorted(metadata_map.keys())
        return sorted(StockScreener().get_nse_stock_list())

    def fetch_company_html(self, symbol):
        urls = [
            f"https://www.screener.in/company/{symbol}/consolidated/",
            f"https://www.screener.in/company/{symbol}/",
        ]
        last_error = None
        for url in urls:
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                if "Page not found" not in response.text:
                    return response.text
            except Exception as exc:
                last_error = exc
        if last_error:
            raise last_error
        raise ValueError(f"Could not fetch company page for {symbol}")

    def _build_soup(self, html):
        for parser in ("lxml", "html.parser"):
            try:
                return BeautifulSoup(html, parser)
            except FeatureNotFound:
                continue
        return BeautifulSoup(html, "html.parser")

    def _extract_year_from_header(self, value):
        text = str(value).strip()
        match = re.search(r"(19|20)\d{2}", text)
        return int(match.group(0)) if match else None

    def _coerce_numeric(self, value):
        if value is None:
            return np.nan
        text = str(value).replace(",", "").replace("%", "").replace("x", "").strip()
        if text in {"", "-", "--", "—", "None"}:
            return np.nan
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        return float(match.group(0)) if match else np.nan

    def _normalize_label(self, value):
        text = re.sub(r"\s+", " ", str(value).strip().lower())
        return re.sub(r"[^a-z0-9+%/ ]", "", text)

    def _parse_section_table(self, soup, section_id):
        section = soup.find("section", {"id": section_id}) or soup.find(id=section_id)
        if not section:
            return {}

        table = section.find("table")
        if not table:
            return {}

        rows = table.find_all("tr")
        if not rows:
            return {}

        header_cells = rows[0].find_all(["th", "td"])
        header_years = [self._extract_year_from_header(cell.get_text(" ", strip=True)) for cell in header_cells[1:]]
        valid_positions = [(idx, year) for idx, year in enumerate(header_years, start=1) if year is not None]
        if not valid_positions:
            return {}

        parsed = {}
        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = self._normalize_label(cells[0].get_text(" ", strip=True))
            if not label:
                continue

            series = {}
            for position, year in valid_positions:
                if position < len(cells):
                    series[year] = self._coerce_numeric(cells[position].get_text(" ", strip=True))
            if series:
                parsed[label] = series
        return parsed

    def _find_series(self, section_map, candidates):
        for label, series in section_map.items():
            for candidate in candidates:
                if candidate in label:
                    return series
        return {}

    def _series_to_frame(self, series_map, column_name):
        if not series_map:
            return pd.DataFrame(columns=["year", column_name])
        df = pd.DataFrame({"year": list(series_map.keys()), column_name: list(series_map.values())})
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        return df.dropna(subset=["year"]).astype({"year": int}).sort_values("year").reset_index(drop=True)

    def _compute_growth_series(self, base_df, source_column, target_column):
        if base_df.empty or source_column not in base_df.columns:
            return base_df
        base_df = base_df.sort_values("year").copy()
        base_df[target_column] = base_df[source_column].pct_change() * 100
        return base_df

    def parse_company_page(self, symbol, html, metadata):
        soup = self._build_soup(html)
        profit_loss = self._parse_section_table(soup, "profit-loss")
        ratios = self._parse_section_table(soup, "ratios")
        shareholding = self._parse_section_table(soup, "shareholding")

        sales_series = self._find_series(profit_loss, ["sales", "revenue from operations"])
        other_income_series = self._find_series(profit_loss, ["other income"])
        eps_series = self._find_series(profit_loss, ["eps in rs", "eps"])

        roce_series = self._find_series(ratios, ["roce"])
        pb_series = self._find_series(ratios, ["price to book value", "price to book"])
        ps_series = self._find_series(ratios, ["price to sales", "price/sales"])
        pcf_series = self._find_series(ratios, ["price to cash flow", "price to cashflow", "price/cash flow"])
        book_value_series = self._find_series(ratios, ["book value"])
        interest_coverage_series = self._find_series(ratios, ["interest coverage"])

        promoter_holding_series = self._find_series(shareholding, ["promoters +", "promoters"])
        promoter_pledging_series = self._find_series(shareholding, ["pledged percentage", "pledged %", "pledged"])

        frames = [
            self._series_to_frame(sales_series, "sales"),
            self._series_to_frame(other_income_series, "other_income"),
            self._series_to_frame(eps_series, "eps"),
            self._series_to_frame(roce_series, "roce_pct"),
            self._series_to_frame(pb_series, "pb_ratio"),
            self._series_to_frame(ps_series, "ps_ratio"),
            self._series_to_frame(pcf_series, "pcf_ratio"),
            self._series_to_frame(book_value_series, "book_value"),
            self._series_to_frame(interest_coverage_series, "interest_coverage_ratio"),
            self._series_to_frame(promoter_holding_series, "promoter_holding_pct"),
            self._series_to_frame(promoter_pledging_series, "promoter_pledging_pct"),
        ]

        non_empty_frames = [frame for frame in frames if not frame.empty]
        if not non_empty_frames:
            return pd.DataFrame()

        result = non_empty_frames[0]
        for frame in non_empty_frames[1:]:
            result = result.merge(frame, on="year", how="outer")

        result = result.sort_values("year").reset_index(drop=True)
        result = self._compute_growth_series(result, "sales", "sales_growth_pct")
        result = self._compute_growth_series(result, "book_value", "book_value_growth_pct")
        result = self._compute_growth_series(result, "eps", "eps_growth_pct")

        if "sales" in result.columns and "other_income" in result.columns:
            result["quality_turnover_pct"] = (result["other_income"] / result["sales"]) * 100
        else:
            result["quality_turnover_pct"] = np.nan

        result["ticker"] = symbol
        result["sector"] = metadata.get("Sector", "Unknown")
        result["market_cap"] = metadata.get("Market Cap", np.nan)

        required_columns = [
            "ticker",
            "year",
            "sales_growth_pct",
            "roce_pct",
            "pb_ratio",
            "book_value_growth_pct",
            "eps_growth_pct",
            "promoter_holding_pct",
            "ps_ratio",
            "pcf_ratio",
            "promoter_pledging_pct",
            "quality_turnover_pct",
            "interest_coverage_ratio",
            "sector",
            "market_cap",
        ]
        for column in required_columns:
            if column not in result.columns:
                result[column] = np.nan

        return result[required_columns].sort_values("year").reset_index(drop=True)

    def generate(self, symbols, metadata_map):
        rows = []
        summary = GenerationSummary(total_symbols=len(symbols))

        for index, symbol in enumerate(symbols, start=1):
            print(f"[{index}/{len(symbols)}] Processing {symbol}")
            metadata = metadata_map.get(symbol, {"Sector": "Unknown", "Market Cap": np.nan})
            try:
                html = self.fetch_company_html(symbol)
                company_df = self.parse_company_page(symbol, html, metadata)
                if not company_df.empty:
                    rows.append(company_df)
                    summary.successful_symbols += 1
                else:
                    print(f"  No yearly data parsed for {symbol}")
                    summary.failed_symbols += 1
            except Exception as exc:
                print(f"  Failed for {symbol}: {exc}")
                summary.failed_symbols += 1

            time.sleep(self.request_delay)

        if rows:
            output_df = pd.concat(rows, ignore_index=True)
            output_df = output_df.sort_values(["ticker", "year"]).reset_index(drop=True)
        else:
            output_df = pd.DataFrame(
                columns=[
                    "ticker",
                    "year",
                    "sales_growth_pct",
                    "roce_pct",
                    "pb_ratio",
                    "book_value_growth_pct",
                    "eps_growth_pct",
                    "promoter_holding_pct",
                    "ps_ratio",
                    "pcf_ratio",
                    "promoter_pledging_pct",
                    "quality_turnover_pct",
                    "interest_coverage_ratio",
                    "sector",
                    "market_cap",
                ]
            )

        summary.output_rows = len(output_df)
        return output_df, summary


def parse_args():
    parser = argparse.ArgumentParser(description="Generate yearly historical fundamentals for strategy modules.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Output CSV path.")
    parser.add_argument("--sample-size", type=int, default=0, help="Limit processing to the first N symbols.")
    parser.add_argument("--symbols", default="", help="Comma-separated list of symbols to process.")
    parser.add_argument("--min-successful-symbols", type=int, default=1, help="Minimum successful symbols required.")
    parser.add_argument("--request-delay", type=float, default=0.4, help="Delay between requests in seconds.")
    return parser.parse_args()


def main():
    args = parse_args()
    generator = YearlyFundamentalsGenerator(request_delay=args.request_delay)
    metadata_map = generator.load_symbol_metadata()

    if args.symbols:
        symbols = [symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()]
    else:
        symbols = generator.get_symbol_universe(metadata_map)

    if args.sample_size and args.sample_size > 0:
        symbols = symbols[: args.sample_size]

    output_df, summary = generator.generate(symbols, metadata_map)
    output_path = os.path.join(REPO_BASE_PATH, args.output)
    os.makedirs(os.path.dirname(output_path) or REPO_BASE_PATH, exist_ok=True)
    output_df.to_csv(output_path, index=False)

    print(
        f"Generation complete. Symbols={summary.total_symbols}, "
        f"successful={summary.successful_symbols}, failed={summary.failed_symbols}, rows={summary.output_rows}"
    )
    print(f"Saved output to {output_path}")

    if summary.successful_symbols < args.min_successful_symbols:
        raise SystemExit(
            f"Only {summary.successful_symbols} symbols succeeded, below required minimum {args.min_successful_symbols}."
        )


if __name__ == "__main__":
    main()
