-- Migration 008: AI Planner usage tracking
-- Tracks every API call made by the AI planner system for monitoring and analytics

CREATE TABLE IF NOT EXISTS ai_planner_usage (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES users(id),
  endpoint        VARCHAR(100) NOT NULL,            -- e.g. '/api/planner/generate', '/api/airspace/openaip'
  method          VARCHAR(10) NOT NULL DEFAULT 'GET',
  request_params  JSONB,                            -- sanitized request parameters
  response_status INTEGER NOT NULL,                 -- HTTP status code
  response_time_ms INTEGER,                         -- response time in milliseconds
  external_calls  JSONB,                            -- list of external API calls made {service, endpoint, status, time_ms}
  error_message   TEXT,                             -- error message if failed
  ip_address      VARCHAR(45),                      -- IPv4 or IPv6
  user_agent      VARCHAR(500),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ON ai_planner_usage (created_at DESC);
CREATE INDEX ON ai_planner_usage (user_id, created_at DESC);
CREATE INDEX ON ai_planner_usage (endpoint, created_at DESC);
