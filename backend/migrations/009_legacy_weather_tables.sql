-- Migration 009: Create legacy weather/forecast tables if they don't exist.
-- These tables were originally created by a Node.js/Prisma backend.
-- This migration ensures they can be recreated from scratch on a fresh database.

-- ── Airports ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS airports (
    id                TEXT PRIMARY KEY,
    "icaoCode"        TEXT UNIQUE,
    name              TEXT NOT NULL,
    latitude          DOUBLE PRECISION NOT NULL,
    longitude         DOUBLE PRECISION NOT NULL,
    elevation         INTEGER,
    timezone          TEXT,
    country           TEXT,
    "isActive"        BOOLEAN NOT NULL DEFAULT TRUE,
    "createdAt"       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "updatedAt"       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "runwayDirection"  TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS "airports_icaoCode_key"
    ON airports ("icaoCode");


-- ── Forecast Models ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS forecast_models (
    id              TEXT PRIMARY KEY,
    name            TEXT UNIQUE NOT NULL,
    description     TEXT,
    "apiUrl"        TEXT,
    "isActive"      BOOLEAN NOT NULL DEFAULT TRUE,
    priority        INTEGER NOT NULL DEFAULT 0,
    weight          DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    "createdAt"     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "updatedAt"     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS "forecast_models_name_key"
    ON forecast_models (name);


-- ── Forecast Requests ───────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS forecast_requests (
    id              TEXT PRIMARY KEY,
    "airportId"     TEXT NOT NULL REFERENCES airports(id),
    "modelId"       TEXT NOT NULL REFERENCES forecast_models(id),
    "fetchedAt"     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "validUntil"    TIMESTAMPTZ,
    "dataSource"    TEXT
);

CREATE INDEX IF NOT EXISTS "forecast_requests_airportId_fetchedAt_idx"
    ON forecast_requests ("airportId", "fetchedAt");
CREATE INDEX IF NOT EXISTS "forecast_requests_validUntil_idx"
    ON forecast_requests ("validUntil");


-- ── Forecasts ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS forecasts (
    id                TEXT PRIMARY KEY,
    "requestId"       TEXT NOT NULL REFERENCES forecast_requests(id),
    "forecastTime"    TIMESTAMPTZ NOT NULL,
    "windSpeed"       DOUBLE PRECISION,
    "windDirection"   INTEGER,
    "windGusts"       DOUBLE PRECISION,
    "cloudBase"       INTEGER,
    "cloudCover"      INTEGER,
    "lapseRate"       DOUBLE PRECISION,
    "thermalIndex"    DOUBLE PRECISION,
    temperature       DOUBLE PRECISION,
    "dewPoint"        DOUBLE PRECISION,
    "solarRadiation"  DOUBLE PRECISION,
    pressure          DOUBLE PRECISION,
    humidity          INTEGER,
    visibility        INTEGER,
    precipitation     DOUBLE PRECISION,
    "rawData"         JSONB,
    UNIQUE ("requestId", "forecastTime")
);

CREATE INDEX IF NOT EXISTS "forecasts_requestId_idx"
    ON forecasts ("requestId");
CREATE INDEX IF NOT EXISTS "forecasts_forecastTime_idx"
    ON forecasts ("forecastTime");


-- ── Actual Weather (METAR / observations) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS actual_weather (
    id                TEXT PRIMARY KEY,
    "airportId"       TEXT NOT NULL REFERENCES airports(id),
    "observedAt"      TIMESTAMPTZ UNIQUE NOT NULL,
    "enteredAt"       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "enteredBy"       TEXT,
    "windSpeed"       DOUBLE PRECISION,
    "windDirection"   INTEGER,
    "windGusts"       DOUBLE PRECISION,
    "cloudBase"       INTEGER,
    temperature       DOUBLE PRECISION,
    "dewPoint"        DOUBLE PRECISION,
    visibility        INTEGER,
    notes             TEXT,
    "thermalQuality"  SMALLINT,
    "soarabilityNote" TEXT
);

CREATE INDEX IF NOT EXISTS "actual_weather_airportId_observedAt_idx"
    ON actual_weather ("airportId", "observedAt");


-- ── Accuracy Scores ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS accuracy_scores (
    id                    TEXT PRIMARY KEY,
    "modelId"             TEXT NOT NULL REFERENCES forecast_models(id),
    "actualWeatherId"     TEXT NOT NULL REFERENCES actual_weather(id),
    "calculatedAt"        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "windAccuracy"        DOUBLE PRECISION,
    "temperatureAccuracy" DOUBLE PRECISION,
    "cloudBaseAccuracy"   DOUBLE PRECISION,
    "overallAccuracy"     DOUBLE PRECISION,
    "windSpeedDiff"       DOUBLE PRECISION,
    "windDirectionDiff"   INTEGER,
    "temperatureDiff"     DOUBLE PRECISION,
    "cloudBaseDiff"       INTEGER
);

CREATE INDEX IF NOT EXISTS "accuracy_scores_modelId_calculatedAt_idx"
    ON accuracy_scores ("modelId", "calculatedAt");
CREATE INDEX IF NOT EXISTS "accuracy_scores_overallAccuracy_idx"
    ON accuracy_scores ("overallAccuracy");


-- ── AI Descriptions ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_descriptions (
    id                TEXT PRIMARY KEY,
    "airportId"       TEXT NOT NULL REFERENCES airports(id),
    "forecastDate"    TIMESTAMPTZ NOT NULL,
    language          TEXT NOT NULL DEFAULT 'en',
    "aiModel"         TEXT NOT NULL DEFAULT 'gpt-4',
    "aiScore"         SMALLINT,
    "aiExplanation"   TEXT,
    sources           TEXT[],
    "createdAt"       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    "updatedAt"       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE ("airportId", "forecastDate", language, "aiModel")
);

CREATE INDEX IF NOT EXISTS "ai_descriptions_airportId_idx"
    ON ai_descriptions ("airportId");
CREATE INDEX IF NOT EXISTS "ai_descriptions_forecastDate_idx"
    ON ai_descriptions ("forecastDate");
