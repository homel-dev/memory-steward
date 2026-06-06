-- sql/migrations/000_base.sql
-- Base schema: Layer 1 (static) + Layer 2 (dynamic, append-only) memory.
-- Non-destructive: no DROP SCHEMA. The migrate runner owns the transaction,
-- so this file intentionally has NO BEGIN/COMMIT.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

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

-- =========================
-- Layer 2: Dynamic Memory (append-only)
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
