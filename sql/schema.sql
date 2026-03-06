CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
-- DROP SCHEMA telemetry CASCADE;
-- CREATE SCHEMA telemetry;


-- =========================
-- Layer 1: Static Memory
-- =========================
CREATE TABLE IF NOT EXISTS static_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content TEXT NOT NULL,
  mode TEXT NOT NULL DEFAULT 'global',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

--- CREATE INDEX IF NOT EXISTS static_memory_active_idx
---  ON static_memory(project_id, mode, is_active, priority DESC);

-- =========================
-- Layer 2: Dynamic Memory (append-only; no compaction in Part 1)
-- =========================
CREATE TABLE IF NOT EXISTS dynamic_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id TEXT NOT NULL,
  scope TEXT NULL,
  type TEXT NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  high_confidence BOOLEAN NOT NULL DEFAULT TRUE,
  evidence_type TEXT NULL,
  evidence_ref TEXT NULL,
  qdrant_point_id TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, content_hash)
);

CREATE INDEX IF NOT EXISTS dynamic_memory_project_idx
  ON dynamic_memory(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS dynamic_memory_confidence_idx
  ON dynamic_memory(project_id, high_confidence, created_at DESC);
