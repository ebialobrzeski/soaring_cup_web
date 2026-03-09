-- Migration 011: Create weather_cache table for task planner grid caching.
-- Caches weather data per grid point with 2-hour TTL.
-- Used by the AI task planner to avoid redundant API calls for the same area.

CREATE TABLE IF NOT EXISTS weather_cache (
    lat             NUMERIC(7,4) NOT NULL,
    lon             NUMERIC(7,4) NOT NULL,
    forecast_date   DATE NOT NULL,
    model_run       VARCHAR(20) NOT NULL,
    source          VARCHAR(50) NOT NULL,
    data            JSONB NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (lat, lon, forecast_date, model_run, source)
);

CREATE INDEX IF NOT EXISTS weather_cache_lookup_idx
    ON weather_cache (lat, lon, forecast_date, expires_at);
