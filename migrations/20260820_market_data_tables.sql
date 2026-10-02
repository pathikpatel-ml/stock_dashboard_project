-- ============================================================
-- Market Data Tables Migration
-- Run this in your Supabase SQL editor (or via psql/DATABASE_URL) BEFORE
-- deploying the code that reads/writes these tables.
-- All statements are idempotent (safe to re-run).
--
-- Replaces the CSV-file data pipeline (V20 signals, Turtle signals,
-- fundamentals, live prices, NSE universe/categories) with Postgres
-- tables. Two shapes, matching the two shapes the CSVs already had:
--
--   * "Rolling snapshot" tables (nse_universe, nse_categories,
--     turtle_live_prices, turtle_fundamentals, turtle_sector_pulse,
--     market_trend_analysis) -- one row per key, UPSERTed in place on
--     every run. Directly equivalent to the old overwritten-in-place
--     CSVs (turtle_live_prices.csv etc.) -- no history kept, matches
--     existing behaviour exactly.
--
--   * Time-series families (Turtle signals, V20 signals) -- HYBRID:
--     a "_latest" table (one row per symbol, what the dashboard reads,
--     always fast) plus a "_history" table (append-only, one row per
--     symbol per run date, for trend analysis). This replaces the old
--     "commit a new dated CSV file every run" pattern, which is what
--     caused real git bloat (446 historical V20 files already in git
--     history) and real git race conditions (an add/add conflict this
--     session, when a scheduled cron and a manual push both touched
--     the same dated turtle_signals file).
-- ============================================================

