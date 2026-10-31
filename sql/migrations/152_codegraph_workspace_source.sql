-- Track serving readiness for RR workspace CodeGraph generations.
-- Existing Flux rows keep NULL; the migration runner owns the transaction.
ALTER TABLE codegraph_builds ADD COLUMN worker_endpoint TEXT NULL;
