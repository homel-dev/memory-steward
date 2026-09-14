# EXECUTION OPTIMIZATIONS
## Current Fast Paths, Budgets, and Explicit Backlog
### Foundational Engineering Specification (Document 04 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 03 (Reference Memory)](03_reference.md) | [Next: Document 05 (Stability)](05_stability.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Implemented](#1-implemented)
- [2. Not Implemented](#2-not-implemented)
- [3. Telemetry Caveat](#3-telemetry-caveat)
- [4. Optimization Rule](#4-optimization-rule)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PARTIAL
**Audience:** Maintainers and performance engineers
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

This document separates optimizations present in code from ideas that are not implemented.

[Back to top](#navigation)

---

## 1. Implemented

### 1.1 Structured Retrieval Reuse

Chat and AMP retrieval use the same structured Router retrieval operation before presentation-specific rendering. Agent retrieval can return context without invoking the Builder.

### 1.2 Bounded Retrieval

The Router applies bounded prefetch/top-k values, MMR selection, and a maximum context-token budget. Static and dynamic/reference context accounting is emitted to telemetry.

### 1.3 Runtime Token Budget

`MAX_CONTEXT_TOKENS` can be persisted in `runtime_config`; the Router periodically reloads this key and applies it to subsequent requests.

### 1.4 Async Chat Admission Dispatch

After a chat response, Router admission is dispatched to Memory Steward asynchronously. Admission failure does not replace a successful Builder response.

### 1.5 Builder Runtime Selection

The Router can consume persisted `BUILDER_BASE_URL` and `BUILDER_MODEL` runtime keys. The current configuration module still requires `BUILDER_MODEL` at process startup, so the model-discovery helper is not a normal fallback path in the deployed contract.

[Back to top](#navigation)

---

## 2. Not Implemented

The current tree does not implement the following previously discussed optimizations:

- speculative mode routing;
- scatter/gather retrieval across predicted modes;
- semantic cache for mode classification;
- static-memory preload cache in the Router;
- reference-memory shadow collections + atomic alias switching;
- a GitOps operator that watches a knowledge manifest.

These are backlog/design ideas, not runtime guarantees.

[Back to top](#navigation)

---

## 3. Telemetry Caveat

Router telemetry writes are synchronous best-effort Postgres calls with short connection timeouts. They are failure-isolated, but they are not an asynchronous telemetry queue.

[Back to top](#navigation)

---

## 4. Optimization Rule

An optimization MUST preserve API semantics, memory-type isolation, deterministic filter construction, and selection/budget accounting. If it changes observable behavior, it requires tests and documentation in the same change set.

[Back to top](#navigation)

---

## 5. Closing Statement

Optimization claims in this repository MUST be grounded in current code. Speculation, semantic caches, and other future fast paths remain non-contractual until implemented and covered by executable tests.

[Back to top](#navigation)

---

**END OF DOCUMENT 04**
