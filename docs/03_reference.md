# REFERENCE MEMORY
## Explicit Ingestion, Exact Metadata Filters, and Read-Only Retrieval
### Foundational Engineering Specification (Document 03 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 02 (Operational Mode)](02_operational_mode.md) | [Next: Document 04 (Optimizations)](04_optimizations.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Definition](#1-definition)
- [2. Ingestion Surface](#2-ingestion-surface)
- [3. Metadata](#3-metadata)
- [4. Retrieval](#4-retrieval)
- [5. APIs](#5-apis)
- [6. Gating](#6-gating)
- [7. Invariants](#7-invariants)
- [8. Closing Statement](#8-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers, operators, agent-runtime integrators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

[Back to top](#navigation)

---

## 1. Definition

Canonical Reference Memory is explicitly ingested source material stored/indexed with `memory_type=reference_memory`. It is separate from conversation-derived `dynamic_memory` and structured `agent_reference` artifacts.

Reference memory is read-only during normal inference. It is created/removed only by explicit operator/tool actions.

[Back to top](#navigation)

---

## 2. Ingestion Surface

The implemented ingestion surface lives in `memory-steward-mcp` content-plane tools:

- `ref_ingest_url`
- `ref_ingest_text`
- `ref_list`
- `ref_inspect`
- `ref_purge`

Ingestion is synchronous in the current implementation; these tools do not return a background job handle.

[Back to top](#navigation)

---

## 3. Metadata

Ingested chunks carry source metadata used by inspection/retrieval. The Router's v1 caller-controlled exact-match filter whitelist is:

- `product`
- `version`
- `scope`
- `provider`
- `source`

Unknown filter keys are rejected by request validation.

[Back to top](#navigation)

---

## 4. Retrieval

The Router always constrains the reference lane with:

~~~text
memory_type = reference_memory
~~~

For every caller-supplied `reference_filters` entry, it adds an exact-match Qdrant condition for that field.

If `reference_filters` is omitted or empty, the Router does not synthesize product/version/scope/provider/source narrowing.

Semantic similarity ranks candidates inside the resulting filter set; selected material then participates in MMR and context-token budgeting.

[Back to top](#navigation)

---

## 5. APIs

Agent-facing read paths include:

- `POST /v1/context/retrieve` — governed structured context, optionally including reference candidates.
- `POST /v1/reference/search` — reference-only semantic search with optional exact filters.
- `GET /v1/reference/{chunk_id}` — fetch one reference chunk by stable point id.

The MCP agent plane exposes adapters:

- `memory.retrieve_context`
- `memory.reference.search`
- `memory.reference.get`

[Back to top](#navigation)

---

## 6. Gating

Current reference retrieval in general structured context is mode-gated by Router code. The implemented mode allow-set is:

~~~text
engineering, implementation, formal_spec
~~~

There is currently no separate intent classifier and no mandatory product/version gate.

[Back to top](#navigation)

---

## 7. Invariants

- Dynamic-memory admission MUST NOT create canonical reference memory.
- `agent_reference` MUST NOT be silently promoted to canonical reference memory.
- Normal retrieval MUST constrain the reference lane by `memory_type=reference_memory`.
- Optional caller filters are narrowing only; no implicit product/version inference occurs.

[Back to top](#navigation)

---

## 8. Closing Statement

Reference Memory is an explicit, versioned, operator-managed retrieval corpus. Runtime retrieval MUST remain read-only and MUST apply only the exact metadata narrowing requested by the caller.

[Back to top](#navigation)

---

**END OF DOCUMENT 03**
