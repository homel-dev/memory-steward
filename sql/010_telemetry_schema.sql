-- 010_telemetry_schema.sql
-- Memory Steward — Telemetry & Observability (Diagnostics Plane)
-- Canonical Postgres schema (single-file, self-contained).

BEGIN;

CREATE SCHEMA IF NOT EXISTS telemetry;

-- -------------------------------------------------------------------
-- telemetry.request
-- One row per /v1/chat/completions request_id
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry.request (
  request_id              text PRIMARY KEY,
  project_id              text NOT NULL,

  -- request timing
  t_begin                 timestamptz NOT NULL,
  t_end                   timestamptz,

  -- identity / lineage
  origin                  text,
  origin_hash             text,
  model_requested         text,
  model_sent_to_builder   text,
  decided_mode            text,

  -- outcome
  http_status             integer,
  error_kind              text,
  error_detail            text,

  -- token accounting / budgeting
  prompt_tokens           integer,
  completion_tokens       integer,
  total_tokens            integer,
  context_budget_max      integer,
  static_tokens_est       integer,
  dynamic_tokens_est      integer
);

CREATE INDEX IF NOT EXISTS request_project_id_t_begin_idx
  ON telemetry.request (project_id, t_begin DESC);

CREATE INDEX IF NOT EXISTS request_error_kind_t_begin_idx
  ON telemetry.request (error_kind, t_begin DESC);

CREATE INDEX IF NOT EXISTS request_origin_hash_t_begin_idx
  ON telemetry.request (origin_hash, t_begin DESC);

-- -------------------------------------------------------------------
-- telemetry.step
-- One row per measured step within a request_id (embed/qdrant_search/pg_static/builder_chat/...)
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry.step (
  id               bigserial PRIMARY KEY,

  request_id        text NOT NULL REFERENCES telemetry.request(request_id) ON DELETE CASCADE,
  project_id        text NOT NULL,

  name              text NOT NULL,

  t_begin           timestamptz NOT NULL,
  t_end             timestamptz,

  duration_ms       integer,

  ok                boolean,
  http_status       integer,
  error_detail      text,

  extra_json        jsonb
);

CREATE INDEX IF NOT EXISTS step_request_id_idx
  ON telemetry.step (request_id);

CREATE INDEX IF NOT EXISTS step_project_name_t_begin_idx
  ON telemetry.step (project_id, name, t_begin DESC);

CREATE INDEX IF NOT EXISTS step_name_t_begin_idx
  ON telemetry.step (name, t_begin DESC);

-- -------------------------------------------------------------------
-- telemetry.retrieval
-- One row per request_id (router retrieval outcomes)
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry.retrieval (
  request_id         text PRIMARY KEY REFERENCES telemetry.request(request_id) ON DELETE CASCADE,
  project_id         text NOT NULL,

  dense_candidates    integer NOT NULL DEFAULT 0,
  selected_topk       integer NOT NULL DEFAULT 0,
  context_tokens_est  integer NOT NULL DEFAULT 0,

  -- deterministic drop accounting (blame-able)
  dropped_budget      integer NOT NULL DEFAULT 0,
  dropped_no_content  integer NOT NULL DEFAULT 0,
  dropped_other       integer NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS retrieval_project_id_idx
  ON telemetry.retrieval (project_id);

-- -------------------------------------------------------------------
-- telemetry.admission
-- One row per request_id (steward admission outcomes)
-- -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telemetry.admission (
  request_id           text PRIMARY KEY REFERENCES telemetry.request(request_id) ON DELETE CASCADE,
  project_id           text NOT NULL,

  t_begin              timestamptz NOT NULL,
  t_end                timestamptz,

  fragments_extracted  integer NOT NULL DEFAULT 0,
  fragments_inserted   integer NOT NULL DEFAULT 0,
  qdrant_upserts        integer NOT NULL DEFAULT 0,

  admission_lag_ms     integer,

  ok                   boolean NOT NULL DEFAULT true,
  error_detail         text
);

CREATE INDEX IF NOT EXISTS admission_project_id_t_begin_idx
  ON telemetry.admission (project_id, t_begin DESC);

-- -------------------------------------------------------------------
-- Optional convenience views for dashboards (no retention/rollups here)
-- -------------------------------------------------------------------
CREATE OR REPLACE VIEW telemetry.v_step_latency_p95_15m AS
SELECT
  date_trunc('minute', t_begin) AS bucket_minute,
  project_id,
  name AS step_name,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
  count(*) AS n
FROM telemetry.step
WHERE duration_ms IS NOT NULL
  AND t_begin >= now() - interval '15 minutes'
GROUP BY 1, 2, 3;

CREATE OR REPLACE VIEW telemetry.v_request_tokens_15m AS
SELECT
  date_trunc('minute', t_begin) AS bucket_minute,
  project_id,
  count(*) AS requests,
  avg(total_tokens)::int AS avg_total_tokens,
  avg(prompt_tokens)::int AS avg_prompt_tokens,
  avg(completion_tokens)::int AS avg_completion_tokens,
  avg(static_tokens_est)::int AS avg_static_tokens_est,
  avg(dynamic_tokens_est)::int AS avg_dynamic_tokens_est
FROM telemetry.request
WHERE t_begin >= now() - interval '15 minutes'
GROUP BY 1, 2;

COMMIT;