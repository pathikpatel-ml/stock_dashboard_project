-- ============================================================
-- Groww Integration Migration
-- Run this in your Supabase SQL editor BEFORE deploying.
-- All statements are idempotent (safe to re-run).
-- ============================================================

-- 1. Groww credentials and settings per user
CREATE TABLE IF NOT EXISTS groww_settings (
    user_id                 INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    app_id_enc              TEXT,               -- Groww App ID (API Key), AES-256 encrypted
    app_secret_enc          TEXT,               -- Groww App Secret, encrypted
    totp_secret_enc         TEXT,               -- TOTP secret for auto-refresh, encrypted (optional)
    access_token_enc        TEXT,               -- Current access token, encrypted
    access_token_set_at     TIMESTAMPTZ,        -- When token was last set
    totp_auto_refresh       BOOLEAN NOT NULL DEFAULT FALSE,
    proximity_threshold_pct FLOAT   NOT NULL DEFAULT 2.0,
    max_allocation_pct      FLOAT   NOT NULL DEFAULT 3.0,
    gtt_enabled             BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at              TIMESTAMPTZ
);

-- 2. Groww stock exclusions (same pattern as kite_exclusions)
CREATE TABLE IF NOT EXISTS groww_exclusions (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol  TEXT    NOT NULL,
    UNIQUE(user_id, symbol)
);

-- 3. Add broker_choice to kite_settings
--    NULL / 'zerodha' = Zerodha (backward compatible)
--    'groww'          = Groww
ALTER TABLE kite_settings
    ADD COLUMN IF NOT EXISTS broker_choice TEXT DEFAULT 'zerodha';

-- 4. Add broker column to gtt_log so logs show which platform placed the order
ALTER TABLE gtt_log
    ADD COLUMN IF NOT EXISTS broker TEXT DEFAULT 'zerodha';

-- 5. Indexes for performance
CREATE INDEX IF NOT EXISTS idx_groww_settings_gtt_enabled
    ON groww_settings(gtt_enabled) WHERE gtt_enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_groww_exclusions_user
    ON groww_exclusions(user_id);
