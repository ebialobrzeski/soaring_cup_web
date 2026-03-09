-- Migration 005: Glider polars table
-- Stores glider polar data imported from XCSoar and LK8000 repositories

CREATE TABLE IF NOT EXISTS glider_polars (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            VARCHAR(200) NOT NULL UNIQUE,
  source          VARCHAR(20) NOT NULL,           -- 'xcsoar' | 'lk8000' | 'manual'
  max_gross_kg    INTEGER NOT NULL,
  max_ballast_l   INTEGER NOT NULL DEFAULT 0,
  v1_kmh          DOUBLE PRECISION NOT NULL,
  w1_ms           DOUBLE PRECISION NOT NULL,
  v2_kmh          DOUBLE PRECISION NOT NULL,
  w2_ms           DOUBLE PRECISION NOT NULL,
  v3_kmh          DOUBLE PRECISION NOT NULL,
  w3_ms           DOUBLE PRECISION NOT NULL,
  wing_area_m2    DOUBLE PRECISION,
  reference_mass_kg DOUBLE PRECISION,
  handicap        INTEGER,
  empty_mass_kg   INTEGER,
  polar_a         DOUBLE PRECISION,
  polar_b         DOUBLE PRECISION,
  polar_c         DOUBLE PRECISION,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
