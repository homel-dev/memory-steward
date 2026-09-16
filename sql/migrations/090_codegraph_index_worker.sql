-- CodeGraph index-worker state, persisted artifact metadata, and indexing telemetry.
-- The migration runner owns BEGIN/COMMIT.

ALTER TABLE codegraph_registry
  ADD COLUMN IF NOT EXISTS index_mode TEXT NULL
    CHECK (index_mode IS NULL OR index_mode IN ('full', 'incremental')),
  ADD COLUMN IF NOT EXISTS base_revision TEXT NULL,
  ADD COLUMN IF NOT EXISTS state_artifact_schema_version INTEGER NULL
    CHECK (state_artifact_schema_version IS NULL OR state_artifact_schema_version > 0);

CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE IF NOT EXISTS telemetry.codegraph_index (
  id BIGSERIAL PRIMARY KEY,
  registry_id UUID NOT NULL REFERENCES codegraph_registry(id) ON DELETE CASCADE,
  worker_generation BIGINT NOT NULL,
  project_id TEXT NULL,
  run_id TEXT NULL,
  repository TEXT NULL,
  revision TEXT NULL,
  base_revision TEXT NULL,
  index_mode TEXT NULL,
  codegraph_version TEXT NULL,
  index_profile TEXT NULL,
  duration_ms INTEGER NULL CHECK (duration_ms IS NULL OR duration_ms >= 0),
  ok BOOLEAN NOT NULL,
  error_detail TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS telemetry_codegraph_index_registry_idx
  ON telemetry.codegraph_index(registry_id, created_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_codegraph_index_repository_idx
  ON telemetry.codegraph_index(repository, created_at DESC)
  WHERE repository IS NOT NULL;
