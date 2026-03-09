-- Airspace cache table for the AI Task Planner.
-- Caches OpenAIP airspace polygons and ICAO NOTAMs per (bbox_hash, date) with 24h TTL.
CREATE TABLE IF NOT EXISTS airspace_cache (
    bbox_hash       VARCHAR(16) NOT NULL,
    flight_date     DATE NOT NULL,
    data            JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (bbox_hash, flight_date)
);
CREATE INDEX IF NOT EXISTS idx_airspace_cache_expires ON airspace_cache (expires_at);
