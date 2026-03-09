-- Migration 001: Core schema — users table and migration tracking
-- Note: gen_random_uuid() is built into PostgreSQL 13+. If using PG 12 or older,
-- a superuser must run: CREATE EXTENSION IF NOT EXISTS "pgcrypto"; beforehand.

-- Schema migration tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          SERIAL PRIMARY KEY,
    filename    VARCHAR(255) UNIQUE NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    display_name    VARCHAR(100) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    tier            VARCHAR(20) NOT NULL DEFAULT 'free'
                    CHECK (tier IN ('free', 'premium', 'admin')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_tier ON users (tier);
