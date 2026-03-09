-- Migration 002: Waypoint file storage
CREATE TABLE IF NOT EXISTS waypoint_files (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    is_public       BOOLEAN NOT NULL DEFAULT TRUE,
    waypoint_count  INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, name)
);

CREATE INDEX IF NOT EXISTS idx_waypoint_files_owner ON waypoint_files (owner_id);
CREATE INDEX IF NOT EXISTS idx_waypoint_files_public ON waypoint_files (is_public) WHERE is_public = TRUE;

CREATE TABLE IF NOT EXISTS waypoint_entries (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id          UUID NOT NULL REFERENCES waypoint_files(id) ON DELETE CASCADE,
    name             VARCHAR(255) NOT NULL,
    code             VARCHAR(50),
    country          VARCHAR(10),
    latitude         NUMERIC(10,7) NOT NULL,
    longitude        NUMERIC(10,7) NOT NULL,
    elevation        INTEGER,
    style            INTEGER NOT NULL DEFAULT 1,
    runway_direction INTEGER,
    runway_length    INTEGER,
    runway_width     INTEGER,
    frequency        VARCHAR(20),
    description      TEXT,
    sort_order       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_waypoint_entries_file ON waypoint_entries (file_id);
