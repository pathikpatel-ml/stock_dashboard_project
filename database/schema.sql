CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    is_active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

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
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