-- ---------------------------------------------------------------
-- 1. NSE universe (was NSE_EQ_All_Stocks_Analysis.csv) -- rolling
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nse_universe (
    symbol                    TEXT PRIMARY KEY,
    company_name              TEXT,
    sector                    TEXT,
    industry                  TEXT,
    market_cap                DOUBLE PRECISION,
    net_profit_cr             DOUBLE PRECISION,
    roce_pct                  DOUBLE PRECISION,
    roe_pct                   DOUBLE PRECISION,
    debt_to_equity            DOUBLE PRECISION,
    latest_quarter_profit_cr  DOUBLE PRECISION,
    last_3q_profits_cr        TEXT,   -- comma-separated in the source data, kept as-is
    public_holding_pct        DOUBLE PRECISION,
    is_bank_finance           BOOLEAN,
    is_psu                    BOOLEAN,
    passes_criteria           BOOLEAN,
    screening_date            DATE,
    ma10                      DOUBLE PRECISION,
    ma50                      DOUBLE PRECISION,
    ma100                     DOUBLE PRECISION,
    ma200                     DOUBLE PRECISION,
    current_price             DOUBLE PRECISION,
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 2. Market trend analysis (was Master_company_market_trend_analysis.csv)
--    -- rolling. Same shape as nse_universe minus the MA/price/passes
--    columns; kept separate since it's a genuinely different upstream
--    input (feeds generate_daily_signals.py), not just a smaller view.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_trend_analysis (
    symbol                    TEXT PRIMARY KEY,
    company_name              TEXT,
    sector                    TEXT,
    industry                  TEXT,
    market_cap                DOUBLE PRECISION,
    net_profit_cr             DOUBLE PRECISION,
    roce_pct                  DOUBLE PRECISION,
    roe_pct                   DOUBLE PRECISION,
    debt_to_equity            DOUBLE PRECISION,
    latest_quarter_profit_cr  DOUBLE PRECISION,
    last_3q_profits_cr        TEXT,
    public_holding_pct        DOUBLE PRECISION,
    is_bank_finance           BOOLEAN,
    is_psu                    BOOLEAN,
    screening_date            DATE,
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 3. NSE index/category membership (was nse_categories.csv) -- rolling
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nse_categories (
    symbol         TEXT PRIMARY KEY,
    nse_categories TEXT,   -- comma-joined index tags, kept as-is (matches CSV shape)
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 4. Turtle intraday live prices (was turtle_live_prices.csv) -- rolling
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtle_live_prices (
    symbol       TEXT PRIMARY KEY,
    live_price   DOUBLE PRECISION,
    price_as_of  TIMESTAMPTZ,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 5. Turtle standalone/consolidated fundamentals (was
--    turtle_screener_fundamentals.csv) -- rolling
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtle_fundamentals (
    symbol                  TEXT PRIMARY KEY,
    ttm_net_profit          DOUBLE PRECISION,
    max_annual_net_profit   DOUBLE PRECISION,
    ttm_net_sales           DOUBLE PRECISION,
    max_annual_net_sales    DOUBLE PRECISION,
    -- screener.in's own sector/industry classification (2026-09) -- a real 12/22/58/188-tier
    -- hierarchy (Broad Sector -> Sector -> Broad Industry -> Industry), extracted from the same
    -- company-page response already fetched here for TTM profit/sales. See
    -- modules/turtle/screener.py::run_pipeline for how Sector/Broad_Sector are preferred over
    -- the universe CSV's cruder Yahoo Finance "Sector" tag.
    broad_sector            TEXT,
    sector                  TEXT,
    broad_industry          TEXT,
    industry                TEXT,
    -- Turtle Quant's 9 fundamental quality/valuation flags (2026-10-01) -- 10-year CAGR/ROCE
    -- from screener.in's Balance Sheet/Ratios/Cash Flows/Profit & Loss history (same page,
    -- zero extra screener.in requests), plus one extra yfinance monthly-price fetch per symbol
    -- for the 3 valuation-ratio checks (5yr-avg P/B, P/S, P/CF vs current). See
    -- modules/turtle/quality_flags.py for every formula and documented assumption (ROCE as a
    -- 10-year average not a per-year minimum; zero-interest treated as an automatic pass on
    -- interest coverage; promoter holding scoped to the real ~3-year window screener.in's free
    -- shareholding data actually has, not the originally-asked 10 years). All nullable --
    -- insufficient history -> NULL, never a guessed/short-window value.
    book_value_cagr_10y        DOUBLE PRECISION,
    book_value_growth_flag     BOOLEAN,
    eps_cagr_10y                DOUBLE PRECISION,
    eps_growth_flag             BOOLEAN,
    -- ROE (not screener.in's own ROCE/ROE row), derived from Net Profit / Book Value --
    -- see modules/turtle/quality_flags.py::roe_by_year's docstring for why (screener.in's free
    -- "Ratios" history has ROCE for non-financial companies, ROE for banks/NBFCs, never both).
    roe_avg_10y                 DOUBLE PRECISION,
    roe_flag                    BOOLEAN,
    sales_cagr_10y              DOUBLE PRECISION,
    sales_growth_flag           BOOLEAN,
    promoter_holding_change_3y  DOUBLE PRECISION,
    promoter_holding_flag       BOOLEAN,
    -- Promoter Pledge (2026-10-02) -- sourced from NSE's own corporate-pledgedata API (the
    -- primary regulatory source), not screener.in (confirmed zero pledge data on its free
    -- tier). Keyed by the exact NSE symbol already used everywhere -- see
    -- modules/turtle/nse_shareholding.py.
    promoter_pledge_pct         DOUBLE PRECISION,
    promoter_pledge_flag        BOOLEAN,
    interest_coverage           DOUBLE PRECISION,
    interest_coverage_flag      BOOLEAN,
    -- 2026-10-02 additions: Quality of Turnover (Other Income / Total Revenue, a real red-flag
    -- check) and 3 category-aggregate flags (Growth/Red Flag/Value) -- see
    -- modules/turtle/quality_flags.py's module docstring for the full redesign: growth checks
    -- now require EVERY individual year to clear the threshold, not just the overall CAGR/
    -- average (those CAGR/average columns above are kept for debugging/export only). Promoter
    -- Pledge is NOT included in red_flag_category_flag -- still unavailable on screener.in's
    -- free tier; a Moneycontrol-based version is a deferred follow-up, not yet built.
    quality_of_turnover_pct     DOUBLE PRECISION,
    quality_of_turnover_flag    BOOLEAN,
    pb_current                  DOUBLE PRECISION,
    pb_5y_avg                   DOUBLE PRECISION,
    pb_flag                     BOOLEAN,
    ps_current                  DOUBLE PRECISION,
    ps_5y_avg                   DOUBLE PRECISION,
    ps_flag                     BOOLEAN,
    pcf_current                 DOUBLE PRECISION,
    pcf_5y_avg                  DOUBLE PRECISION,
    pcf_flag                    BOOLEAN,
    growth_category_flag        BOOLEAN,
    red_flag_category_flag      BOOLEAN,
    value_category_flag         BOOLEAN,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 6. Turtle Sector Pulse (was turtle_sector_pulse.csv) -- rolling
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtle_sector_pulse (
    sector          TEXT PRIMARY KEY,
    ath_price_flag  BOOLEAN,
    rs_vs_nifty50   DOUBLE PRECISION,
    -- 2026-10-01: how many stocks make up this row -- a curated NSE index's real membership
    -- count for the 12 index rows, or the screener.in-Sector group size for the ~22 sector
    -- rows (see modules/turtle/screener.py::compute_sector_breadth_pulse). Purely informational
    -- (e.g. "helps you judge how much a single outlier stock can skew a small sector's numbers).
    stock_count     INTEGER,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 7. Turtle signals -- latest (dashboard reads this) + history (append-only)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtle_signals_latest (
    symbol               TEXT PRIMARY KEY,
    company              TEXT,
    broad_sector         TEXT,  -- screener.in's 12-value macro sector (2026-09); see turtle_fundamentals
    sector               TEXT,
    industry             TEXT,
    current_price        DOUBLE PRECISION,
    ath_price_flag       BOOLEAN,
    ttm_net_profit       DOUBLE PRECISION,
    ath_profit_flag      BOOLEAN,
    above_ma212_flag     BOOLEAN,
    rs_peer_group        TEXT,
    rs_vs_sector         DOUBLE PRECISION,
    rs_vs_benchmark      DOUBLE PRECISION,
    outperformance_flag  BOOLEAN,
    ttm_net_sales        DOUBLE PRECISION,
    ath_sales            DOUBLE PRECISION,
    ath_sales_flag       BOOLEAN,
    signal               TEXT,
    signal_change        TEXT,  -- e.g. "EXIT -> HOLD", "HOLD -> ADD", "NEW", or NULL if unchanged
                                 -- (added 2026-09-01; see generate_turtle_signals.py's
                                 -- _fetch_previous_signals/_signal_change)
    signal_date          DATE NOT NULL,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_turtle_signals_latest_signal ON turtle_signals_latest(signal);

CREATE TABLE IF NOT EXISTS turtle_signals_history (
    id                   BIGSERIAL PRIMARY KEY,
    symbol               TEXT NOT NULL,
    company              TEXT,
    broad_sector         TEXT,  -- see turtle_signals_latest's column comment above
    sector               TEXT,
    industry             TEXT,
    current_price        DOUBLE PRECISION,
    ath_price_flag       BOOLEAN,
    ttm_net_profit       DOUBLE PRECISION,
    ath_profit_flag      BOOLEAN,
    above_ma212_flag     BOOLEAN,
    rs_peer_group        TEXT,
    rs_vs_sector         DOUBLE PRECISION,
    rs_vs_benchmark      DOUBLE PRECISION,
    outperformance_flag  BOOLEAN,
    ttm_net_sales        DOUBLE PRECISION,
    ath_sales            DOUBLE PRECISION,
    ath_sales_flag       BOOLEAN,
    signal               TEXT,
    signal_change        TEXT,  -- see turtle_signals_latest's column comment above
    signal_date          DATE NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, signal_date)   -- idempotent re-runs on the same day upsert, not duplicate
);
CREATE INDEX IF NOT EXISTS idx_turtle_signals_history_symbol ON turtle_signals_history(symbol);
CREATE INDEX IF NOT EXISTS idx_turtle_signals_history_date ON turtle_signals_history(signal_date);

-- ---------------------------------------------------------------
-- 7b. Turtle Quant signals -- a pure fundamental quality/valuation screen (10yr book value/EPS/
--     sales growth, ROCE, promoter holding trend, interest coverage, P/B-P/S-P/CF vs. 5yr own
--     average). Added 2026-09-02 as a weekly RS/SuperTrend/ADX/RSI technical-signal system;
--     that entire system (and its companion turtlequant_signals_history/
--     turtlequant_signal_transitions tables) was REMOVED 2026-10-02 per explicit user request
--     (the user doesn't trade off it) -- only the fundamental flags (added 2026-10-01) remain.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtlequant_signals_latest (
    symbol               TEXT PRIMARY KEY,
    company              TEXT,
    broad_sector         TEXT,  -- screener.in's 12-value macro sector (2026-09-24); see turtle_fundamentals
    sector               TEXT,
    industry             TEXT,
    current_price        DOUBLE PRECISION,
    -- Turtle Quant's 9 fundamental quality/valuation flags (2026-10-01) -- see
    -- turtle_fundamentals' own column comment above for the full explanation; same values,
    -- threaded through by modules/turtlequant/screener.py the same way Broad_Sector/Sector are.
    book_value_cagr_10y        DOUBLE PRECISION,
    book_value_growth_flag     BOOLEAN,
    eps_cagr_10y                DOUBLE PRECISION,
    eps_growth_flag             BOOLEAN,
    -- ROE (not screener.in's own ROCE/ROE row), derived from Net Profit / Book Value --
    -- see modules/turtle/quality_flags.py::roe_by_year's docstring for why (screener.in's free
    -- "Ratios" history has ROCE for non-financial companies, ROE for banks/NBFCs, never both).
    roe_avg_10y                 DOUBLE PRECISION,
    roe_flag                    BOOLEAN,
    sales_cagr_10y              DOUBLE PRECISION,
    sales_growth_flag           BOOLEAN,
    promoter_holding_change_3y  DOUBLE PRECISION,
    promoter_holding_flag       BOOLEAN,
    -- Promoter Pledge (2026-10-02) -- sourced from NSE's own corporate-pledgedata API (the
    -- primary regulatory source), not screener.in (confirmed zero pledge data on its free
    -- tier). Keyed by the exact NSE symbol already used everywhere -- see
    -- modules/turtle/nse_shareholding.py.
    promoter_pledge_pct         DOUBLE PRECISION,
    promoter_pledge_flag        BOOLEAN,
    interest_coverage           DOUBLE PRECISION,
    interest_coverage_flag      BOOLEAN,
    -- 2026-10-02: Quality of Turnover + the 3 category-aggregate flags the dashboard actually
    -- displays (Growth/Red Flag/Value) -- see turtle_fundamentals' own column comment above.
    quality_of_turnover_pct     DOUBLE PRECISION,
    quality_of_turnover_flag    BOOLEAN,
    pb_current                  DOUBLE PRECISION,
    pb_5y_avg                   DOUBLE PRECISION,
    pb_flag                     BOOLEAN,
    ps_current                  DOUBLE PRECISION,
    ps_5y_avg                   DOUBLE PRECISION,
    ps_flag                     BOOLEAN,
    pcf_current                 DOUBLE PRECISION,
    pcf_5y_avg                  DOUBLE PRECISION,
    pcf_flag                    BOOLEAN,
    growth_category_flag        BOOLEAN,
    red_flag_category_flag      BOOLEAN,
    value_category_flag         BOOLEAN,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Migration (2026-10-02, run once by hand via DATABASE_URL -- this file is a reference copy,
-- not applied by any migration tooling, same as every other table here):
--   DROP INDEX IF EXISTS idx_turtlequant_signals_latest_signal;
--   ALTER TABLE turtlequant_signals_latest
--       DROP COLUMN IF EXISTS signal_date, DROP COLUMN IF EXISTS rs_long_term,
--       DROP COLUMN IF EXISTS rs_short_term, DROP COLUMN IF EXISTS adx,
--       DROP COLUMN IF EXISTS rsi, DROP COLUMN IF EXISTS supertrend_direction,
--       DROP COLUMN IF EXISTS volume_building, DROP COLUMN IF EXISTS price_above_ma13,
--       DROP COLUMN IF EXISTS signal;
--   DROP TABLE IF EXISTS turtlequant_signals_history;
--   DROP TABLE IF EXISTS turtlequant_signal_transitions;

-- ---------------------------------------------------------------
-- 8. V20 signals -- "latest" only, NOT the same hybrid shape as Turtle.
--
--    V20's own data shape is different from Turtle's: a row is a historical
--    Buy/Sell candle SEQUENCE, not a one-row-per-symbol classification -- a
--    single symbol can have 15+ rows (verified live: up to 17 in one day's
--    real output). generate_daily_signals.py re-scans full price history
--    and re-detects every currently-qualifying sequence FROM SCRATCH each
--    run, so this table is a full daily snapshot, not an incremental diff --
--    a "_history" table would just re-store ~the same 880 rows every day
--    with no new trend information, so it's deliberately omitted (unlike
--    Turtle, where the same-symbol classification genuinely changes day to
--    day and a history table captures that).
--
--    Primary key is (symbol, buy_date) -- verified live, zero duplicate
--    pairs in real output. Written via REPLACE semantics (delete all +
--    bulk insert in one transaction, not upsert) because a sequence that
--    no longer qualifies must be REMOVED, not left behind as a stale row --
--    see database/market_data_writer.py::replace_table_contents.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS v20_signals_latest (
    symbol                  TEXT NOT NULL,
    buy_date                DATE NOT NULL,
    buy_price_low           DOUBLE PRECISION,
    sell_date               DATE,
    sell_price_high         DOUBLE PRECISION,
    sequence_gain_percent   DOUBLE PRECISION,
    days_in_sequence        INTEGER,
    run_date                DATE NOT NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, buy_date)
);
CREATE INDEX IF NOT EXISTS idx_v20_signals_latest_symbol ON v20_signals_latest(symbol);

-- ---------------------------------------------------------------
-- 9. Least-privilege role for GitHub Actions batch writes.
--    Deliberately NOT the admin DATABASE_URL role and NOT the
--    SUPABASE_SERVICE_KEY (that key bypasses RLS entirely and has
--    full access to users/sessions/kite_settings/etc -- a leaked
--    GitHub Secret with that key would expose the whole database,
--    not just market data). This role can only touch the 10 tables
--    above -- no SELECT/INSERT/UPDATE/DELETE on anything auth- or
--    broker-related.
--
--    Password is set separately (see migration notes) -- never commit
--    a real password in this file. Run this section once, then:
--      ALTER ROLE market_data_writer WITH PASSWORD '<generated>';
--    and build the GitHub Secret connection string from that password.
-- ---------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'market_data_writer') THEN
        CREATE ROLE market_data_writer WITH LOGIN;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE postgres TO market_data_writer;
GRANT USAGE ON SCHEMA public TO market_data_writer;

GRANT SELECT, INSERT, UPDATE ON
    nse_universe,
    market_trend_analysis,
    nse_categories,
    turtle_live_prices,
    turtle_fundamentals,
    turtle_sector_pulse,
    turtle_signals_latest,
    turtle_signals_history,
    turtlequant_signals_latest,
    v20_signals_latest
TO market_data_writer;

-- v20_signals_latest alone also needs DELETE: it's written with REPLACE semantics (delete all
-- + bulk insert), not upsert, since a sequence that no longer qualifies must be removed, not
-- left as a stale row (see the table's own comment above).
GRANT DELETE ON v20_signals_latest TO market_data_writer;

-- turtle_signals_latest (2026-09-23): upserted, not replaced, but a symbol rejected for
-- insufficient_monthly_data (not yet 12 months of listed price history) must still be
-- deletable individually so its stale pre-screening row doesn't linger forever -- see
-- generate_turtle_signals.py's targeted delete_by_symbols() call.
GRANT DELETE ON turtle_signals_latest TO market_data_writer;

-- turtle_sector_pulse (2026-10-01): written with REPLACE semantics (delete-all + bulk insert,
-- same as v20_signals_latest) since a sector (screener.in Sector or curated NSE index) can
-- legitimately have zero members on a later run -- see generate_turtle_signals.py's write call.
GRANT DELETE ON turtle_sector_pulse TO market_data_writer;

GRANT USAGE, SELECT ON
    turtle_signals_history_id_seq
TO market_data_writer;
