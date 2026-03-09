-- Migration 012: Custom user gliders + waypoint/task metadata for previews

-- Allow users to have their own custom gliders
ALTER TABLE glider_polars
    ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- NULL user_id = global (imported from XCSoar), non-NULL = user's private glider
CREATE INDEX IF NOT EXISTS idx_glider_polars_user ON glider_polars (user_id) WHERE user_id IS NOT NULL;

-- Allow duplicate names per user (only global names must be unique)
ALTER TABLE glider_polars DROP CONSTRAINT IF EXISTS glider_polars_name_key;
CREATE UNIQUE INDEX IF NOT EXISTS glider_polars_global_name_unique
    ON glider_polars (name) WHERE user_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS glider_polars_user_name_unique
    ON glider_polars (user_id, name) WHERE user_id IS NOT NULL;

-- Waypoint file bounding box and country codes for minimap preview in browse
ALTER TABLE waypoint_files
    ADD COLUMN IF NOT EXISTS country_codes TEXT,
    ADD COLUMN IF NOT EXISTS bbox JSONB;

-- Saved task bounding box for minimap preview in browse
ALTER TABLE saved_tasks
    ADD COLUMN IF NOT EXISTS bbox JSONB;
