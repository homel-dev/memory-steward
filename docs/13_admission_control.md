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

## 6. Closing Statement

Memory Steward already provisions schema for a richer audited-admission system, but the complete deterministic gate/Auditor/failure-memory pipeline is not active today. The repository MUST keep that distinction explicit until code and tests make the provisioned model operational.

[Back to top](#navigation)

---

**END OF DOCUMENT 13**
