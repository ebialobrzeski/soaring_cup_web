-- Migration 010: AI Planner sessions — persists task generation requests, fetched data, and results

CREATE TABLE IF NOT EXISTS planner_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255),                    -- user-editable label, auto-generated if blank
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'generating', 'completed', 'error')),

    -- Form inputs (what the user requested)
    inputs          JSONB NOT NULL,                  -- full form snapshot: takeoff, dest, distance, date, glider, safety, constraints…

    -- Fetched external data cached with the session
    weather_data    JSONB,                           -- weather forecasts fetched for this request
    airspace_data   JSONB,                           -- airspace conflicts / zones for this request

    -- Generated result
    result          JSONB,                           -- full AI task proposal (legs, narrative, scores…)
    error_message   TEXT,                            -- error text if status='error'

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_planner_sessions_user
    ON planner_sessions (user_id, updated_at DESC);
