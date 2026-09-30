CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    name          TEXT        NOT NULL DEFAULT '',
    status        TEXT        NOT NULL DEFAULT 'active',
    -- status: 'pending' = awaiting approval, 'active' = approved, 'rejected' = denied, 'deactivated'
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- Migrations for existing deployments (safe to re-run):
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '';
-- ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
-- UPDATE users SET status = 'active', name = 'Admin' WHERE email = 'pathikc129@gmail.com';

CREATE TABLE IF NOT EXISTS kite_settings (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER     NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    api_key_enc             TEXT,
    api_secret_enc          TEXT,
    access_token_enc        TEXT,
    access_token_set_at     TIMESTAMPTZ,
    proximity_threshold_pct REAL        NOT NULL DEFAULT 2.0,
    max_allocation_pct      REAL        NOT NULL DEFAULT 3.0,
    gtt_enabled             BOOLEAN     NOT NULL DEFAULT FALSE,
    schedule_time           TEXT        NOT NULL DEFAULT '08:30',
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT        PRIMARY KEY,
    user_id      INTEGER     REFERENCES users(id) ON DELETE CASCADE,
    data         JSONB       NOT NULL DEFAULT '{}',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL,
    remember_me  BOOLEAN     NOT NULL DEFAULT FALSE,
    ip_address   TEXT,
    user_agent   TEXT
);
CREATE INDEX IF NOT EXISTS sessions_user_id_idx ON sessions(user_id);
CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS kite_exclusions (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol     TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, symbol)
);

CREATE TABLE IF NOT EXISTS turtle_watchlist (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol     TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, symbol)
);

-- Turtle Quant "My Holdings" -- separate from turtle_watchlist above (distinct strategy,
-- distinct namespace, same reasoning as turtle_signals_* vs turtlequant_signals_*).
CREATE TABLE IF NOT EXISTS turtlequant_watchlist (
    id         SERIAL PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol     TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, symbol)
);

-- Simulator tab: agentic paper-trading (LangGraph + OpenRouter LLM) over the app's real V20
-- and Turtle signals. Per-user, accessed via the same SUPABASE_URL/SUPABASE_SERVICE_KEY REST
-- path as every other table on this page -- written by a daily GitHub Actions batch job
-- (generate_simulator_decisions.py), read by the live app for display + config changes.
CREATE TABLE IF NOT EXISTS simulator_config (
    id                SERIAL PRIMARY KEY,
    user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy          TEXT NOT NULL CHECK (strategy IN ('v20', 'turtle')),
    starting_balance  NUMERIC NOT NULL DEFAULT 100000,
    max_position_pct  REAL NOT NULL DEFAULT 12.0,
    is_active         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reset_at          TIMESTAMPTZ,
    UNIQUE (user_id, strategy)
);

CREATE TABLE IF NOT EXISTS simulator_portfolio (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy      TEXT NOT NULL CHECK (strategy IN ('v20', 'turtle')),
    cash_balance  NUMERIC NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, strategy)
);

CREATE TABLE IF NOT EXISTS simulator_holdings (
    id               SERIAL PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy         TEXT NOT NULL CHECK (strategy IN ('v20', 'turtle')),
    symbol           TEXT NOT NULL,
    quantity         NUMERIC NOT NULL,
    entry_price      NUMERIC NOT NULL,
    entry_date       DATE NOT NULL,
    entry_rationale  TEXT,
    UNIQUE (user_id, strategy, symbol)
);

CREATE TABLE IF NOT EXISTS simulator_trades (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy      TEXT NOT NULL CHECK (strategy IN ('v20', 'turtle')),
    symbol        TEXT NOT NULL,
    action        TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    price         NUMERIC NOT NULL,
    quantity      NUMERIC NOT NULL,
    trade_date    DATE NOT NULL,
    realized_pnl  NUMERIC,  -- only set on SELL
    rationale     TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Records EVERY candidate reviewed, including ones the agent chose not to act on -- the
-- transparency/trust mechanism ("why didn't it buy X today") and the debugging tool when
-- something looks wrong.
CREATE TABLE IF NOT EXISTS simulator_decision_log (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    strategy    TEXT NOT NULL CHECK (strategy IN ('v20', 'turtle')),
    symbol      TEXT NOT NULL,
    decision    TEXT NOT NULL CHECK (decision IN ('BUY', 'SELL', 'HOLD', 'SKIP')),
    rationale   TEXT,
    run_date    DATE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Turtle Quant "Analyze" button: admin-triggered, per-stock LLM deep-research (Management
-- Quality / Business Quality / Price & Final Decision, via Perplexity Sonar Pro over OpenRouter
-- -- see modules/turtlequant/stock_analysis.py). NOT per-user -- a stock's research doesn't
-- depend on who asked, and it's a shared, admin-gated feature -- so this is a global cache
-- keyed by symbol, one row per symbol, overwritten on re-Analyze. Accessed via the same
-- SUPABASE_URL/SUPABASE_SERVICE_KEY REST path as every other table on this page, written
-- directly by the live app itself (a background thread spawned from a Dash callback, NOT a
-- GitHub Actions batch job -- this is single-stock, on-demand, admin-only work, a different
-- scale of problem from the whole-universe batch jobs elsewhere in this repo).
CREATE TABLE IF NOT EXISTS turtlequant_stock_analysis (
    symbol                TEXT PRIMARY KEY,
    company               TEXT,
    status                TEXT NOT NULL DEFAULT 'pending',  -- pending | running | done | error
    management_report     TEXT,
    management_citations  TEXT,   -- JSON-encoded list of source URLs
    business_report       TEXT,
    business_citations    TEXT,
    price_report          TEXT,
    price_citations       TEXT,
    requested_by          TEXT,   -- admin's email, audit trail
    -- Which STOCK_ANALYSIS_MODEL actually generated this row's reports -- recorded per-row
    -- (not just read from the current env var) so old reports keep an accurate record even
    -- after the model setting is later changed. Free-tier models (openrouter/free) have no
    -- real web search grounding and confirmed-live will fabricate plausible-sounding but
    -- entirely false company facts rather than saying "NOT FOUND" -- see modules/turtlequant/
    -- callbacks.py's _render_analysis_panel for the warning banner keyed off this field.
    model                 TEXT,
    requested_at          TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    error_message         TEXT,
    -- Doubles as a heartbeat: patched after EACH of the 3 stages completes (not just at the
    -- end), so a row stuck at status='running' with a stale updated_at (see
    -- analysis_store.is_stale) means the background thread died (e.g. Render recycled the
    -- process mid-run) rather than genuinely still working -- the UI treats that as failed and
    -- offers re-Analyze instead of polling forever.
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gtt_log (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER     NOT NULL REFERENCES users(id),
    run_date    DATE        NOT NULL,
    symbol      TEXT        NOT NULL,
    strategy    TEXT        NOT NULL,
    gtt_id      INTEGER,
    status      TEXT        NOT NULL,
    error_msg   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
