-- Agent Memory Protocol (AMP): agent outcome idempotency, reusable structured
-- agent/analyzer reference artifacts, context feedback, and AMP telemetry.
-- The migration runner owns BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS agent_outcome_submission (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id TEXT NOT NULL,
  outcome_id TEXT NOT NULL,
  task_id TEXT NULL,
  session_id TEXT NULL,
  context_request_id TEXT NULL,
  objective TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  request_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_payload JSONB NULL,
  status TEXT NOT NULL DEFAULT 'processing'
    CHECK (status IN ('processing', 'complete', 'failed')),
  error_detail TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, outcome_id)
);

CREATE INDEX IF NOT EXISTS agent_outcome_submission_project_created_idx
  ON agent_outcome_submission(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_outcome_submission_context_idx
  ON agent_outcome_submission(context_request_id)
  WHERE context_request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS agent_reference (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id TEXT NOT NULL,
  artifact_key TEXT NOT NULL,
  repository TEXT NULL,
  revision TEXT NULL,
  artifact_type TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  producer_type TEXT NOT NULL
    CHECK (producer_type IN ('agent', 'analyzer', 'tool')),
  producer_name TEXT NULL,
  producer_version TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  payload JSONB NOT NULL,
  provenance JSONB NOT NULL DEFAULT '[]'::jsonb,
  source_outcome_id TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, artifact_key)
);

CREATE INDEX IF NOT EXISTS agent_reference_lookup_idx
  ON agent_reference(project_id, repository, revision, artifact_type, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_reference_source_outcome_idx
  ON agent_reference(project_id, source_outcome_id)
  WHERE source_outcome_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS context_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  feedback_id TEXT NOT NULL UNIQUE,
  context_request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  used_memory_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  irrelevant_memory_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  missing_context TEXT NULL,
  task_id TEXT NULL,
  session_id TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS context_feedback_context_idx
  ON context_feedback(context_request_id, created_at DESC);

CREATE INDEX IF NOT EXISTS context_feedback_project_idx
  ON context_feedback(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS telemetry.agent_outcome (
  id BIGSERIAL PRIMARY KEY,
  outcome_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  context_request_id TEXT NULL,
  fragments_extracted INTEGER NOT NULL DEFAULT 0,
  fragments_inserted INTEGER NOT NULL DEFAULT 0,
  artifacts_received INTEGER NOT NULL DEFAULT 0,
  artifacts_inserted INTEGER NOT NULL DEFAULT 0,
  qdrant_upserts INTEGER NOT NULL DEFAULT 0,
  idempotent_replay BOOLEAN NOT NULL DEFAULT false,
  ok BOOLEAN NOT NULL DEFAULT true,
  error_detail TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS telemetry_agent_outcome_identity_idx
  ON telemetry.agent_outcome(project_id, outcome_id, created_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_agent_outcome_project_created_idx
  ON telemetry.agent_outcome(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS telemetry.context_feedback (
  id BIGSERIAL PRIMARY KEY,
  feedback_id TEXT NOT NULL UNIQUE,
  context_request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  used_count INTEGER NOT NULL DEFAULT 0,
  irrelevant_count INTEGER NOT NULL DEFAULT 0,
  missing_context_reported BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS telemetry_context_feedback_project_created_idx
  ON telemetry.context_feedback(project_id, created_at DESC);
