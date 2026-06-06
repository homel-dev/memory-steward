-- 030_reference_ingestion.sql
-- Provenance table for reference memory ingestion events (Doc 03 §5).
-- Every ingest_reference_url / ingest_reference_text call writes one row.

BEGIN;

CREATE TABLE IF NOT EXISTS reference_ingestion (
    id              BIGSERIAL PRIMARY KEY,
    product         TEXT NOT NULL,
    version         TEXT NOT NULL,
    scope           TEXT NOT NULL DEFAULT 'general',
    source_url      TEXT NOT NULL,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    upserted_count  INTEGER NOT NULL DEFAULT 0,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ref_ingestion_product_version_idx
    ON reference_ingestion (product, version, ingested_at DESC);

COMMENT ON TABLE reference_ingestion IS
    'Audit log for all reference memory ingestion events. '
    'Written by Glass Pane MCP content plane. Never mutated after insert.';

COMMIT;
