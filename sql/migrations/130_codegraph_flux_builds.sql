-- Flux artifact -> CodeGraph build lifecycle.
-- The migration runner owns BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS codegraph_builds (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_api_version TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_namespace TEXT NOT NULL,
  source_name TEXT NOT NULL,
  source_uid TEXT NULL,
  artifact_revision TEXT NOT NULL,
  artifact_digest TEXT NOT NULL,
  artifact_url TEXT NULL,
  source_event JSONB NOT NULL DEFAULT '{}'::jsonb,
  state TEXT NOT NULL DEFAULT 'received'
    CHECK (state IN ('received', 'submitted', 'running', 'succeeded', 'failed', 'superseded')),
  workflow_namespace TEXT NULL,
  workflow_name TEXT NULL,
  workflow_uid TEXT NULL,
  generation_bucket TEXT NULL,
  generation_key TEXT NULL,
  generation_digest TEXT NULL,
  generation_schema_version INTEGER NULL
    CHECK (generation_schema_version IS NULL OR generation_schema_version > 0),
  result JSONB NULL,
  error_detail TEXT NULL,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  submitted_at TIMESTAMPTZ NULL,
  started_at TIMESTAMPTZ NULL,
  finished_at TIMESTAMPTZ NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source_namespace, source_kind, source_name, artifact_digest)
);

CREATE INDEX IF NOT EXISTS codegraph_builds_state_idx
  ON codegraph_builds(state, received_at, id);

CREATE INDEX IF NOT EXISTS codegraph_builds_source_idx
  ON codegraph_builds(source_namespace, source_kind, source_name, received_at DESC);
