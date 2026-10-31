-- Persist the Reference catalog descriptor embedding during ingestion.

BEGIN;

ALTER TABLE reference_documents
    ADD COLUMN descriptor_embedding DOUBLE PRECISION[];

COMMIT;
