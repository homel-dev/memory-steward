-- 120_retrieval_observability.sql
-- Classify Router telemetry rows by operation so direct Reference Memory
-- queries are visible separately from context retrieval and chat requests.

BEGIN;

ALTER TABLE telemetry.request
  ADD COLUMN IF NOT EXISTS operation text NOT NULL DEFAULT 'chat';

CREATE INDEX IF NOT EXISTS request_operation_project_t_begin_idx
  ON telemetry.request (operation, project_id, t_begin DESC);

COMMIT;
