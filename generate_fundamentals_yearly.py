#!/usr/bin/env python

import argparse
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime

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

    def fetch_chart_datasets(self, company_id, metrics, days=1825, consolidated=True):
        url = f"https://www.screener.in/api/company/{company_id}/chart/"
        params = {"q": "-".join(metrics), "days": days}
        if consolidated:
            params["consolidated"] = "true"
        response = self.session.get(
            url,
            params=params,
            timeout=self.timeout,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("datasets", [])

    def fetch_investor_breakdown(self, company_id, classification="promoters", period="yearly"):
        url = f"https://www.screener.in/api/3/{company_id}/investors/{classification}/{period}/"
        response = self.session.get(
            url,
            timeout=self.timeout,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        return response.json()

    def fetch_nse_pledged_data(self, symbol):
        session = requests.Session()
        session.headers.update({"User-Agent": self.session.headers.get("User-Agent", "Mozilla/5.0")})
        try:
            session.get("https://www.nseindia.com", timeout=self.timeout)
            response = session.get(
                "https://www.nseindia.com/api/corporate-pledgedata",
                params={"symbol": symbol},
                headers={"Referer": "https://www.nseindia.com/companies-listing/corporate-filings-pledged-data"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return {}

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
        normalized_candidates = [self._normalize_label(candidate) for candidate in candidates]

        for candidate in normalized_candidates:
            for label, series in section_map.items():
                if label == candidate:
                    return series

        for candidate in normalized_candidates:
            for label, series in section_map.items():
                if label.startswith(f"{candidate} "):
                    return series

        for label, series in section_map.items():
            for candidate in normalized_candidates:
                if candidate in label:
                    return series
        return {}

    def _series_to_frame(self, series_map, column_name):
        if not series_map:
            return pd.DataFrame(columns=["year", column_name])
        df = pd.DataFrame({"year": list(series_map.keys()), column_name: list(series_map.values())})
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        return df.dropna(subset=["year"]).astype({"year": int}).sort_values("year").reset_index(drop=True)

    def _dataset_values_to_year_map(self, datasets, metric_name):
        for dataset in datasets:
            if dataset.get("metric") != metric_name:
                continue
            values = dataset.get("values", [])
            year_map = {}
            for date_str, value in values:
                year = self._extract_year_from_header(date_str)
                if year is None:
                    continue
                year_map[year] = value
            return year_map
        return {}

    def _parse_period_date(self, label):
        label = str(label).strip()
        for fmt in ("%b %Y", "%B %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(label, fmt)
            except ValueError:
                continue
        year = self._extract_year_from_header(label)
        if year is None:
            return None
        return datetime(year, 12, 31)

    def _aggregate_investor_payload(self, payload):
        totals = {}
        for investor_name, investor_data in payload.items():
            if investor_name == "setAttributes" or not isinstance(investor_data, dict):
                continue
            best_value_by_year = {}
            best_date_by_year = {}
            for period_label, value in investor_data.items():
                if period_label == "setAttributes":
                    continue
                year = self._extract_year_from_header(period_label)
                period_date = self._parse_period_date(period_label)
                numeric_value = self._coerce_numeric(value)
                if year is None or period_date is None or pd.isna(numeric_value):
                    continue
                existing_date = best_date_by_year.get(year)
                if existing_date is None or period_date > existing_date:
                    best_date_by_year[year] = period_date
                    best_value_by_year[year] = float(numeric_value)
            for year, numeric_value in best_value_by_year.items():
                totals[year] = totals.get(year, 0.0) + numeric_value
        return totals

    def _pledged_payload_to_year_map(self, payload):
        if not payload or "data" not in payload or not payload["data"]:
            return {}

        year_map = {}
        for row in payload["data"]:
            if not isinstance(row, dict):
                continue
            period_label = row.get("shp") or row.get("disclosureToDate") or row.get("broadcastDt")
            year = self._extract_year_from_header(period_label)
            if year is None:
                continue

            promoter_pct = self._coerce_numeric(row.get("percPromoterShares"))
            depository_pct = self._coerce_numeric(row.get("percSharesPledged"))

            # Prefer the direct "% of promoter shares (X/A)" metric from NSE.
            value = promoter_pct if not pd.isna(promoter_pct) else depository_pct
            if pd.isna(value):
                continue
            year_map[year] = float(value)
        return year_map

    def _compute_growth_series(self, base_df, source_column, target_column):
        if base_df.empty or source_column not in base_df.columns:
            return base_df
        base_df = base_df.sort_values("year").copy()
        base_df[target_column] = base_df[source_column].pct_change() * 100
        return base_df

    def _empty_output_frame(self):
        return pd.DataFrame(
            columns=[
                "ticker",
                "year",
                "sales",
                "book_value",
                "eps",
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

    def _normalize_existing_output(self, df):
        if df is None or df.empty:
            return self._empty_output_frame()
        normalized = df.copy()
        if "ticker" in normalized.columns:
            normalized["ticker"] = normalized["ticker"].astype(str).str.upper().str.strip()
        if "year" in normalized.columns:
            normalized["year"] = pd.to_numeric(normalized["year"], errors="coerce")
            normalized = normalized.dropna(subset=["year"])
            normalized["year"] = normalized["year"].astype(int)
        required = self._empty_output_frame().columns.tolist()
        for column in required:
            if column not in normalized.columns:
                normalized[column] = np.nan
        normalized = normalized[required]
        if {"ticker", "year"}.issubset(set(normalized.columns)):
            normalized = normalized.drop_duplicates(subset=["ticker", "year"], keep="last")
        return normalized.sort_values(["ticker", "year"]).reset_index(drop=True)

    def parse_company_page(self, symbol, html, metadata):
        soup = self._build_soup(html)
        company_info = soup.find(id="company-info")
        company_id = company_info.get("data-company-id") if company_info else None
        is_consolidated = str(company_info.get("data-consolidated", "")).lower() == "true" if company_info else True

        profit_loss = self._parse_section_table(soup, "profit-loss")
        ratios = self._parse_section_table(soup, "ratios")
        cash_flow = self._parse_section_table(soup, "cash-flow")
        shareholding = self._parse_section_table(soup, "shareholding")

        chart_datasets = []
        investor_payload = {}
        nse_pledged_payload = {}
        if company_id:
            try:
                chart_datasets = self.fetch_chart_datasets(
                    company_id,
                    [
                        "Price to book value",
                        "Median PBV",
                        "Book value",
                        "Market Cap to Sales",
                        "Median Market Cap to Sales",
                        "Sales",
                    ],
                    days=10000,
                    consolidated=is_consolidated,
                )
            except Exception:
                chart_datasets = []
            try:
                investor_payload = self.fetch_investor_breakdown(company_id, classification="promoters", period="yearly")
            except Exception:
                investor_payload = {}
            if not investor_payload:
                try:
                    investor_payload = self.fetch_investor_breakdown(
                        company_id, classification="promoters", period="quarterly"
                    )
                except Exception:
                    investor_payload = {}
        # Only augment with NSE pledged data for real company pages.
        # Fixture-based unit tests intentionally pass HTML without company-info.
        if company_id:
            try:
                nse_pledged_payload = self.fetch_nse_pledged_data(symbol)
            except Exception:
                nse_pledged_payload = {}

        sales_series = self._find_series(profit_loss, ["sales", "revenue from operations"])
        other_income_series = self._find_series(profit_loss, ["other income"])
        interest_series = self._find_series(profit_loss, ["interest"])
        operating_profit_series = self._find_series(profit_loss, ["operating profit"])
        eps_series = self._find_series(profit_loss, ["eps in rs", "eps"])

        roce_series = self._find_series(ratios, ["roce"])
        book_value_series = self._find_series(ratios, ["book value"])
        cfo_series = self._find_series(cash_flow, ["cash from operating activity", "cash from operations"])

        pb_series = self._dataset_values_to_year_map(chart_datasets, "Price to book value")
        ps_series = self._dataset_values_to_year_map(chart_datasets, "Market Cap to Sales")
        chart_book_value_series = self._dataset_values_to_year_map(chart_datasets, "Book value")
        ratios_pb_series = self._find_series(ratios, ["price to book value", "price to book"])
        ratios_ps_series = self._find_series(ratios, ["price to sales", "market cap to sales"])
        ratios_pcf_series = self._find_series(ratios, ["price to cash flow", "price to cashflow"])
        if not pb_series:
            pb_series = ratios_pb_series
        if not ps_series:
            ps_series = ratios_ps_series
        if chart_book_value_series:
            book_value_series = chart_book_value_series

        promoter_holding_series = self._aggregate_investor_payload(investor_payload)
        if not promoter_holding_series:
            promoter_holding_series = self._find_series(shareholding, ["promoters +", "promoters"])
        promoter_pledging_series = self._pledged_payload_to_year_map(nse_pledged_payload)
        if not promoter_pledging_series:
            promoter_pledging_series = self._find_series(shareholding, ["pledged percentage", "pledged %", "pledged"])

        interest_coverage_series = {}
        if operating_profit_series and interest_series:
            years = sorted(set(operating_profit_series.keys()) | set(interest_series.keys()))
            for year in years:
                operating_profit = self._coerce_numeric(operating_profit_series.get(year))
                interest = self._coerce_numeric(interest_series.get(year))
                if pd.isna(operating_profit) or pd.isna(interest):
                    continue
                if interest == 0:
                    interest_coverage_series[year] = np.nan
                else:
                    interest_coverage_series[year] = operating_profit / interest

        pcf_series = ratios_pcf_series if ratios_pcf_series else {}
        if ps_series and sales_series and cfo_series:
            years = sorted(set(ps_series.keys()) & set(sales_series.keys()) & set(cfo_series.keys()))
            for year in years:
                ps_value = self._coerce_numeric(ps_series.get(year))
                sales_value = self._coerce_numeric(sales_series.get(year))
                cfo_value = self._coerce_numeric(cfo_series.get(year))
                if pd.isna(ps_value) or pd.isna(sales_value) or pd.isna(cfo_value) or cfo_value == 0:
                    continue
                implied_market_cap = ps_value * sales_value
                pcf_series[year] = implied_market_cap / cfo_value

        frames = [
            self._series_to_frame(sales_series, "sales"),
            self._series_to_frame(other_income_series, "other_income"),
            self._series_to_frame(eps_series, "eps"),
            self._series_to_frame(roce_series, "roce_pct"),
            self._series_to_frame(pb_series, "pb_ratio"),
            self._series_to_frame(ps_series, "ps_ratio"),
            self._series_to_frame(pcf_series, "pcf_ratio"),
            self._series_to_frame(book_value_series, "book_value"),
            self._series_to_frame(cfo_series, "cash_from_operations"),
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
            "sales",
            "book_value",
            "eps",
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

        # Annual fundamentals often lag live valuation-series updates by one reporting cycle.
        # Carry forward the latest known annual values so the current year row remains usable.
        carry_forward_columns = [
            "sales",
            "book_value",
            "eps",
            "sales_growth_pct",
            "roce_pct",
            "book_value_growth_pct",
            "eps_growth_pct",
            "promoter_holding_pct",
            "promoter_pledging_pct",
            "quality_turnover_pct",
            "interest_coverage_ratio",
        ]
        result = result.sort_values("year").reset_index(drop=True)
        result[carry_forward_columns] = result[carry_forward_columns].ffill()

        return result[required_columns].sort_values("year").reset_index(drop=True)

    def generate(self, symbols, metadata_map, existing_output_df=None, checkpoint_path=None, checkpoint_every=0):
        rows = []
        if existing_output_df is not None and not existing_output_df.empty:
            rows.append(self._normalize_existing_output(existing_output_df))
        summary = GenerationSummary(total_symbols=len(symbols))
        checkpoint_every = int(checkpoint_every or 0)
        processed_since_checkpoint = 0

        for index, symbol in enumerate(symbols, start=1):
            print(f"[{index}/{len(symbols)}] Processing {symbol}")
            metadata = metadata_map.get(symbol, {"Sector": "Unknown", "Market Cap": np.nan})
            try:
                html = self.fetch_company_html(symbol)
                company_df = self.parse_company_page(symbol, html, metadata)
                if not company_df.empty:
                    rows.append(company_df)
                    summary.successful_symbols += 1
                    processed_since_checkpoint += 1
                else:
                    print(f"  No yearly data parsed for {symbol}")
                    summary.failed_symbols += 1
            except Exception as exc:
                print(f"  Failed for {symbol}: {exc}")
                summary.failed_symbols += 1

            if checkpoint_path and checkpoint_every > 0 and processed_since_checkpoint >= checkpoint_every:
                checkpoint_df = self._normalize_existing_output(pd.concat(rows, ignore_index=True)) if rows else self._empty_output_frame()
                os.makedirs(os.path.dirname(checkpoint_path) or REPO_BASE_PATH, exist_ok=True)
                checkpoint_df.to_csv(checkpoint_path, index=False)
                print(
                    f"Checkpoint saved to {checkpoint_path} "
                    f"(rows={len(checkpoint_df)}, processed_symbols={index}/{len(symbols)})"
                )
                processed_since_checkpoint = 0

            time.sleep(self.request_delay)

        if rows:
            output_df = self._normalize_existing_output(pd.concat(rows, ignore_index=True))
        else:
            output_df = self._empty_output_frame()

        if checkpoint_path:
            os.makedirs(os.path.dirname(checkpoint_path) or REPO_BASE_PATH, exist_ok=True)
            output_df.to_csv(checkpoint_path, index=False)
            print(f"Checkpoint saved to {checkpoint_path} (rows={len(output_df)})")

        summary.output_rows = len(output_df)
        return output_df, summary


def parse_args():
    parser = argparse.ArgumentParser(description="Generate yearly historical fundamentals for strategy modules.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_FILE, help="Output CSV path.")
    parser.add_argument("--sample-size", type=int, default=0, help="Limit processing to the first N symbols.")
    parser.add_argument("--symbols", default="", help="Comma-separated list of symbols to process.")
    parser.add_argument("--min-successful-symbols", type=int, default=1, help="Minimum successful symbols required.")
    parser.add_argument("--request-delay", type=float, default=0.4, help="Delay between requests in seconds.")
    parser.add_argument(
        "--checkpoint-path",
        default="",
        help="Optional CSV checkpoint path to persist intermediate results.",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=50,
        help="Write checkpoint after every N processed symbols when checkpoint path is set.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing checkpoint/output file and skip already processed tickers.",
    )
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

    checkpoint_path = os.path.join(REPO_BASE_PATH, args.checkpoint_path) if args.checkpoint_path else ""
    output_path = os.path.join(REPO_BASE_PATH, args.output)

    existing_df = pd.DataFrame()
    resume_source = ""
    if args.resume:
        candidate_paths = [path for path in [checkpoint_path, output_path] if path]
        for candidate in candidate_paths:
            if os.path.exists(candidate):
                try:
                    existing_df = pd.read_csv(candidate)
                    resume_source = candidate
                    break
                except Exception:
                    continue

    if not existing_df.empty and "ticker" in existing_df.columns:
        existing_tickers = set(existing_df["ticker"].dropna().astype(str).str.upper().tolist())
        before_count = len(symbols)
        symbols = [symbol for symbol in symbols if symbol.upper() not in existing_tickers]
        print(
            f"Resuming from {resume_source or 'existing data'}: "
            f"skipped {before_count - len(symbols)} already-processed symbols, remaining={len(symbols)}"
        )

    output_df, summary = generator.generate(
        symbols,
        metadata_map,
        existing_output_df=existing_df,
        checkpoint_path=checkpoint_path or None,
        checkpoint_every=args.checkpoint_every,
    )
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
