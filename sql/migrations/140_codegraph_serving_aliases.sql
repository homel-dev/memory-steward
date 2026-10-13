-- Stable repository -> active READY CodeGraph generation.
-- The migration runner owns BEGIN/COMMIT.
CREATE TABLE IF NOT EXISTS codegraph_serving_aliases (
    repository TEXT PRIMARY KEY,
    build_id UUID NOT NULL REFERENCES codegraph_builds(id),
    worker_endpoint TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Read-only latest sessions follow the active repository alias.
ALTER TABLE capability_sessions DROP CONSTRAINT IF EXISTS capability_sessions_revision_check;
ALTER TABLE capability_sessions
    ADD CONSTRAINT capability_sessions_revision_check
    CHECK (revision = 'latest' OR revision ~ '^[0-9a-f]{40}$');

CREATE INDEX IF NOT EXISTS codegraph_serving_aliases_build_idx
    ON codegraph_serving_aliases(build_id);
