-- users/001_init.sql
-- Schema for users-db — stores personal data (PII) separately from billing-db.
-- CERBER CORE billing API does NOT connect to this database.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT        NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,   -- bcrypt
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- The SHA-256 of users.id is what CERBER CORE receives as user_hash.
-- Computing and transmitting it is the responsibility of the integrating service.
