-- CodeGraph discovery/queue registry.
-- The migration runner owns BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS codegraph_registry (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_identity TEXT NOT NULL UNIQUE,
  source_bucket TEXT NOT NULL,
  source_object_key TEXT NOT NULL,
  source_version_id TEXT NULL,
  source_etag TEXT NULL,
  source_size_bytes BIGINT NULL CHECK (source_size_bytes IS NULL OR source_size_bytes >= 0),
  source_event_name TEXT NOT NULL,
  source_event_time TIMESTAMPTZ NULL,
  source_sequencer TEXT NULL,
  source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  source_event JSONB NOT NULL DEFAULT '{}'::jsonb,
  project_id TEXT NULL,
  run_id TEXT NULL,
  realm TEXT NULL,
  repository TEXT NULL,
  indexed_revision TEXT NULL,
  codegraph_version TEXT NULL,
  index_profile TEXT NULL,
  state_artifact_bucket TEXT NULL,
  state_artifact_key TEXT NULL,
  state_artifact_digest TEXT NULL,
  worker_id TEXT NULL,
  worker_generation BIGINT NOT NULL DEFAULT 0 CHECK (worker_generation >= 0),
  worker_endpoint TEXT NULL,
  ready BOOLEAN NOT NULL DEFAULT FALSE,
  state TEXT NOT NULL DEFAULT 'discovered'
    CHECK (state IN (
      'discovered',
      'queued',
      'indexing',
      'storing',
      'activating',
      'ready',
      'reindexing',
      'failed',
      'unindexable'
    )),
  error_detail TEXT NULL,
  discovered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  controller_claimed_at TIMESTAMPTZ NULL,
  indexing_started_at TIMESTAMPTZ NULL,
  indexing_finished_at TIMESTAMPTZ NULL,
  ready_at TIMESTAMPTZ NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK ((ready AND state = 'ready') OR (NOT ready AND state <> 'ready'))
);

CREATE INDEX IF NOT EXISTS codegraph_registry_work_idx
  ON codegraph_registry(ready, state, discovered_at);

CREATE INDEX IF NOT EXISTS codegraph_registry_run_revision_idx
  ON codegraph_registry(run_id, indexed_revision)
  WHERE run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS codegraph_registry_repository_revision_idx
  ON codegraph_registry(repository, indexed_revision)
  WHERE repository IS NOT NULL;
