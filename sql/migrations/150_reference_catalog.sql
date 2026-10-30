-- 150_reference_catalog.sql
-- Canonical document-level Reference catalog.

BEGIN;

CREATE TABLE IF NOT EXISTS reference_documents (
    document_id    UUID PRIMARY KEY,
    source         TEXT NOT NULL,
    product        TEXT NOT NULL,
    version        TEXT NOT NULL,
    title          TEXT NOT NULL,
    content_hash   TEXT NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    metadata       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product, version, source)
);

CREATE INDEX IF NOT EXISTS reference_documents_product_version_idx
    ON reference_documents (product, version, title);

COMMENT ON TABLE reference_documents IS
    'Canonical document-level catalog for globally reusable Reference Memory.';

COMMIT;
