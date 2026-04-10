import pandas as pd


REQUIRED_COLUMNS = [
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

OPTIONAL_RAW_COLUMNS = [
    "sales",
    "book_value",
    "eps",
]


def _prepare_panel(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["ticker", "year", *REQUIRED_COLUMNS])

    panel = df.copy()

    if isinstance(panel.index, pd.MultiIndex):
        index_names = [name or f"level_{idx}" for idx, name in enumerate(panel.index.names)]
        panel = panel.reset_index()
        rename_map = {}
        if index_names:
            rename_map[index_names[0]] = "ticker"
        if len(index_names) > 1:
            rename_map[index_names[1]] = "year"
        panel = panel.rename(columns=rename_map)

    if "ticker" not in panel.columns or "year" not in panel.columns:
        raise ValueError("DataFrame must include a MultiIndex or columns for ticker and year.")

    missing = [column for column in REQUIRED_COLUMNS if column not in panel.columns]
    if missing:
        raise ValueError(f"DataFrame is missing required columns: {missing}")

    for column in OPTIONAL_RAW_COLUMNS:
        if column not in panel.columns:
            panel[column] = pd.NA

    panel = panel.copy()
    panel["ticker"] = panel["ticker"].astype(str).str.upper().str.strip()
    panel["year"] = pd.to_numeric(panel["year"], errors="coerce")
    panel = panel.dropna(subset=["ticker", "year"])
    panel["year"] = panel["year"].astype(int)
    panel = panel.sort_values(["ticker", "year"]).reset_index(drop=True)

    if panel.duplicated(subset=["ticker", "year"]).any():
        duplicates = panel.loc[panel.duplicated(subset=["ticker", "year"], keep=False), ["ticker", "year"]]
        raise ValueError(f"Duplicate ticker-year rows found: {duplicates.to_dict('records')[:5]}")

    numeric_columns = [column for column in REQUIRED_COLUMNS if column not in {"sector"}]
    numeric_columns.extend(OPTIONAL_RAW_COLUMNS)
    for column in numeric_columns:
        panel[column] = pd.to_numeric(panel[column], errors="coerce")

    panel["sector"] = panel["sector"].fillna("Unknown").astype(str).str.strip()
    panel.loc[panel["sector"].eq(""), "sector"] = "Unknown"
    return panel


def calculate_derived_metrics(df):
    panel = _prepare_panel(df)
    if panel.empty:
        return panel

    grouped = panel.groupby("ticker", group_keys=False)
    panel["3yr_avg_sales_growth"] = grouped["sales_growth_pct"].transform(
        lambda series: series.rolling(window=3, min_periods=3).mean()
    )
    panel["3yr_avg_roce"] = grouped["roce_pct"].transform(
        lambda series: series.rolling(window=3, min_periods=3).mean()
    )
    panel["5yr_avg_pb"] = grouped["pb_ratio"].transform(
        lambda series: series.rolling(window=5, min_periods=5).mean()
    )
    panel["5yr_avg_ps"] = grouped["ps_ratio"].transform(
        lambda series: series.rolling(window=5, min_periods=5).mean()
    )
    panel["5yr_avg_pcf"] = grouped["pcf_ratio"].transform(
        lambda series: series.rolling(window=5, min_periods=5).mean()
    )
    panel["10yr_change_promoter_holding"] = grouped["promoter_holding_pct"].transform(
        lambda series: series - series.shift(9)
    )
    panel["10yr_avg_book_value_growth"] = grouped["book_value_growth_pct"].transform(
        lambda series: series.rolling(window=10, min_periods=10).mean()
    )
    panel["10yr_avg_eps_growth"] = grouped["eps_growth_pct"].transform(
        lambda series: series.rolling(window=10, min_periods=10).mean()
    )
    panel["10yr_avg_roce"] = grouped["roce_pct"].transform(
        lambda series: series.rolling(window=10, min_periods=10).mean()
    )
    panel["10yr_avg_sales_growth"] = grouped["sales_growth_pct"].transform(
        lambda series: series.rolling(window=10, min_periods=10).mean()
    )
    panel["10yr_period_book_value_growth"] = grouped["book_value"].transform(
        lambda series: _period_cagr(series, periods_back=9)
    )
    panel["10yr_period_eps_growth"] = grouped["eps"].transform(
        lambda series: _period_cagr(series, periods_back=9)
    )
    panel["10yr_period_sales_growth"] = grouped["sales"].transform(
        lambda series: _period_cagr(series, periods_back=9)
    )
    return panel


def _period_cagr(series, periods_back):
    earlier = series.shift(periods_back)
    valid = (earlier > 0) & (series > 0)
    result = pd.Series(index=series.index, dtype="float64")
    result.loc[valid] = (((series.loc[valid] / earlier.loc[valid]) ** (1 / periods_back)) - 1) * 100
    return result


def get_current_year_snapshot(df, current_year):
    features = calculate_derived_metrics(df)
    if features.empty:
        return features
    return features[features["year"] == int(current_year)].copy().reset_index(drop=True)


def sector_ranker(df, current_year, top_n=3):
    current = get_current_year_snapshot(df, current_year)
    if current.empty:
        return current

    ranked = current[current["market_cap"] >= 200].copy()
    if ranked.empty:
        return ranked

    ranked["sales_growth_rank"] = ranked.groupby("sector")["3yr_avg_sales_growth"].rank(
        method="dense", ascending=False, na_option="bottom"
    )
    ranked["roce_rank"] = ranked.groupby("sector")["3yr_avg_roce"].rank(
        method="dense", ascending=False, na_option="bottom"
    )
    ranked["pb_rank"] = ranked.groupby("sector")["pb_ratio"].rank(
        method="dense", ascending=True, na_option="bottom"
    )
    ranked["combined_score"] = ranked["sales_growth_rank"] + ranked["roce_rank"] + ranked["pb_rank"]
    ranked = ranked.sort_values(["sector", "combined_score", "ticker"]).reset_index(drop=True)
    ranked["sector_position"] = ranked.groupby("sector").cumcount() + 1
    ranked = ranked[ranked["sector_position"] <= int(top_n)].copy()

    display_columns = [
        "ticker",
        "year",
        "sector",
        "market_cap",
        "3yr_avg_sales_growth",
        "3yr_avg_roce",
        "pb_ratio",
        "sales_growth_rank",
        "roce_rank",
        "pb_rank",
        "combined_score",
        "sector_position",
    ]
    return ranked[display_columns].reset_index(drop=True)


def quality_filter(df_shortlist, current_year, df=None):
    if df is None:
        current = _prepare_panel(df_shortlist)
        current = calculate_derived_metrics(current)
        current = current[current["year"] == int(current_year)].copy().reset_index(drop=True)
    else:
        current = get_current_year_snapshot(df, current_year)
    if current.empty:
        return current

    if isinstance(df_shortlist, pd.DataFrame):
        if "ticker" in df_shortlist.columns:
            tickers = df_shortlist["ticker"].dropna().astype(str).str.upper().tolist()
        elif "Symbol" in df_shortlist.columns:
            tickers = df_shortlist["Symbol"].dropna().astype(str).str.upper().tolist()
        else:
            tickers = current["ticker"].dropna().astype(str).str.upper().tolist()
    else:
        tickers = [str(ticker).upper() for ticker in df_shortlist]

    filtered = current[current["ticker"].isin(tickers)].copy()
    if filtered.empty:
        return filtered

    filtered["book_value_growth_10y_check"] = filtered["10yr_period_book_value_growth"].fillna(
        filtered["10yr_avg_book_value_growth"]
    )
    filtered["eps_growth_10y_check"] = filtered["10yr_period_eps_growth"].fillna(
        filtered["10yr_avg_eps_growth"]
    )
    filtered["sales_growth_10y_check"] = filtered["10yr_period_sales_growth"].fillna(
        filtered["10yr_avg_sales_growth"]
    )

    filtered["passes_book_value_growth"] = filtered["book_value_growth_10y_check"] > 10
    filtered["passes_eps_growth"] = filtered["eps_growth_10y_check"] > 10
    filtered["passes_roce"] = filtered["10yr_avg_roce"] > 10
    filtered["passes_sales_growth"] = filtered["sales_growth_10y_check"] > 10
    filtered["passes_promoter_holding"] = filtered["10yr_change_promoter_holding"] >= 0
    filtered["passes_promoter_pledging"] = filtered["promoter_pledging_pct"] < 10
    filtered["passes_quality_turnover"] = filtered["quality_turnover_pct"] <= 10
    filtered["passes_interest_coverage"] = filtered["interest_coverage_ratio"] > 5

    check_columns = [
        "passes_book_value_growth",
        "passes_eps_growth",
        "passes_roce",
        "passes_sales_growth",
        "passes_promoter_holding",
        "passes_promoter_pledging",
        "passes_quality_turnover",
        "passes_interest_coverage",
    ]
    filtered["all_quality_checks_pass"] = filtered[check_columns].all(axis=1)

    keep_columns = [
        "ticker",
        "year",
        "sector",
        "10yr_avg_book_value_growth",
        "10yr_avg_eps_growth",
        "10yr_avg_roce",
        "10yr_avg_sales_growth",
        "10yr_period_book_value_growth",
        "10yr_period_eps_growth",
        "10yr_period_sales_growth",
        "book_value_growth_10y_check",
        "eps_growth_10y_check",
        "sales_growth_10y_check",
        "10yr_change_promoter_holding",
        "promoter_pledging_pct",
        "quality_turnover_pct",
        "interest_coverage_ratio",
        *check_columns,
        "all_quality_checks_pass",
    ]
    return filtered[filtered["all_quality_checks_pass"]][keep_columns].reset_index(drop=True)


def quality_filter_diagnostics(df_shortlist, current_year, df=None):
    if df is None:
        current = _prepare_panel(df_shortlist)
        current = calculate_derived_metrics(current)
        current = current[current["year"] == int(current_year)].copy().reset_index(drop=True)
    else:
        current = get_current_year_snapshot(df, current_year)
    if current.empty:
        return current

    if isinstance(df_shortlist, pd.DataFrame):
        if "ticker" in df_shortlist.columns:
            tickers = df_shortlist["ticker"].dropna().astype(str).str.upper().tolist()
        elif "Symbol" in df_shortlist.columns:
            tickers = df_shortlist["Symbol"].dropna().astype(str).str.upper().tolist()
        else:
            tickers = current["ticker"].dropna().astype(str).str.upper().tolist()
    else:
        tickers = [str(ticker).upper() for ticker in df_shortlist]

    diagnostics = current[current["ticker"].isin(tickers)].copy()
    if diagnostics.empty:
        return diagnostics

    diagnostics["book_value_growth_10y_check"] = diagnostics["10yr_period_book_value_growth"].fillna(
        diagnostics["10yr_avg_book_value_growth"]
    )
    diagnostics["eps_growth_10y_check"] = diagnostics["10yr_period_eps_growth"].fillna(
        diagnostics["10yr_avg_eps_growth"]
    )
    diagnostics["sales_growth_10y_check"] = diagnostics["10yr_period_sales_growth"].fillna(
        diagnostics["10yr_avg_sales_growth"]
    )

    diagnostics["passes_book_value_growth"] = diagnostics["book_value_growth_10y_check"] > 10
    diagnostics["passes_eps_growth"] = diagnostics["eps_growth_10y_check"] > 10
    diagnostics["passes_roce"] = diagnostics["10yr_avg_roce"] > 10
    diagnostics["passes_sales_growth"] = diagnostics["sales_growth_10y_check"] > 10
    diagnostics["passes_promoter_holding"] = diagnostics["10yr_change_promoter_holding"] >= 0
    diagnostics["passes_promoter_pledging"] = diagnostics["promoter_pledging_pct"] < 10
    diagnostics["passes_quality_turnover"] = diagnostics["quality_turnover_pct"] <= 10
    diagnostics["passes_interest_coverage"] = diagnostics["interest_coverage_ratio"] > 5

    check_columns = [
        "passes_book_value_growth",
        "passes_eps_growth",
        "passes_roce",
        "passes_sales_growth",
        "passes_promoter_holding",
        "passes_promoter_pledging",
        "passes_quality_turnover",
        "passes_interest_coverage",
    ]
    diagnostics["all_quality_checks_pass"] = diagnostics[check_columns].all(axis=1)
    diagnostics["failed_checks"] = diagnostics[check_columns].apply(
        lambda row: ", ".join(column.replace("passes_", "") for column, value in row.items() if not bool(value)),
        axis=1,
    )

    keep_columns = [
        "ticker",
        "year",
        "sector",
        "10yr_avg_book_value_growth",
        "10yr_avg_eps_growth",
        "10yr_avg_roce",
        "10yr_avg_sales_growth",
        "10yr_period_book_value_growth",
        "10yr_period_eps_growth",
        "10yr_period_sales_growth",
        "book_value_growth_10y_check",
        "eps_growth_10y_check",
        "sales_growth_10y_check",
        "10yr_change_promoter_holding",
        "promoter_pledging_pct",
        "quality_turnover_pct",
        "interest_coverage_ratio",
        *check_columns,
        "all_quality_checks_pass",
        "failed_checks",
    ]
    return diagnostics[keep_columns].reset_index(drop=True)


def value_reversion_signals(df, current_year):
    current = get_current_year_snapshot(df, current_year)
    if current.empty:
        return current

    signaled = current.copy()
    signaled["Buy_Signal"] = (
        (signaled["pb_ratio"] < signaled["5yr_avg_pb"])
        & (signaled["ps_ratio"] < signaled["5yr_avg_ps"])
        & (signaled["pcf_ratio"] < signaled["5yr_avg_pcf"])
    )
    signaled["Sell_Signal"] = (
        (signaled["pb_ratio"] > signaled["5yr_avg_pb"])
        | (signaled["ps_ratio"] > signaled["5yr_avg_ps"])
        | (signaled["pcf_ratio"] > signaled["5yr_avg_pcf"])
    )

    keep_columns = [
        "ticker",
        "year",
        "sector",
        "pb_ratio",
        "ps_ratio",
        "pcf_ratio",
        "5yr_avg_pb",
        "5yr_avg_ps",
        "5yr_avg_pcf",
        "Buy_Signal",
        "Sell_Signal",
    ]
    return signaled[keep_columns].reset_index(drop=True)
