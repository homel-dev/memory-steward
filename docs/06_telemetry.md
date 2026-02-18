
# TELEMETRY & OBSERVABILITY
## The Diagnostics Plane: Metrics, Accounting, and Introspection
### Foundational Engineering Specification (Document 06 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 05 (Stability)](05_stability.md) | [Next: Document 07 (Management)](07_glass_pane.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [0.1 Change Set Since Prior Draft](#01-change-set-since-prior-draft)
- [1. Purpose](#1-purpose)
- [2. Architectural Concept: The Diagnostics Plane](#2-architectural-concept-the-diagnostics-plane)
- [3. Telemetry Storage Contract](#3-telemetry-storage-contract)
- [4. Metric Taxonomy](#4-metric-taxonomy)
- [5. Drop Reasons and “Explain Rejection”](#5-drop-reasons-and-explain-rejection)
- [6. Deterministic System Suggestions](#6-deterministic-system-suggestions)
- [7. Agent Skill Exposure (Pull Model)](#7-agent-skill-exposure-pull-model)
- [8. Implementation Wiring](#8-implementation-wiring)
- [9. Relationship to Other Documents](#9-relationship-to-other-documents)
- [10. Summary](#10-summary)
- [11. Log Aggregation & Retention (Diagnostics Plane)](#11-log-aggregation--retention-diagnostics-plane)
- [12. SQL Reference (Agent Logs)](#12-sql-reference-agent-logs)
- [13. Closing Statement](#13-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** Core maintainers, operators
**Change policy:**
- Append-only
- No silent edits

[Back to top](#navigation)

---

## 0.1 Change Set Since Prior Draft

This revision makes the previous draft **implementation-grade** by aligning with the **current** Postgres schema (`010_telemetry_schema.sql`) and the current writer (`telemetry.py`).

### Changes applied
1. **Naming fix:** removed “Homel.dev” branding from the document header. System is **Memory Steward**.
2. **Storage contract aligned:** schema, keys, indexes, retention, cardinality, and compatibility rules match `010_telemetry_schema.sql`.
3. **Mode lineage clarified:** the Router **records** `decided_mode` if provided by upstream policy/decision logic; it is not the “mode authority” by default.
4. **Explainability made real:** deterministic drop counters exist in `telemetry.retrieval` (`dropped_budget`, `dropped_no_content`, `dropped_other`) enabling `telemetry.explain_rejection(request_id)`.
5. **Agent Skill made concrete:** defined deterministic read operations and exact SQL queries (bounded, safe) updated to the new column names.

[Back to top](#navigation)

---

## 1. Purpose

This document defines the Telemetry Subsystem as a formal **Diagnostics Plane** alongside the **Content Plane**.
It specifies:
- What telemetry must be captured (high-signal, low-ambiguity)
- How telemetry is stored (tables, keys, indexes, retention)
- How telemetry is exposed to operators (pull-only Agent Skill)
- How telemetry drives deterministic system suggestions and debugging

This turns telemetry from “logs” into **measurable, regressible, and actionable signals**.

[Back to top](#navigation)

---

## 2. Architectural Concept: The Diagnostics Plane

### 2.1 Separation of Planes

The system operates on two distinct planes:

1. **Content Plane:** `static_memory`, `dynamic_memory`, `reference_memory`
   Used to shape generation (prompt injection and retrieval).
2. **Diagnostics Plane:** telemetry tables (time series, step traces, error digests, accounting)
   Used for introspection, debugging, and regression detection.

> **Hard Invariant:** Telemetry from the Diagnostics Plane is **never injected** into chat context automatically. Telemetry is **pull-only** (operator/tool initiated) to prevent context pollution.

### 2.2 The “Observability Memory” Concept

Telemetry is treated as “Observability Memory”: a durable record of **how** the system behaved, not **what** it discussed.
Telemetry must answer engineering questions deterministically:
- “What got slower?”
- “Which dependency failed?”
- “Why didn’t retrieval return anything?”
- “Why was memory dropped / gated?”
- “Did we respect budgets?”

[Back to top](#navigation)

---

## 3. Telemetry Storage Contract

### 3.1 Canonical Postgres Schema (Current)

The canonical schema is currently defined by `010_telemetry_schema.sql` and implemented by `telemetry.py`.

#### Current DDL (canonical)
~~~sql
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
~~~

### 3.2 Keys, Indexes, and Query Shape

#### Primary identities
- `request_id` is the join key across:
  - `telemetry.request` (one row per request)
  - `telemetry.step` (N rows per request)
  - `telemetry.retrieval` (optional one row per request)
  - `telemetry.admission` (optional one row per request)
- `project_id` is present on all tables to support project-scoped time-window queries.

#### Foreign key (ordering) invariant
Because `telemetry.step`, `telemetry.retrieval`, and `telemetry.admission` reference `telemetry.request(request_id)` with `ON DELETE CASCADE`:
- The writer MUST create the `telemetry.request` row first for a `request_id`.
- Only then may it insert step/retrieval/admission rows referencing the same `request_id`.
- Deleting a `telemetry.request` row will cascade-delete step/retrieval/admission rows.

#### Index intent (current)
- `request_project_id_t_begin_idx`: project-level time window queries (dashboards and summaries)
- `request_error_kind_t_begin_idx`: triage and error rates over time
- `request_origin_hash_t_begin_idx`: bounded correlation by origin (hashed)
- `step_request_id_idx`: point lookup of steps for a request (blame ops)
- `step_project_name_t_begin_idx`: per-project step latencies and p95 aggregation
- `step_name_t_begin_idx`: global step latency trends (optional)
- `retrieval_project_id_idx`: per-project retrieval health

#### Query shape constraints
All operator queries MUST be bounded by at least one of:
- Time window (e.g. last 15m / 1h / 24h)
- `project_id`
- Specific `request_id`

Unbounded full-table scans are non-compliant.

### 3.3 Retention and Truncation Policy

Telemetry is explicitly **bounded** and must not grow without limit.

#### Required policy (MVP)
- Retain raw telemetry for a fixed window (example defaults; make these config-driven):
  - `telemetry.step`: 7 days
  - `telemetry.request`: 7 days
  - `telemetry.retrieval`: 7 days
  - `telemetry.admission`: 30 days (useful for “admission health”)

#### Enforcement mechanism (MVP)
One of:
- A Kubernetes CronJob that runs bounded `DELETE` statements
- A Postgres-native scheduled job if available in your environment (deployment-specific)

> **Hard Invariant:** Retention must be enforced by automation, not “manual cleanup.”

#### Example retention deletes (canonical column names)
~~~sql
-- NOTE: deleting from telemetry.request cascades to step/retrieval/admission
-- due to ON DELETE CASCADE foreign keys.

-- requests (and cascaded children) older than 7 days
DELETE FROM telemetry.request
WHERE t_begin < now() - interval '7 days';

-- optional: keep admissions longer than requests (only if you do NOT rely on cascades)
-- If you want admission retention independently, do NOT FK admission->request or do not delete requests earlier.
DELETE FROM telemetry.admission
WHERE t_begin < now() - interval '30 days';
~~~

### 3.4 Cardinality Rules

To keep telemetry usable and cheap:

Allowed high-cardinality identifiers:
- `request_id` (only for point lookups)
- `step.id` (internal)

Allowed bounded labels:
- `project_id` (bounded by operator usage; must not contain raw user text)
- `step.name` (bounded to a small canonical set)
- `error_kind` (bounded enum-like set)
- `decided_mode` (bounded enum-like set)

Potentially dangerous labels (must be bounded or hashed):
- `origin`: may be stored, but must be bounded and must not contain sensitive content
- `origin_hash`: preferred for correlation; must be stable and non-reversible (e.g. SHA-256 of origin + salt)
- `error_detail`: MUST be truncated and must not include sensitive content
- `extra_json`: MUST be bounded, structured, and non-sensitive

**Never store**:
- Raw chat text
- Raw retrieved memory content
- Secrets (API keys, passwords)
- Full upstream request/response bodies (unless truncated and scrubbed)

### 3.5 Compatibility Guarantees

The writer contract requires:
- Exactly one `telemetry.request` row per `request_id`
- `request_end()` must execute in a `finally:` path (best-effort)
- Steps must be recorded even if they fail, with `ok=false` and truncated `error_detail`
- Writes must never block the request path beyond reasonable DB timeouts (best-effort semantics)
- Retrieval/admission rows are optional, but when written:
  - must reference an existing `telemetry.request` row (FK ordering invariant)

[Back to top](#navigation)

---

## 4. Metric Taxonomy

This section defines which metrics must exist **now** (aligned with the current schema).

### 4.1 Router Metrics (Per Request)

**Required (`telemetry.request`)**
- Identity:
  - `request_id`
  - `project_id`
- Timing:
  - `t_begin`, `t_end` (request latency derived from delta)
- Lineage:
  - `origin`, `origin_hash`
  - `model_requested`
  - `model_sent_to_builder`
  - `decided_mode` (recorded metadata; not authoritative by default)
- Outcome:
  - `http_status`
  - `error_kind`
  - `error_detail` (truncated)
- Token accounting / budgeting:
  - `prompt_tokens`, `completion_tokens`, `total_tokens`
  - `context_budget_max`
  - `static_tokens_est`, `dynamic_tokens_est`

### 4.2 Router Step Metrics (Per Step)

**Required (`telemetry.step`)**
- `name` (canonical step name)
- `t_begin`, `t_end`
- `duration_ms` (preferred; must be filled by writer, or derived at query time if absent)
- `ok`
- `http_status` (if the step is HTTP)
- `error_detail` (truncated)
- `extra_json` (bounded, structured, non-sensitive)

**Canonical step set (writer must use these names)**
- `embed`
- `qdrant_search`
- `pg_static`
- `builder_chat`
- `steward_async_call` *(or the exact async step name used in your router/steward wiring)*

### 4.3 Steward Metrics (Per Admission)

**Required (`telemetry.admission`)**
- Identity:
  - `request_id`, `project_id`
- Timing:
  - `t_begin`, `t_end`
  - `admission_lag_ms` (optional in writer logic, column exists)
- Extraction outcomes:
  - `fragments_extracted`
  - `fragments_inserted`
  - `qdrant_upserts`
- Outcome:
  - `ok`
  - `error_detail` (truncated)

[Back to top](#navigation)

---

## 5. Drop Reasons and “Explain Rejection”

The goal is deterministic, debuggable answers to:
- “Why was nothing injected?”
- “Why were candidates dropped?”

### 5.1 Drop Reason Enum

This enum is a Diagnostics Plane concept used to ensure deterministic accounting. It is not “prompt memory”.

**DropReason (bounded set, mapped onto counters)**
- `budget_exceeded` → `telemetry.retrieval.dropped_budget`
- `no_content`      → `telemetry.retrieval.dropped_no_content`
- `other`           → `telemetry.retrieval.dropped_other` *(writer must include details in `telemetry.step.extra_json` when `other` is incremented)*

### 5.2 Required Counters

Drop accounting MUST be recorded in `telemetry.retrieval` for each request that performs retrieval.

**Required counters (`telemetry.retrieval`)**
- `dense_candidates`
- `selected_topk`
- `context_tokens_est`
- `dropped_budget`
- `dropped_no_content`
- `dropped_other`

These counters are deterministic, cheap, and query-safe (no JSON extraction required).

### 5.3 Request-Level Blame Output

`telemetry.explain_rejection(request_id)` MUST be derivable from stored data.

#### Output format (canonical)
~~~text
Request: <request_id>
Project: <project_id>
Mode: <decided_mode>
Model: requested=<model_requested> sent=<model_sent_to_builder>
HTTP: <http_status> error_kind=<error_kind>

Token accounting:
  - prompt=<prompt_tokens> completion=<completion_tokens> total=<total_tokens>
  - budget_max=<context_budget_max> static_est=<static_tokens_est> dynamic_est=<dynamic_tokens_est>

Retrieval:
  - Dense Candidates: <dense_candidates>
  - Selected: <selected_topk>
  - Dropped (Budget): <dropped_budget>
  - Dropped (No Content): <dropped_no_content>
  - Dropped (Other): <dropped_other>

Steps:
  - embed: <ms> ok=<...>
  - qdrant_search: <ms> ok=<...>
  - pg_static: <ms> ok=<...>
  - builder_chat: <ms> ok=<...>

Admission:
  - ok=<...> extracted=<...> inserted=<...> qdrant_upserts=<...>
  - admission_lag_ms=<...>
~~~

If a retrieval or admission row does not exist for the request, the blame output MUST explicitly say:
- “Retrieval telemetry missing (not executed or not recorded).”
- “Admission telemetry missing (not executed or not recorded).”

[Back to top](#navigation)

---

## 6. Deterministic System Suggestions

Suggestions must be threshold-driven and objective. No subjective coaching.

### 6.1 Budget Pressure

**Trigger (supported by current schema)**
- `telemetry.retrieval.dropped_budget > 0` over a window, OR
- `static_tokens_est` repeatedly exceeds a configured fraction of `context_budget_max` (example 0.5)

**Signal**
- “Budget pressure: candidates dropped due to budget.”

**Actionable**
- Reduce `TOP_K` or per-item max token cap
- Increase context window (if available)
- Refactor static memory to reduce its token share (if static injection exists)

### 6.2 Retrieval Health

**Trigger (supported by current schema)**
- `dense_candidates = 0 AND selected_topk = 0` over a window

**Signal**
- “Retrieval blind spot: no candidates returned.”

**Actionable**
- Verify `project_id` filtering
- Verify embeddings service health
- Verify Qdrant collection exists and is populated
- Verify Qdrant reachable and search endpoint ok

### 6.3 Latency Hotspots

**Trigger (supported by current schema)**
- Step p95 by `telemetry.step.name` exceeds a configured threshold over a window
  Example: `builder_chat` p95 > 2000ms over last 1h

**Signal**
- “Latency hotspot detected in step: builder_chat”

**Actionable**
- Switch model backend
- Reduce request size / max generation
- Investigate upstream saturation

[Back to top](#navigation)

---

## 7. Agent Skill Exposure (Pull Model)

Telemetry is exposed on-demand via a read-only Agent Skill.

### 7.1 Interface Contract

The telemetry skill MUST be read-only and support bounded queries:

- `telemetry.summary(window_seconds, project_id)`
- `telemetry.slowest_steps(window_seconds, project_id)`
- `telemetry.errors(window_seconds, top_n, project_id_optional)`
- `telemetry.budget_health(window_seconds, project_id)`
- `telemetry.explain_rejection(request_id)`

### 7.2 Concrete Query Definitions

The following SQL is canonical for the skill (MVP). All queries MUST be bounded.

#### telemetry.summary(window_seconds, project_id)
~~~sql
SELECT
  count(*) AS requests,
  count(*) FILTER (WHERE http_status >= 500 OR error_kind IS NOT NULL) AS errors,
  percentile_cont(0.95) WITHIN GROUP (
    ORDER BY EXTRACT(EPOCH FROM (t_end - t_begin)) * 1000
  ) AS p95_ms
FROM telemetry.request
WHERE project_id = %s
  AND t_begin >= now() - (%s::int || ' seconds')::interval
  AND t_end IS NOT NULL;
~~~

#### telemetry.slowest_steps(window_seconds, project_id)
~~~sql
SELECT
  s.name AS step_name,
  count(*) AS n,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY s.duration_ms) AS p95_ms
FROM telemetry.step s
WHERE s.project_id = %s
  AND s.t_begin >= now() - (%s::int || ' seconds')::interval
  AND s.duration_ms IS NOT NULL
GROUP BY s.name
ORDER BY p95_ms DESC
LIMIT 20;
~~~

#### telemetry.errors(window_seconds, top_n, project_id_optional)
~~~sql
SELECT
  coalesce(error_kind, 'unknown') AS kind,
  count(*) AS n,
  max(t_begin) AS last_seen
FROM telemetry.request
WHERE t_begin >= now() - (%s::int || ' seconds')::interval
  AND ( %s::text IS NULL OR project_id = %s::text )
  AND (http_status >= 400 OR error_kind IS NOT NULL)
GROUP BY 1
ORDER BY n DESC
LIMIT %s;
~~~

#### telemetry.budget_health(window_seconds, project_id)
~~~sql
SELECT
  count(*) AS requests,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY total_tokens) AS p95_total_tokens,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY static_tokens_est) AS p95_static_tokens_est,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY dynamic_tokens_est) AS p95_dynamic_tokens_est,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY context_budget_max) AS p95_budget_max,
  avg(
    CASE
      WHEN context_budget_max IS NULL OR context_budget_max = 0 THEN NULL
      ELSE (total_tokens::numeric / context_budget_max::numeric)
    END
  ) AS avg_budget_fraction
FROM telemetry.request
WHERE project_id = %s
  AND t_begin >= now() - (%s::int || ' seconds')::interval;
~~~

#### telemetry.explain_rejection(request_id)
~~~sql
-- request
SELECT * FROM telemetry.request WHERE request_id = %s;

-- retrieval (if present)
SELECT * FROM telemetry.retrieval WHERE request_id = %s;

-- steps
SELECT
  name, t_begin, t_end, duration_ms, ok, http_status, error_detail, extra_json
FROM telemetry.step
WHERE request_id = %s
ORDER BY t_begin ASC;

-- admission (if present)
SELECT * FROM telemetry.admission WHERE request_id = %s;
~~~

### 7.3 Safety Rules

- No write operations.
- Enforce max window (example: max 7 days).
- Enforce max rows returned (example: 2,000).
- Truncate `error_detail` in output.
- Never return raw secrets or content plane data.

[Back to top](#navigation)

---

## 8. Implementation Wiring

### 8.1 Writer Contract (Router)

Router MUST call:
- `telemetry.request_begin(...)` at the start of handling `/v1/chat/completions`
- `telemetry.request_end(...)` in a `finally:` block
- `telemetry.step(...)` context manager for:
  - `embed`
  - `qdrant_search`
  - `pg_static`
  - `builder_chat`
- `telemetry.retrieval_write(...)` after selection is computed

**FK ordering invariant (mandatory)**
Because `telemetry.step` and `telemetry.retrieval` reference `telemetry.request` by `request_id`:
- The Router MUST insert `telemetry.request` first, before steps/retrieval rows.

### 8.2 Writer Contract (Steward)

Steward MUST write admission results once per `request_id`:
- `telemetry.admission_write(request_id, project_id, fragments_extracted, fragments_inserted, qdrant_upserts, admission_lag_ms, ok, error_detail)`

Admission telemetry MUST be written in a `finally:` path so it exists even on failure.

**FK ordering invariant (mandatory)**
Because `telemetry.admission` references `telemetry.request` by `request_id`:
- The originating `telemetry.request` row MUST exist before inserting admission telemetry.

### 8.3 Step Naming Canon

To keep dashboards stable, step names are a strict canon:
- `embed`
- `qdrant_search`
- `pg_static`
- `builder_chat`
- `steward_async_call`

Adding new step names is allowed only if they are:
- Bounded
- Documented here
- Adopted by dashboards explicitly

[Back to top](#navigation)

---

## 9. Relationship to Other Documents

- Aligns with the “write-only observability” requirement (Telemetry must not be injected into prompts).
- Validates routing and memory subsystems by providing deterministic introspection hooks.
- Provides the basis for operator dashboards (Grafana) and for tool-based debugging.

[Back to top](#navigation)

---

## 10. Summary

Telemetry in Memory Steward is a Diagnostics Plane subsystem with hard invariants:
- Write-only by default
- Pull-only exposure via Agent Skill
- Deterministic, bounded metrics and queries
- Enforced retention
- Concrete storage contract (tables, keys, indexes)

This makes the system debuggable, regressible, and operationally safe without polluting the Content Plane.

[Back to top](#navigation)

---

## 11. Log Aggregation & Retention (Diagnostics Plane)

The Diagnostics Plane includes a first-class log aggregation and retention layer to support incident response, explainability, and predictive diagnostics.
Logs are harvested from Kubernetes container streams and persisted locally with bounded growth and deterministic rotation.

### 11.1 Component Overview
- **Agent:** Vector (DaemonSet), harvesting `/var/log/containers/*.log` and container streams.
- **Sink:** Local file storage inside the cluster, persisted via PVC.
- **Format:** Line-oriented UTF-8 text (default) with optional JSON payloads preserved; timestamps normalized to RFC 3339.
- **Ownership:** Logs are an **operator-visible** diagnostic artifact; they do not participate in user content memory.

### 11.2 File Layout & Naming
All logs are written under a single root directory:
- Root: `/var/log/memory_steward_logs/`
- Per-service files (examples):
  - `memory-router.log`
  - `memory-steward.log`
  - `memory-steward-mcp.log`
  - `embeddings.log`
  - `qdrant.log`
  - `postgres.log`
  - `vllm-builder.log`
  - `vllm-steward.log`
  - `anythingllm.log`

**Stream tagging:** If stdout/stderr differentiation is needed, suffix with `.stdout.log` / `.stderr.log`.

### 11.3 Rotation & Retention Policy
- **Rotation trigger:** Max file size (`LOG_ROTATE_MAX_SIZE_MB`, default **10**).
- **History:** Max rotated files per log (`LOG_ROTATE_MAX_FILES`, default **10**).
- **Time cap:** Hard retention horizon (`LOG_RETENTION_DAYS`, default **14**); Vector purges files older than this horizon daily.
- **Global cap (optional):** Total directory cap (`LOG_TOTAL_CAP_MB`, default **5120**) enforced by LRU deletion of oldest rotated files.

Policies are **manifest-driven** and immutable at runtime (configured via ConfigMap).

### 11.4 Log Telemetry (Metrics)
The agent exports self-metrics into the Telemetry DB under `telemetry.agent_logs` with the following counters/gauges:

| Metric | Type | Labels | Description |
| :--- | :--- | :--- | :--- |
| `log_bytes_written_total` | counter | `service` | Cumulative bytes written per service file. |
| `log_rotations_total` | counter | `service` | Number of rotations performed. |
| `log_files_current` | gauge | `service` | Current number of files (active + rotated). |
| `log_retained_days` | gauge | – | Effective configured retention horizon. |
| `log_purge_events_total` | counter | `reason` | Purges due to `age`, `size`, or `global_cap`. |
| `log_write_errors_total` | counter | `service` | Failed writes or permission errors. |
| `agent_uptime_seconds` | gauge | – | Agent process uptime for health baselining. |

### 11.5 MCP Diagnostics Binding (Read-Only)
The Diagnostics Plane exposes **bounded** slices of logs to MCP:
- **Selectors:** `service`, `since` / `until`, `lines` (hard cap), optional `grep` (substring or RE2-style pattern).
- **Guards:** Responses are never unbounded; binary content is dropped; secrets redaction is allowed at the agent level.

### 11.6 Compliance & Tests
- No unbounded log growth under nominal throughput.
- Rotation occurs before exceeding `LOG_ROTATE_MAX_SIZE_MB`.
- Purge removes files older than `LOG_RETENTION_DAYS`.
- MCP log queries obey caps and return in ≤ 2 s for `lines ≤ 1000`.

[Back to top](#navigation)

---

## 12. SQL Reference (Agent Logs)

### Agent Logs Schema (Support for Section 11.4)
~~~sql
CREATE TABLE IF NOT EXISTS telemetry.agent_logs (
    id                  BIGSERIAL PRIMARY KEY,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT now(),
    service             TEXT NOT NULL,
    bytes_written       BIGINT DEFAULT 0,
    rotations           INT DEFAULT 0,
    write_errors        INT DEFAULT 0,
    files_current       INT DEFAULT 0,
    disk_usage_mb       NUMERIC(10, 2),
    node_name           TEXT,
    pod_name            TEXT
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_service_time
    ON telemetry.agent_logs (service, timestamp DESC);
~~~

[Back to top](#navigation)

---

## 13. Closing Statement
This document establishes the strict diagnostics, telemetry constraints, and operational standards required to maintain transparency and enforce system determinism within the Memory Steward architecture.

---

**END OF DOCUMENT 06**
