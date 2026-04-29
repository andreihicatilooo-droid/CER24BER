-- 001_init.sql
-- Run once against the billing database.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Users ───────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Services (API consumers) ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS services (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    api_key    TEXT        NOT NULL UNIQUE,
    api_secret TEXT        NOT NULL,
    active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Providers (payment providers) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS providers (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    code       TEXT        NOT NULL UNIQUE,
    active     BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Accounts (balances) ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    id         UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID           NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT           NOT NULL,
    currency   CHAR(3)        NOT NULL,
    balance    NUMERIC(18, 8) NOT NULL DEFAULT 0 CHECK (balance >= 0),
    created_at TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id);

-- ─── Account <-> Provider link (acquiring accounts) ──────────────────────────
CREATE TABLE IF NOT EXISTS account_providers (
    account_id  UUID NOT NULL REFERENCES accounts(id)  ON DELETE CASCADE,
    provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    PRIMARY KEY (account_id, provider_id)
);

-- ─── Service <-> Account scope ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS service_accounts (
    service_id UUID NOT NULL REFERENCES services(id)  ON DELETE CASCADE,
    account_id UUID NOT NULL REFERENCES accounts(id)  ON DELETE CASCADE,
    PRIMARY KEY (service_id, account_id)
);

-- ─── Transactions ─────────────────────────────────────────────────────────────
CREATE TYPE tx_type AS ENUM ('deposit', 'withdrawal', 'transfer');

CREATE TABLE IF NOT EXISTS transactions (
    id              UUID           PRIMARY KEY DEFAULT gen_random_uuid(),
    from_account_id UUID           REFERENCES accounts(id),
    to_account_id   UUID           REFERENCES accounts(id),
    amount          NUMERIC(18, 8) NOT NULL CHECK (amount > 0),
    type            tx_type        NOT NULL,
    description     TEXT           NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tx_from ON transactions(from_account_id);
CREATE INDEX IF NOT EXISTS idx_tx_to   ON transactions(to_account_id);

-- ─── Payments (incoming / acquiring) ─────────────────────────────────────────
CREATE TYPE payment_status AS ENUM ('pending', 'confirmed', 'failed', 'canceled');

CREATE TABLE IF NOT EXISTS payments (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id  UUID            NOT NULL REFERENCES services(id),
    provider_id UUID            NOT NULL REFERENCES providers(id),
    account_id  UUID            NOT NULL REFERENCES accounts(id),
    external_id TEXT            NOT NULL UNIQUE,
    amount      NUMERIC(18, 8)  NOT NULL CHECK (amount > 0),
    currency    CHAR(3)         NOT NULL,
    status      payment_status  NOT NULL DEFAULT 'pending',
    requisites  JSONB           NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_payments_service ON payments(service_id);
CREATE INDEX IF NOT EXISTS idx_payments_status  ON payments(status);
