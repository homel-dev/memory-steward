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

## 8. Closing Statement

Telemetry is a diagnostics plane with bounded operational exposure. It MUST remain separate from durable learned memory and MUST NOT be injected automatically into Builder context.

[Back to top](#navigation)

---

**END OF DOCUMENT 06**
