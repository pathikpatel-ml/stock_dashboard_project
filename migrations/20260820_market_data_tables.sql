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
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 6. Turtle Sector Pulse (was turtle_sector_pulse.csv) -- rolling
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtle_sector_pulse (
    sector          TEXT PRIMARY KEY,
    ath_price_flag  BOOLEAN,
    rs_vs_nifty50   DOUBLE PRECISION,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------
-- 7. Turtle signals -- latest (dashboard reads this) + history (append-only)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtle_signals_latest (
    symbol               TEXT PRIMARY KEY,
    company              TEXT,
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
-- 7b. Turtle Quant signals -- same hybrid latest+history shape as Turtle Strategy's own
--     tables above, but an unrelated methodology (weekly RS vs NSE:NIFTY + SuperTrend/ADX/RSI,
--     "Turtle Quant" firm, not Turtle Wealth). Added 2026-09-02.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtlequant_signals_latest (
    symbol               TEXT PRIMARY KEY,
    company              TEXT,
    sector               TEXT,
    industry             TEXT,
    current_price        DOUBLE PRECISION,
    rs_long_term         DOUBLE PRECISION,
    rs_short_term        DOUBLE PRECISION,
    adx                  DOUBLE PRECISION,
    rsi                  DOUBLE PRECISION,
    supertrend_direction TEXT,   -- 'BULLISH' / 'BEARISH'
    volume_building      BOOLEAN,
    price_above_ma13     BOOLEAN,
    signal               TEXT,   -- BUY / HOLD / SELL
    signal_date          DATE NOT NULL,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_turtlequant_signals_latest_signal ON turtlequant_signals_latest(signal);

CREATE TABLE IF NOT EXISTS turtlequant_signals_history (
    id                   BIGSERIAL PRIMARY KEY,
    symbol               TEXT NOT NULL,
    company              TEXT,
    sector               TEXT,
    industry             TEXT,
    current_price        DOUBLE PRECISION,
    rs_long_term         DOUBLE PRECISION,
    rs_short_term        DOUBLE PRECISION,
    adx                  DOUBLE PRECISION,
    rsi                  DOUBLE PRECISION,
    supertrend_direction TEXT,
    volume_building      BOOLEAN,
    price_above_ma13     BOOLEAN,
    signal               TEXT,
    signal_date          DATE NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, signal_date)
);
CREATE INDEX IF NOT EXISTS idx_turtlequant_signals_history_symbol ON turtlequant_signals_history(symbol);
CREATE INDEX IF NOT EXISTS idx_turtlequant_signals_history_date ON turtlequant_signals_history(signal_date);

-- ---------------------------------------------------------------
-- 7c. Turtle Quant signal transitions -- a curated event log, NOT one row per week. Only
--     written when a symbol's signal actually CHANGES between two distinct recorded weeks
--     (never for the same week being re-evaluated intraday as fresher data comes in -- see
--     generate_turtlequant_signals.py's transition-detection logic), and only when the new
--     signal is BUY or SELL (a move into/out of HOLD isn't logged as an event here -- per the
--     user's own framing, HOLD isn't an actionable "entry"/"exit" point, 2026-09-05). This is
--     what actually answers "when did this stock last enter a fresh BUY, and when did it exit
--     via SELL" as a real sequence, since turtlequant_signals_history's Last_Buy_Date/
--     Last_Sell_Date (see modules/turtlequant/compute.py::last_signal_dates) only finds the
--     most recent OCCURRENCE of each, not a curated alternating event list. Added 2026-09-05.
--     Necessarily starts empty and only from today forward -- no historical backfill is
--     possible (the underlying signal history itself only exists from today).
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS turtlequant_signal_transitions (
    id               BIGSERIAL PRIMARY KEY,
    symbol           TEXT NOT NULL,
    transition_date  DATE NOT NULL,   -- the (new) week's signal_date this transition took effect
    from_signal      TEXT,            -- previous recorded signal; NULL if this is the symbol's
                                       -- very first recorded signal ever (nothing to transition from)
    to_signal        TEXT NOT NULL,   -- 'BUY' or 'SELL' -- see comment above on scope
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, transition_date)
);
CREATE INDEX IF NOT EXISTS idx_turtlequant_transitions_symbol ON turtlequant_signal_transitions(symbol);

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
    turtlequant_signals_history,
    turtlequant_signal_transitions,
    v20_signals_latest
TO market_data_writer;

-- v20_signals_latest alone also needs DELETE: it's written with REPLACE semantics (delete all
-- + bulk insert), not upsert, since a sequence that no longer qualifies must be removed, not
-- left as a stale row (see the table's own comment above). No other table needs DELETE.
GRANT DELETE ON v20_signals_latest TO market_data_writer;

GRANT USAGE, SELECT ON
    turtle_signals_history_id_seq,
    turtlequant_signals_history_id_seq,
    turtlequant_signal_transitions_id_seq
TO market_data_writer;
