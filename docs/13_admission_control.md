# AUDITED ADMISSION CONTROL
## Provisioned Schema and Proposed Deterministic Admission Pipeline
### Engineering Proposal (Document 13 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 12 (Extensions)](12_extensions.md) | [Next: Whitepaper](WHITEPAPER.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Current Runtime Boundary](#1-current-runtime-boundary)
- [2. Provisioned but Inactive Schema](#2-provisioned-but-inactive-schema)
- [3. Proposed Runtime Pipeline](#3-proposed-runtime-pipeline)
- [4. Requirements for Promotion to Implemented](#4-requirements-for-promotion-to-implemented)
- [5. Authority](#5-authority)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PARTIALLY PROVISIONED / RUNTIME PROPOSAL
**Audience:** Architects and admission-control implementers
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

Migration `060_admission_control.sql` provisions durable and telemetry tables for a richer audited-admission design. The active `components/memory_steward` request path does not currently execute that complete design. This document distinguishes storage that exists from runtime semantics that do not.

[Back to top](#navigation)

---

## 1. Current Runtime Boundary

The current Steward implements ordinary chat admission, structured agent outcomes, context feedback, deterministic artifact hash validation, idempotent agent-outcome submission, dense embedding, Postgres persistence, and Qdrant upsert.

For ordinary `/admit` requests, the active path is approximately:

~~~text
chat turn
  -> Steward LLM extracts fragments
  -> fragment metadata is derived
  -> Postgres dynamic_memory insert
  -> Qdrant upsert
  -> admission telemetry
~~~

For `/v1/agent/outcomes`, the active path additionally validates/persists reusable `agent_reference` artifacts and optionally extracts durable fragments from the structured outcome.

The current Steward does **not** execute a complete deterministic gate → Auditor → deterministic score → hold/reject/quarantine pipeline. It also does not consult `failure_memory` during admission and does not emit `telemetry.context_diff` from Router context assembly.

[Back to top](#navigation)

---

## 2. Provisioned but Inactive Schema

Migration `060_admission_control.sql` currently creates these public tables:

- `admission_candidate`;
- `admission_decision`;
- `failure_memory`;
- `quarantined_candidate`.

It also creates these diagnostics tables:

- `telemetry.admission_gate`;
- `telemetry.admission_audit`;
- `telemetry.context_diff`.

These tables are real database schema, but their presence MUST NOT be interpreted as proof that the corresponding admission pipeline is active. Current Steward server code does not populate/use them as the authoritative ordinary-admission path.

OCO dashboard SQL may reference provisioned admission-control tables. Empty or sparse panels are therefore possible until writers for those tables are implemented and enabled.

[Back to top](#navigation)

---

## 3. Proposed Runtime Pipeline

The provisioned schema anticipates these concepts:

1. deterministic pre-LLM or pre-Auditor admission gates;
2. a separate skeptical Auditor with broader historical evidence;
3. deterministic final admit/hold/reject/quarantine policy;
4. append-only failure memory;
5. pull-only context-diff diagnostics.

A future implementation could use a flow such as:

~~~text
candidate
  -> deterministic gates
  -> optional Auditor observation
  -> deterministic scoring/policy
  -> admit | hold | reject | quarantine
  -> telemetry / failure-memory lineage
~~~

Specific thresholds such as `MIN_EVIDENCE`, `MAX_ATTEMPTS`, score bands, cooldowns, and Auditor confidence rules are **not current runtime contracts** merely because a schema can store their results.

[Back to top](#navigation)

---

## 4. Requirements for Promotion to Implemented

Before the proposed pipeline can be documented as active runtime behavior, implementation MUST include:

- explicit gate functions and bounded reason codes;
- a deterministic decision/scoring function if score-based admission is retained;
- the Auditor input/output schema and invocation path if an Auditor is retained;
- concrete writers/readers for the provisioned admission-control tables;
- failure-memory lookup/write semantics;
- quarantine lifecycle and replay/idempotency behavior;
- context-diff production if `telemetry.context_diff` is retained;
- unit and integration tests covering admit/hold/reject/quarantine outcomes;
- telemetry and OCO verification against actual emitted data;
- updated architecture/runtime documentation.

[Back to top](#navigation)

---

## 5. Authority

Current admission behavior is defined by `components/memory_steward`, its tests, and migrations actually consumed by that code. Provisioned-but-unused tables do not override the active code path, and this proposal does not grant new runtime authority.

[Back to top](#navigation)

---

## 6. Provisioned Schema Inventory

| Table | Provisioned purpose | Active in current admission path? |
| --- | --- | --- |
| admission_candidate | Candidate ledger for deterministic gate pipeline | No |
| admission_decision | Gate/auditor decision record | No |
| failure_memory | Reusable failure evidence | No |
| quarantined_candidate | Quarantine queue/store | No |
| telemetry.admission_gate | Gate decision telemetry | No |
| telemetry.admission_audit | Auditor telemetry | No |
| telemetry.context_diff | Context-change telemetry | No |

The active `/admit` implementation calls LLM extraction and then persists derived fragments. It records ordinary admission accounting through the existing Steward telemetry writer. It does not currently create a candidate row, execute a deterministic gate registry, call a separate Auditor, or move rejected candidates through quarantine/failure-memory states.

## 7. Current Active Admission Path

~~~text
Router async /admit request
  -> Steward _extract(messages, max_fragments)
  -> extraction LLM returns structured fragments
  -> Steward derives persistence metadata
  -> Postgres dynamic_memory insert
  -> embeddings service
  -> Qdrant upsert
  -> telemetry.admission accounting
~~~

Agent outcome admission adds an idempotency and deterministic-artifact path before optional learned extraction, but that is not the proposed audited gate pipeline either.

## 8. Proposed Audited Pipeline (Non-Implemented)

A future pipeline could use the provisioned schema as follows:

~~~text
candidate capture
  -> deterministic eligibility/gate checks
  -> bounded Auditor review only where policy requires
  -> decision record
     -> accept -> dynamic memory persistence
     -> hold/quarantine -> quarantined_candidate
     -> reject/failure -> failure_memory where policy allows
  -> context-diff + gate/audit telemetry
~~~

This remains a proposal until code, tests, and runtime telemetry demonstrate those transitions.

## 9. Required Gate Properties

If implemented, deterministic gates should be:

- versioned;
- reproducible from persisted candidate inputs;
- independent of unconstrained natural-language interpretation for simple policy checks;
- observable through explicit decision codes;
- safe under retry/idempotency;
- bounded in execution time;
- testable without a live model where possible.

## 10. Auditor Boundary

An Auditor, if introduced, should not become a second hidden Steward that can rewrite rules. Its input/output schema, model route, timeout, failure fallback, and authority must be explicit. A failed Auditor call needs a deterministic policy outcome such as hold/reject rather than silent acceptance.

## 11. Promotion Checklist

This document may change from PROPOSAL/PARTIAL to IMPLEMENTED only when all applicable items exist:

1. runtime code writes/reads the provisioned tables;
2. candidate identity and idempotency are defined;
3. deterministic gate codes exist;
4. Auditor schema and route exist if an Auditor is used;
5. accept/hold/reject/quarantine transitions are implemented;
6. failure behavior is explicit;
7. telemetry rows are emitted from the actual state transitions;
8. negative/retry/concurrency tests exist;
9. migration/backfill semantics are defined;
10. operator diagnostics expose the pipeline without requiring ad hoc SQL;
11. ordinary chat latency impact is measured;
12. documentation in 01/06/08/09/11 is updated consistently.

## 12. Proposed Verification Matrix

| Scenario | Expected future evidence |
| --- | --- |
| Duplicate candidate retry | Same candidate identity; no duplicate state transition |
| Deterministic gate reject | Decision code + no dynamic-memory write |
| Auditor unavailable | Documented hold/reject fallback |
| Accepted candidate | Decision + dynamic-memory/Qdrant persistence linked by identity |
| Quarantined candidate | Quarantine row + reason + no active-memory visibility |
| Operator replay/review | Auditable transition rather than silent mutation |
| Telemetry failure | Admission policy must define whether persistence can proceed without diagnostics |

## 13. Why the Distinction Matters

Operationally, claiming an audited admission pipeline when only its schema exists is dangerous. It can lead maintainers to assume low-quality or contradictory memories are being deterministically screened when the active code still relies on extraction and persistence logic. The status label therefore protects system understanding, not merely documentation style.

---

## 6. Closing Statement

Memory Steward already provisions schema for a richer audited-admission system, but the complete deterministic gate/Auditor/failure-memory pipeline is not active today. The repository MUST keep that distinction explicit until code and tests make the provisioned model operational.

[Back to top](#navigation)

---

**END OF DOCUMENT 13**

## Appendix A. Provisioned Admission-Control Schema Details

### `admission_candidate`

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

| Column | SQL definition |
| --- | --- |
| id | UUID PRIMARY KEY DEFAULT gen_random_uuid() |
| request_id | TEXT NOT NULL |
| project_id | TEXT NOT NULL |
| reason | TEXT NOT NULL |
| raw_payload | JSONB NOT NULL |
| created_at | TIMESTAMPTZ NOT NULL DEFAULT now() |
### `telemetry.admission_gate`

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

## Appendix B. Proposed Deterministic Decision Vocabulary

The current runtime does not implement these codes; this section describes requirements for a future bounded vocabulary. A future implementation should prefer machine-readable codes such as `accept`, `reject`, `hold`, or `quarantine` plus reason codes over free-form decision prose.

Reason codes should distinguish at least:

- malformed candidate;
- unsupported evidence class;
- insufficient provenance;
- contradiction requiring review;
- duplicate/redundant fact;
- speculative/low-confidence statement;
- policy-prohibited content class;
- auditor unavailable/timeout;
- persistence dependency failure.

## Appendix C. Candidate Identity Requirements

A future candidate pipeline needs stable identity across retries. Candidate identity should be derived from project/scope/content/provenance in a documented canonical form. The idempotency design used by AMP outcomes is a useful precedent but is not automatically the admission-candidate implementation.

## Appendix D. Proposed Transition Invariants

If the pipeline is implemented:

1. one candidate identity must not have contradictory terminal decisions without an explicit revision record;
2. rejected/quarantined candidates must not appear in active dynamic retrieval;
3. acceptance must link the decision to resulting dynamic-memory/Qdrant identity;
4. retries must not duplicate persistence;
5. auditor failures must never silently become acceptance;
6. telemetry must reference the candidate/decision IDs;
7. operator override/review must be auditable;
8. failure-memory writes must be policy-bound and not become a hidden prompt lane.

## Appendix E. Concurrency Scenarios for Future Tests

| Scenario | Required property |
| --- | --- |
| two identical candidates arrive simultaneously | one logical candidate identity/decision |
| same candidate retried after timeout | replay/continue, not duplicate |
| auditor returns after operator already rejected | deterministic conflict handling |
| persistence succeeds but telemetry write fails | documented consistency decision |
| Postgres decision commits but Qdrant upsert fails | repairable/linkable partial state |
| candidate quarantined while a second worker evaluates | lock/version prevents double terminal transition |

## Appendix F. Current vs Future Comparison

| Capability | Current `/admit` | Proposed audited pipeline |
| --- | --- | --- |
| LLM extraction | Yes | Possibly, but bounded within explicit candidate flow |
| deterministic gate registry | No | Required for proposal |
| separate Auditor | No | Optional/design-dependent but explicit if used |
| admission_candidate writes | No | Yes |
| admission_decision writes | No | Yes |
| quarantine transitions | No | Yes when policy requires |
| failure_memory | No active flow | Explicit bounded use |
| gate/audit telemetry | Schema only | Runtime writes required |
| ordinary telemetry.admission | Yes | Retained/extended as appropriate |

## Appendix G. Operator Diagnostics Required Before Promotion

A production audited pipeline should provide an operator with a supported way to answer:

- what candidate was evaluated;
- which gate version ran;
- which reason code fired;
- whether an Auditor was invoked;
- Auditor model/version and bounded result metadata;
- terminal decision;
- persistence outcome;
- linked dynamic/Qdrant identity if accepted;
- quarantine/review status if held;
- retry history and error details.

Direct SQL may remain useful, but it should not be the only supported explanation path.
