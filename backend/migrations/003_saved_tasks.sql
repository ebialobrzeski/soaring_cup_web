-- Migration 003: Saved tasks storage
CREATE TABLE IF NOT EXISTS saved_tasks (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name              VARCHAR(255) NOT NULL,
    description       TEXT,
    is_public         BOOLEAN NOT NULL DEFAULT TRUE,
    task_data         JSONB NOT NULL,
    waypoint_file_id  UUID REFERENCES waypoint_files(id) ON DELETE SET NULL,
    total_distance    NUMERIC(8,2),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_id, name)
);

CREATE INDEX IF NOT EXISTS idx_saved_tasks_owner ON saved_tasks (owner_id);
CREATE INDEX IF NOT EXISTS idx_saved_tasks_public ON saved_tasks (is_public) WHERE is_public = TRUE;
CREATE INDEX IF NOT EXISTS idx_saved_tasks_distance ON saved_tasks (total_distance);
