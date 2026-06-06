sql/migrations/060_admission_control.sql
-- sql/migrations/060_admission_control.sql
-- Admission Control: candidate, decision, failure, quarantine, and telemetry records.
-- The migration runner owns BEGIN/COMMIT.

CREATE TABLE IF NOT EXISTS admission_candidate (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  scope TEXT NULL,
  candidate_type TEXT NOT NULL,
  claim TEXT NOT NULL,
  normalized_claim TEXT NOT NULL,
  candidate_hash TEXT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  extractor_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  ttl TEXT NULL,
  supersedes JSONB NOT NULL DEFAULT '[]'::jsonb,
  raw_candidate JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, candidate_hash)
);

CREATE INDEX IF NOT EXISTS admission_candidate_project_created_idx
  ON admission_candidate(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS admission_candidate_request_idx
  ON admission_candidate(request_id);

CREATE TABLE IF NOT EXISTS admission_decision (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id UUID NULL REFERENCES admission_candidate(id) ON DELETE SET NULL,
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('admit', 'hold', 'reject', 'quarantine')),
  score INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
  reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
  auditor_verdict JSONB NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admission_decision_project_created_idx
  ON admission_decision(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS admission_decision_request_idx
  ON admission_decision(request_id);

CREATE TABLE IF NOT EXISTS failure_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id TEXT NOT NULL,
  attempted_hash TEXT NOT NULL,
  attempted_normalized TEXT NOT NULL,
  outcome TEXT NOT NULL,
  reason TEXT NOT NULL,
  scope TEXT NULL,
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, attempted_hash, outcome, reason)
);

CREATE INDEX IF NOT EXISTS failure_memory_project_recorded_idx
  ON failure_memory(project_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS failure_memory_project_hash_idx
  ON failure_memory(project_id, attempted_hash, recorded_at DESC);

CREATE TABLE IF NOT EXISTS quarantined_candidate (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  raw_payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS quarantined_candidate_project_created_idx
  ON quarantined_candidate(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS telemetry.admission_gate (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  candidate_hash TEXT NULL,
  gate TEXT NOT NULL,
  passed BOOLEAN NOT NULL,
  reason TEXT NULL,
  score_delta INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admission_gate_request_idx
  ON telemetry.admission_gate(request_id);

CREATE INDEX IF NOT EXISTS admission_gate_project_created_idx
  ON telemetry.admission_gate(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS telemetry.admission_audit (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  candidate_hash TEXT NOT NULL,
  auditor_model TEXT NOT NULL,
  verdict TEXT NULL,
  confidence DOUBLE PRECISION NULL,
  flags JSONB NOT NULL DEFAULT '[]'::jsonb,
  ok BOOLEAN NOT NULL DEFAULT true,
  error_detail TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admission_audit_request_idx
  ON telemetry.admission_audit(request_id);

CREATE INDEX IF NOT EXISTS admission_audit_project_created_idx
  ON telemetry.admission_audit(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS telemetry.context_diff (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  consumer_id TEXT NULL,
  previous_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  current_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  added_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  removed_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS context_diff_project_created_idx
  ON telemetry.context_diff(project_id, created_at DESC);
