-- DEPRECATED manual bootstrap script.
-- Prefer: migrate -path migrations/billing -database "$BILLING_DATABASE_URL" up
-- Canonical source: migrations/billing/000001_init.up.sql

-- billing/000001_init.sql
-- Initial schema for billing-db used by CERBER CORE.
-- users-db stores PII separately; billing-db only keeps opaque user_hash values.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── API consumers ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS services (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT        NOT NULL,
    api_key_hash         TEXT        NOT NULL UNIQUE,
    secret_key_encrypted TEXT        NOT NULL,
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Billing user registry (no PII) ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_hash  TEXT        PRIMARY KEY,
    status     TEXT        NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Per-service balances in USDT ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS service_balances (
    id           UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id   UUID           NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    user_hash    TEXT           NOT NULL,
    balance_usdt NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (balance_usdt >= 0),
    updated_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    UNIQUE (service_id, user_hash)
);
CREATE INDEX IF NOT EXISTS idx_service_balances_service ON service_balances(service_id);
CREATE INDEX IF NOT EXISTS idx_service_balances_user_hash ON service_balances(user_hash);

-- ─── Exchange rates ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS exchange_rates (
    id         SERIAL         PRIMARY KEY,
    source     TEXT           NOT NULL,
    target     TEXT           NOT NULL,
    rate       NUMERIC(18, 8) NOT NULL CHECK (rate > 0),
    updated_at TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    UNIQUE (source, target)
);

-- ─── Immutable balance audit log ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
    id           UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id   UUID           NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    user_hash    TEXT           NOT NULL,
    operation_id TEXT,
    type         TEXT           NOT NULL CHECK (type IN ('topup', 'transfer', 'withdrawal')),
    amount_usdt  NUMERIC(18, 8) NOT NULL CHECK (amount_usdt >= 0),
    amount_rub   NUMERIC(18, 8) NOT NULL DEFAULT 0,
    rate         NUMERIC(18, 8) NOT NULL DEFAULT 0,
    description  TEXT           NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_transactions_service_user ON transactions(service_id, user_hash, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_service_operation_id
    ON transactions(service_id, operation_id)
    WHERE operation_id IS NOT NULL;

-- ─── Top-up providers and sessions ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS topup_methods (
    id          UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT           NOT NULL,
    code        TEXT           NOT NULL UNIQUE,
    fee_percent NUMERIC(8, 4)  NOT NULL DEFAULT 0,
    min_amount  NUMERIC(18, 8) NOT NULL DEFAULT 0,
    max_amount  NUMERIC(18, 8) NOT NULL DEFAULT 0,
    currency    TEXT           NOT NULL DEFAULT 'USDT',
    is_active   BOOLEAN        NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS topup_sessions (
    id          UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id  UUID           NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    user_hash   TEXT           NOT NULL,
    method_id   UUID           NOT NULL REFERENCES topup_methods(id),
    amount_usdt NUMERIC(18, 8) NOT NULL CHECK (amount_usdt > 0),
    amount_rub  NUMERIC(18, 8) NOT NULL DEFAULT 0,
    rate        NUMERIC(18, 8) NOT NULL DEFAULT 0,
    status      TEXT           NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'confirmed', 'failed', 'expired')),
    payment_url TEXT           NOT NULL DEFAULT '',
    requisites  TEXT           NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_topup_sessions_service_user ON topup_sessions(service_id, user_hash);
CREATE INDEX IF NOT EXISTS idx_topup_sessions_status ON topup_sessions(status);

-- ─── Seed data required for local/dev startup ────────────────────────────────
INSERT INTO exchange_rates (source, target, rate, updated_at)
VALUES ('USDT', 'RUB', 90.00, NOW())
ON CONFLICT (source, target) DO NOTHING;

INSERT INTO topup_methods (id, name, code, fee_percent, min_amount, max_amount, currency, is_active)
VALUES (
    '00000000-0000-4000-8000-000000000001',
    'Card RU',
    'card_ru',
    0,
    5.00,
    500.00,
    'USDT',
    TRUE
)
ON CONFLICT (code) DO NOTHING;
