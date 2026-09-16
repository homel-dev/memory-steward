-- Durable capability sessions for revision-bound agent CodeGraph access.
-- The migration runner owns BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS capability_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  token_digest TEXT NOT NULL UNIQUE CHECK (length(token_digest) = 64),
  project_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  realm TEXT NOT NULL CHECK (realm IN ('workspace', 'oracle', 'candidate')),
  repository TEXT NULL,
  revision TEXT NOT NULL CHECK (revision ~ '^[0-9a-f]{40}$'),
  role TEXT NOT NULL,
  stage TEXT NULL,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'releasing', 'released', 'expired', 'revoked')),
  authorized_tools TEXT[] NOT NULL CHECK (cardinality(authorized_tools) > 0),
  codegraph_registry_id UUID NOT NULL REFERENCES codegraph_registry(id) ON DELETE RESTRICT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  released_at TIMESTAMPTZ NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS capability_sessions_active_idx
  ON capability_sessions(status, expires_at);

CREATE INDEX IF NOT EXISTS capability_sessions_binding_idx
  ON capability_sessions(project_id, run_id, realm, revision)
  WHERE status = 'active';

CREATE SCHEMA IF NOT EXISTS telemetry;

CREATE TABLE IF NOT EXISTS telemetry.codegraph_query (
  id BIGSERIAL PRIMARY KEY,
  capability_session_id UUID NOT NULL REFERENCES capability_sessions(id) ON DELETE CASCADE,
  registry_id UUID NOT NULL REFERENCES codegraph_registry(id) ON DELETE CASCADE,
  worker_generation BIGINT NOT NULL,
  tool_name TEXT NOT NULL,
  ok BOOLEAN NOT NULL,
  duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
  error_detail TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS codegraph_query_session_time_idx
  ON telemetry.codegraph_query(capability_session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS codegraph_query_registry_time_idx
  ON telemetry.codegraph_query(registry_id, created_at DESC);
