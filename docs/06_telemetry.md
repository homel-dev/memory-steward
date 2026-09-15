# TELEMETRY AND OBSERVABILITY
## Current Postgres Writers, Request Accounting, and OCO Presentation
### Foundational Engineering Specification (Document 06 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 05 (Stability)](05_stability.md) | [Next: Document 07 (Management)](07_glass_pane.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Principle](#1-principle)
- [2. Router Telemetry](#2-router-telemetry)
- [3. Steward Telemetry](#3-steward-telemetry)
- [4. Provisioned Admission-Control Telemetry](#4-provisioned-admission-control-telemetry)
- [5. Content Restrictions](#5-content-restrictions)
- [6. Operator Surfaces](#6-operator-surfaces)
- [7. Verification](#7-verification)
- [8. Closing Statement](#8-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers, operators, observability engineers
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

[Back to top](#navigation)

---

## 1. Principle

Telemetry is diagnostics data. It is written by runtime components and exposed through diagnostics/OCO surfaces; it is not automatically injected into Builder context.

[Back to top](#navigation)

---

## 2. Router Telemetry

`memory_router.telemetry.TelemetryWriter` writes best-effort Postgres records for:

- request begin/end;
- measured steps;
- retrieval accounting.

The current tables include `telemetry.request`, `telemetry.step`, and `telemetry.retrieval`. Request identity is joined by `request_id`; `project_id` is carried for bounded project queries.

Telemetry failures are caught and logged so they do not intentionally fail the user request. Writes are synchronous DB calls with a short connect timeout; there is no async telemetry queue in the current Router.

[Back to top](#navigation)

---

## 3. Steward Telemetry

Memory Steward writes admission, agent-outcome, and context-feedback telemetry through its dedicated telemetry writer. Exact schema is defined by the SQL migrations in `sql/` and must remain aligned with writer queries.

[Back to top](#navigation)

---

## 4. Provisioned Admission-Control Telemetry

Migration `060_admission_control.sql` provisions `telemetry.admission_gate`, `telemetry.admission_audit`, and `telemetry.context_diff` in addition to public admission-control tables. Current Steward/Router request code does not implement writers for the complete gate/Auditor/context-diff pipeline described by those tables. Schema presence and dashboard queries MUST NOT be reported as proof that these signals are currently emitted.

[Back to top](#navigation)

---

## 5. Content Restrictions

Telemetry SHOULD store bounded operational metadata and error summaries, not raw chat bodies, secrets, or unbounded retrieved context.

[Back to top](#navigation)

---

## 6. Operator Surfaces

- MCP diagnostics tools provide bounded health/metrics/log/retrieval inspection.
- Memory Steward publishes Grafana datasource/dashboard ConfigMaps for OCO.
- OCO owns the shared Grafana presentation runtime; Memory Steward does not deploy its own Grafana workload.
- Vector collects cluster logs into the configured log sink.

[Back to top](#navigation)

---

## 7. Verification

Before merging a telemetry change:

1. verify the migration exists before writer use;
2. run component tests;
3. verify representative rows in Postgres;
4. verify OCO queries reference current columns/tables;
5. ensure telemetry failure is isolated from the main request path where intended.

[Back to top](#navigation)

---

## 8. Telemetry and Persistence Schema Inventory

| Schema | Table | Current purpose |
| --- | --- | --- |
| public | static_memory | Human/operator-authored static rules |
| public | dynamic_memory | Steward-admitted durable facts |
| public | runtime_config | Live key/value configuration |
| public | reference_ingestion | Reference ingestion audit/metadata |
| public | git_connections | Repository connection metadata |
| public | agent_outcome_submission | AMP idempotency and result state |
| public | agent_reference | Deterministic reusable agent artifacts |
| public | context_feedback | Context-usefulness feedback |
| public | admission_candidate | Provisioned candidate ledger; proposed admission-control runtime |
| public | admission_decision | Provisioned decisions; proposed runtime |
| public | failure_memory | Provisioned failure-memory store; proposed runtime |
| public | quarantined_candidate | Provisioned quarantine store; proposed runtime |
| telemetry | request | Router request lifecycle |
| telemetry | step | Step/timing telemetry |
| telemetry | retrieval | Retrieval accounting |
| telemetry | admission | Ordinary Steward admission accounting |
| telemetry | agent_outcome | AMP outcome accounting |
| telemetry | context_feedback | Feedback accounting |
| telemetry | admission_gate | Provisioned gate telemetry; proposed runtime |
| telemetry | admission_audit | Provisioned audit telemetry; proposed runtime |
| telemetry | context_diff | Provisioned context-diff telemetry; proposed runtime |

Rows under `telemetry.*` are operational evidence. Public-schema memory/config/artifact tables are not telemetry merely because diagnostics may query them.

## 9. Router Request Accounting

Router begins a telemetry request record before retrieval/Builder work and completes it with status/error information. Retrieval accounting records bounded operational facts such as:

- dense candidate count;
- final selected count;
- context token estimate;
- dropped-by-budget count;
- dropped-without-content count;
- estimated static and dynamic token contributions.

The request path also records requested/effective model context and mode input as available. These fields are diagnostics, not a decision authority.

## 10. Steward Admission Accounting

Ordinary `/admit` records:

- fragments extracted;
- fragments inserted;
- Qdrant upserts;
- success/failure;
- bounded error detail.

Structured agent outcomes additionally record artifact counts and idempotent replay state. Context feedback records used/irrelevant counts and whether missing context was reported.

## 11. Diagnostic Query Paths

| MCP tool | Primary diagnostic use |
| --- | --- |
| diag_health | Aggregate service health information |
| diag_explain | Inspect telemetry for a request |
| diag_explain_last | Inspect most recent request telemetry |
| diag_metrics | Summarize operational telemetry |
| diag_qdrant_stats | Inspect Qdrant collection statistics |
| dyn_inspect | Inspect dynamic-memory rows |
| dyn_simulate_retrieval | Simulate dynamic retrieval for troubleshooting |
| diag_logs | Read shared collected logs |

`diag_explain` and `diag_explain_last` are designed for request-level reasoning about what the system did. `dyn_simulate_retrieval` is a troubleshooting aid; it does not become the Router's production retrieval path.

## 12. Observability Presentation

Memory Steward ships OCO consumer resources for Grafana datasource/dashboard provisioning. The presentation plane is not canonical telemetry storage. Deleting or restarting a Grafana presentation component must not be treated as deleting the underlying Postgres/Qdrant state.

Vector is used for collected logs. The MCP diagnostics plane can read from the shared log volume where configured.

## 13. Data-Minimization Rules

Operational telemetry SHOULD prefer identifiers, counts, durations, statuses, hashes, and bounded error details over raw prompts or entire memory payloads. `DEBUG_PROMPTS` is an explicit exception for diagnosis and must remain disabled in normal deployment.

Steward extraction logging deserves the same scrutiny: logging extracted fragments may expose user memory. Operational deployments should evaluate log retention and access accordingly.

## 14. Provisioned Admission-Control Telemetry

Migration `060_admission_control.sql` creates `telemetry.admission_gate`, `telemetry.admission_audit`, and `telemetry.context_diff`. These tables are **provisioned for a proposed pipeline**. Their existence does not mean the current `/admit` route executes a deterministic gate -> auditor -> quarantine loop.

The documentation must keep this distinction explicit until runtime code and tests use those tables as part of an active state transition.

## 15. Request Investigation Procedure

A practical investigation is:

1. identify request/context/outcome ID;
2. use `diag_explain` or relevant Postgres telemetry query;
3. compare retrieval candidate and selected counts;
4. inspect token-budget drops;
5. inspect Router/Steward logs around the same ID;
6. inspect Qdrant only when semantic-store state is relevant;
7. inspect `agent_outcome_submission` for AMP idempotency/result state;
8. inspect `context_feedback` when an agent reported irrelevant or missing context;
9. avoid using telemetry as a replacement for canonical memory content inspection.

## 16. Verification Matrix

| Area | Verification |
| --- | --- |
| Router request lifecycle | Every completed/failed request closes its telemetry row |
| Retrieval accounting | Candidate/selected/drop counts match bounded retrieval behavior |
| Ordinary admission | Success/failure and insert/upsert counts are written |
| Agent outcome | Artifacts/fragments/replay values reflect response |
| Context feedback | Feedback IDs and counts are persisted |
| Error detail | Bounded and does not cause telemetry writer failure |
| Presentation | Dashboards can disappear without deleting canonical state |
| Proposal schema | No documentation claims gate/audit pipeline execution absent code |

---

## 8. Closing Statement

Telemetry is a diagnostics plane with bounded operational exposure. It MUST remain separate from durable learned memory and MUST NOT be injected automatically into Builder context.

[Back to top](#navigation)

---

**END OF DOCUMENT 06**


## Appendix A. Storage Table Classification

| Schema | Table | Classification |
| --- | --- | --- |
| public | static_memory | Human/operator-authored static rules |
| public | dynamic_memory | Steward-admitted durable facts |
| public | runtime_config | Live key/value configuration |
| public | reference_ingestion | Reference ingestion audit/metadata |
| public | git_connections | Repository connection metadata |
| public | agent_outcome_submission | AMP idempotency and result state |
| public | agent_reference | Deterministic reusable agent artifacts |
| public | context_feedback | Context-usefulness feedback |
| public | admission_candidate | Provisioned candidate ledger; proposed admission-control runtime |
| public | admission_decision | Provisioned decisions; proposed runtime |
| public | failure_memory | Provisioned failure-memory store; proposed runtime |
| public | quarantined_candidate | Provisioned quarantine store; proposed runtime |
| telemetry | request | Router request lifecycle |
| telemetry | step | Step/timing telemetry |
| telemetry | retrieval | Retrieval accounting |
| telemetry | admission | Ordinary Steward admission accounting |
| telemetry | agent_outcome | AMP outcome accounting |
| telemetry | context_feedback | Feedback accounting |
| telemetry | admission_gate | Provisioned gate telemetry; proposed runtime |
| telemetry | admission_audit | Provisioned audit telemetry; proposed runtime |
| telemetry | context_diff | Provisioned context-diff telemetry; proposed runtime |

## Appendix B. Detailed Schema Reference

The following tables are included because they participate directly in memory, agent, configuration, or observability reasoning. Column definitions are transcribed from the current SQL migrations/schema; they are not a substitute for the migration files when applying DDL.

### `dynamic_memory`

Source: `sql/migrations/000_base.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| project_id | TEXT NOT NULL |
| scope | TEXT NULL |
| type | TEXT NOT NULL |
| content | TEXT NOT NULL |
| content_hash | TEXT NOT NULL |
| high_confidence | BOOLEAN NOT NULL DEFAULT TRUE |
| evidence_type | TEXT NULL |
| evidence_ref | TEXT NULL |
| qdrant_point_id | TEXT NOT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `telemetry.request`

Source: `sql/migrations/010_telemetry_schema.sql`.

| Column | SQL definition |
| --- | --- |
| request_id | text PRIMARY KEY |
| project_id | text NOT NULL |
| t_begin | timestamptz NOT NULL |
| t_end | timestamptz |
| origin | text |
| origin_hash | text |
| model_requested | text |
| model_sent_to_builder | text |
| decided_mode | text |
| http_status | integer |
| error_kind | text |
| error_detail | text |
| prompt_tokens | integer |
| completion_tokens | integer |
| total_tokens | integer |
| context_budget_max | integer |
| static_tokens_est | integer |
| dynamic_tokens_est | integer |
### `telemetry.step`

Source: `sql/migrations/010_telemetry_schema.sql`.

| Column | SQL definition |
| --- | --- |
| id | bigserial PRIMARY KEY |
| request_id | text NOT NULL REFERENCES telemetry.request(request_id) ON DELETE CASCADE |
| project_id | text NOT NULL |
| name | text NOT NULL |
| t_begin | timestamptz NOT NULL |
| t_end | timestamptz |
| duration_ms | integer |
| ok | boolean |
| http_status | integer |
| error_detail | text |
| extra_json | jsonb |
### `telemetry.retrieval`

Source: `sql/migrations/010_telemetry_schema.sql`.

| Column | SQL definition |
| --- | --- |
| request_id | text PRIMARY KEY REFERENCES telemetry.request(request_id) ON DELETE CASCADE |
| project_id | text NOT NULL |
| dense_candidates | integer NOT NULL DEFAULT 0 |
| selected_topk | integer NOT NULL DEFAULT 0 |
| context_tokens_est | integer NOT NULL DEFAULT 0 |
| dropped_budget | integer NOT NULL DEFAULT 0 |
| dropped_no_content | integer NOT NULL DEFAULT 0 |
| dropped_other | integer NOT NULL DEFAULT 0 |
### `telemetry.admission`

Source: `sql/migrations/010_telemetry_schema.sql`.

| Column | SQL definition |
| --- | --- |
| request_id | text PRIMARY KEY REFERENCES telemetry.request(request_id) ON DELETE CASCADE |
| project_id | text NOT NULL |
| t_begin | timestamptz NOT NULL |
| t_end | timestamptz |
| fragments_extracted | integer NOT NULL DEFAULT 0 |
| fragments_inserted | integer NOT NULL DEFAULT 0 |
| qdrant_upserts | integer NOT NULL DEFAULT 0 |
| admission_lag_ms | integer |
| ok | boolean NOT NULL DEFAULT true |
| error_detail | text |
### `runtime_config`

Source: `sql/migrations/020_runtime_config.sql`.

| Column | SQL definition |
| --- | --- |
| key | TEXT PRIMARY KEY |
| value | TEXT NOT NULL |
| updated_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `reference_ingestion`

Source: `sql/migrations/030_reference_ingestion.sql`.

| Column | SQL definition |
| --- | --- |
| id | BIGSERIAL PRIMARY KEY |
| product | TEXT NOT NULL |
| version | TEXT NOT NULL |
| scope | TEXT NOT NULL DEFAULT 'general' |
| source_url | TEXT NOT NULL |
| chunk_count | INTEGER NOT NULL DEFAULT 0 |
| upserted_count | INTEGER NOT NULL DEFAULT 0 |
| ingested_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `admission_candidate`

Source: `sql/migrations/060_admission_control.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| request_id | TEXT NOT NULL |
| project_id | TEXT NOT NULL |
| scope | TEXT NULL |
| candidate_type | TEXT NOT NULL |
| claim | TEXT NOT NULL |
| normalized_claim | TEXT NOT NULL |
| candidate_hash | TEXT NOT NULL |
| evidence | JSONB NOT NULL DEFAULT '[]'::jsonb |
| evidence_count | INTEGER NOT NULL DEFAULT 0 |
| extractor_confidence | DOUBLE PRECISION NOT NULL DEFAULT 0.0 |
| ttl | TEXT NULL |
| supersedes | JSONB NOT NULL DEFAULT '[]'::jsonb |
| raw_candidate | JSONB NOT NULL DEFAULT '{}'::jsonb |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `admission_decision`

Source: `sql/migrations/060_admission_control.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| candidate_id | UUID NULL REFERENCES admission_candidate(id) ON DELETE SET NULL |
| request_id | TEXT NOT NULL |
| project_id | TEXT NOT NULL |
| outcome | TEXT NOT NULL CHECK (outcome IN ('admit', 'hold', 'reject', 'quarantine')) |
| score | INTEGER NOT NULL CHECK (score >= 0 AND score <= 100) |
| reasons | JSONB NOT NULL DEFAULT '[]'::jsonb |
| auditor_verdict | JSONB NULL |
| admitted_memory_id | UUID NULL REFERENCES dynamic_memory(id) ON DELETE SET NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `failure_memory`

Source: `sql/migrations/060_admission_control.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| project_id | TEXT NOT NULL |
| attempted_hash | TEXT NOT NULL |
| attempted_normalized | TEXT NOT NULL |
| outcome | TEXT NOT NULL |
| reason_code | TEXT NOT NULL |
| reason | TEXT NULL |
| scope | TEXT NULL |
| recorded_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `quarantined_candidate`

Source: `sql/migrations/060_admission_control.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| request_id | TEXT NOT NULL |
| project_id | TEXT NOT NULL |
| reason | TEXT NOT NULL |
| raw_payload | JSONB NOT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `telemetry.admission_gate`

Source: `sql/migrations/060_admission_control.sql`.

| Column | SQL definition |
| --- | --- |
| id | BIGSERIAL PRIMARY KEY |
| request_id | TEXT NOT NULL REFERENCES telemetry.request(request_id) ON DELETE CASCADE |
| project_id | TEXT NOT NULL |
| candidate_hash | TEXT NULL |
| gate | TEXT NOT NULL |
| passed | BOOLEAN NOT NULL |
| reason | TEXT NULL |
| score_delta | INTEGER NOT NULL DEFAULT 0 |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `telemetry.admission_audit`

Source: `sql/migrations/060_admission_control.sql`.

| Column | SQL definition |
| --- | --- |
| id | BIGSERIAL PRIMARY KEY |
| request_id | TEXT NOT NULL REFERENCES telemetry.request(request_id) ON DELETE CASCADE |
| project_id | TEXT NOT NULL |
| candidate_hash | TEXT NOT NULL |
| auditor_model | TEXT NOT NULL |
| verdict | TEXT NULL |
| confidence | DOUBLE PRECISION NULL |
| flags | JSONB NOT NULL DEFAULT '[]'::jsonb |
| ok | BOOLEAN NOT NULL DEFAULT true |
| error_detail | TEXT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `telemetry.context_diff`

Source: `sql/migrations/060_admission_control.sql`.

| Column | SQL definition |
| --- | --- |
| id | BIGSERIAL PRIMARY KEY |
| request_id | TEXT NOT NULL REFERENCES telemetry.request(request_id) ON DELETE CASCADE |
| project_id | TEXT NOT NULL |
| consumer_id | TEXT NULL |
| previous_refs | JSONB NOT NULL DEFAULT '[]'::jsonb |
| current_refs | JSONB NOT NULL DEFAULT '[]'::jsonb |
| added_refs | JSONB NOT NULL DEFAULT '[]'::jsonb |
| removed_refs | JSONB NOT NULL DEFAULT '[]'::jsonb |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `agent_outcome_submission`

Source: `sql/migrations/070_agent_memory_protocol.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| project_id | TEXT NOT NULL |
| outcome_id | TEXT NOT NULL |
| task_id | TEXT NULL |
| session_id | TEXT NULL |
| context_request_id | TEXT NULL |
| objective | TEXT NOT NULL |
| request_hash | TEXT NOT NULL |
| request_payload | JSONB NOT NULL DEFAULT '{}'::jsonb |
| result_payload | JSONB NULL |
| status | TEXT NOT NULL DEFAULT 'processing' |
| error_detail | TEXT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
| updated_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `agent_reference`

Source: `sql/migrations/070_agent_memory_protocol.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| project_id | TEXT NOT NULL |
| artifact_key | TEXT NOT NULL |
| repository | TEXT NULL |
| revision | TEXT NULL |
| artifact_type | TEXT NOT NULL |
| schema_version | TEXT NOT NULL |
| producer_type | TEXT NOT NULL |
| producer_name | TEXT NULL |
| producer_version | TEXT NOT NULL |
| content_hash | TEXT NOT NULL |
| payload | JSONB NOT NULL |
| provenance | JSONB NOT NULL DEFAULT '[]'::jsonb |
| source_outcome_id | TEXT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `context_feedback`

Source: `sql/migrations/070_agent_memory_protocol.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| feedback_id | TEXT NOT NULL UNIQUE |
| context_request_id | TEXT NOT NULL |
| project_id | TEXT NOT NULL |
| used_memory_ids | JSONB NOT NULL DEFAULT '[]'::jsonb |
| irrelevant_memory_ids | JSONB NOT NULL DEFAULT '[]'::jsonb |
| missing_context | TEXT NULL |
| task_id | TEXT NULL |
| session_id | TEXT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `telemetry.agent_outcome`

Source: `sql/migrations/070_agent_memory_protocol.sql`.

| Column | SQL definition |
| --- | --- |
| id | BIGSERIAL PRIMARY KEY |
| outcome_id | TEXT NOT NULL |
| project_id | TEXT NOT NULL |
| context_request_id | TEXT NULL |
| fragments_extracted | INTEGER NOT NULL DEFAULT 0 |
| fragments_inserted | INTEGER NOT NULL DEFAULT 0 |
| artifacts_received | INTEGER NOT NULL DEFAULT 0 |
| artifacts_inserted | INTEGER NOT NULL DEFAULT 0 |
| qdrant_upserts | INTEGER NOT NULL DEFAULT 0 |
| idempotent_replay | BOOLEAN NOT NULL DEFAULT false |
| ok | BOOLEAN NOT NULL DEFAULT true |
| error_detail | TEXT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `telemetry.context_feedback`

Source: `sql/migrations/070_agent_memory_protocol.sql`.

| Column | SQL definition |
| --- | --- |
| id | BIGSERIAL PRIMARY KEY |
| feedback_id | TEXT NOT NULL UNIQUE |
| context_request_id | TEXT NOT NULL |
| project_id | TEXT NOT NULL |
| used_count | INTEGER NOT NULL DEFAULT 0 |
| irrelevant_count | INTEGER NOT NULL DEFAULT 0 |
| missing_context_reported | BOOLEAN NOT NULL DEFAULT false |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `dynamic_memory`

Source: `sql/schema.sql`.

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| project_id | TEXT NOT NULL |
| scope | TEXT NULL |
| type | TEXT NOT NULL |
| content | TEXT NOT NULL |
| content_hash | TEXT NOT NULL |
| high_confidence | BOOLEAN NOT NULL DEFAULT TRUE |
| evidence_type | TEXT NULL |
| evidence_ref | TEXT NULL |
| qdrant_point_id | TEXT NOT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |

## Appendix C. Correlation Identifiers

| Identifier | Generated/supplied by | Purpose |
| --- | --- | --- |
| Router `request_id` | Router | Correlate chat request, retrieval, errors, Builder call |
| `context_request_id` | Router structured context endpoint | Correlate agent context with later outcome/feedback |
| `outcome_id` | Agent/caller | Idempotent structured outcome identity within project |
| `feedback_id` | Caller or Steward-generated | Context feedback identity |
| `project_id` | Request context/caller | Scope memory and telemetry by project |
| Qdrant point/chunk IDs | ingestion/admission code | Retrieve/explain semantic items |

Correlation IDs should appear in logs/telemetry rather than requiring full payload logging.

## Appendix D. Observability Questions and Evidence

### D.1 "Why was this memory returned?"

Use retrieval telemetry for candidate/selection accounting, then inspect the selected item metadata and relevant Qdrant/Postgres row. If reference filters were supplied, confirm they match the request.

### D.2 "Why was this chat fact not remembered?"

Inspect Steward admission telemetry and logs: extraction result, fragments inserted, Qdrant upserts, and dependency failures. Remember that ordinary admission is asynchronous best-effort.

### D.3 "Why did this agent outcome duplicate?"

Inspect `agent_outcome_submission` by `(project_id, outcome_id)`, request hash, status, and result payload. Exact replay is expected; hash conflict is an error.

### D.4 "Why is an artifact missing from context?"

Inspect `agent_reference` selectors (artifact type, repository, revision, schema version, producer type, content hash) and compare to the Router `ArtifactSelector` supplied by the agent.

### D.5 "Why did a config change not apply?"

Check whether the key has a current consumer. If it does, check runtime-config cache TTL. If the key is `FORCE_MODE`/`HYSTERESIS_WINDOW`, persistence alone has no current request effect.

## Appendix E. Metrics/Dashboard Guidance

Useful operational views include:

- Router request rate/error rate/latency;
- retrieval candidates vs selected;
- context token estimates and budget drops;
- Builder prompt/completion usage when available;
- Steward admission success/fragments inserted/Qdrant upserts;
- agent outcome replay/conflict/failure rates;
- context feedback used/irrelevant/missing counts;
- dependency health for Postgres/Qdrant/embeddings/LLM backends;
- MCP tool failures by plane;
- LIST transcription latency/error rate when extension is deployed.

Dashboard labels should preserve request/project/outcome identity dimensions without embedding raw private content.

## Appendix F. Log Retention and Sensitivity

Logs can be more sensitive than structured telemetry because application log messages may include extraction fragments, errors, source URLs, or—when `DEBUG_PROMPTS` is enabled—complete prompt payloads. Production log retention/access policy should therefore be stricter than "logs are only diagnostics." Disable prompt debugging except for bounded investigations.

## Appendix G. Telemetry Evolution Rules

When adding telemetry:

1. prefer append-only schema migration;
2. keep high-cardinality raw payloads out unless justified;
3. define retention expectations;
4. define correlation identifiers;
5. ensure telemetry failure does not create an undocumented memory-policy change;
6. update diagnostics tools/dashboards where useful;
7. document whether a table is active runtime or provisioned future schema;
8. add tests for writer failure paths where telemetry is best-effort.
