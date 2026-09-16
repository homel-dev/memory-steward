-- 100_reference_ingestion_jobs.sql
-- Durable queue for large reference URL ingestion.

BEGIN;

CREATE TABLE IF NOT EXISTS reference_ingestion_jobs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url               TEXT NOT NULL,
    product           TEXT NOT NULL,
    version           TEXT NOT NULL,
    scope             TEXT NOT NULL DEFAULT 'general',
    status            TEXT NOT NULL DEFAULT 'queued'
                      CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    worker_id         TEXT,
    cancel_requested  BOOLEAN NOT NULL DEFAULT FALSE,
    chunk_count       INTEGER NOT NULL DEFAULT 0,
    processed_chunks  INTEGER NOT NULL DEFAULT 0,
    upserted_count    INTEGER NOT NULL DEFAULT 0,
    error             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at        TIMESTAMPTZ,
    heartbeat_at      TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS reference_ingestion_jobs_status_created_idx
    ON reference_ingestion_jobs (status, created_at);

CREATE INDEX IF NOT EXISTS reference_ingestion_jobs_product_version_idx
    ON reference_ingestion_jobs (product, version, created_at DESC);

COMMENT ON TABLE reference_ingestion_jobs IS
    'Durable queue for bounded background ingestion of large reference URLs.';

COMMIT;
