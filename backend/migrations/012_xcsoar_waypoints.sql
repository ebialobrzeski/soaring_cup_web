-- Migration 012: XCSoar global waypoints table for fast bbox queries.
-- Populated on-demand by the waypoint generation service when the user
-- first triggers a generation that requires aviation waypoints.

CREATE TABLE IF NOT EXISTS xcsoar_waypoints (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    code        TEXT    DEFAULT '',
    country     TEXT    DEFAULT '',
    lat         NUMERIC(9,6) NOT NULL,
    lon         NUMERIC(9,6) NOT NULL,
    elev        INTEGER DEFAULT 0,
    style       INTEGER DEFAULT 1,
    rwdir       INTEGER DEFAULT 0,
    rwlen       INTEGER DEFAULT 0,
    rwwidth     INTEGER DEFAULT 0,
    freq        TEXT    DEFAULT '',
    description TEXT    DEFAULT ''
);

-- Composite index for efficient bounding-box queries
CREATE INDEX IF NOT EXISTS idx_xcsoar_wp_bbox
    ON xcsoar_waypoints (lat, lon);

-- Track import status so the service knows whether data is populated
CREATE TABLE IF NOT EXISTS xcsoar_import_status (
    id           SERIAL PRIMARY KEY,
    source_url   TEXT    NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    imported_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
