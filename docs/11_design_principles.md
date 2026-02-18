
# DESIGN PHILOSOPHY & ASYNC SEMANTICS
## Freshness, Human-Tempo Interaction, and Storage Theory
### Foundational Engineering Specification (Document 11 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 10 (Landscape)](10_industry_landscape.md) | [Next: Document 12 (Extensions)](12_extensions.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. Storage Philosophy](#2-storage-philosophy)
- [3. Asynchronous Semantics](#3-asynchronous-semantics)
- [4. Freshness vs. Latency](#4-freshness-vs-latency)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** Core maintainers, storage engineers
**Change policy:**
- Append-only
- No silent edits

[Back to top](#navigation)

---

## 1. Purpose

This document captures the "Soft" engineering decisions—the *why* behind the *how*. It merges the Storage Philosophy and Asynchronous Design specs.

[Back to top](#navigation)

---

## 2. Storage Philosophy

Memory Steward follows three foundational principles:

1.  **Atomicity over Aggregation:** Store individual facts ("Project code is 994"), not summaries ("User talked about project codes").
2.  **Retrieval over Compression:** Do not compress context; filter it.
3.  **Auditability over Convenience:** Every memory must be traceable to a specific admission event.

[Back to top](#navigation)

---

## 3. Asynchronous Semantics

### 3.1 Human-Tempo Interaction
The system assumes a human cadence (seconds to minutes between turns).
This allows the **Steward** to perform expensive admission logic in the background without blocking the **Router's** fast response.

### 3.2 The Inconsistency Window
* **State:** Memory updates may lag one turn behind the conversation.
* **Impact:** If a user says "My name is Bob" and immediately asks "What is my name?" in < 500ms, the system *might* miss it.
* **Acceptance:** This is an accepted trade-off for architectural separation.

[Back to top](#navigation)

---

## 4. Freshness vs. Latency

We prioritize **Correctness of Extraction** over **Immediacy of Availability**.
It is better to remember the right fact 2 seconds late than to remember a hallucination instantly.

[Back to top](#navigation)

---

## 5. Closing Statement

The architecture is intentionally **loosely coupled** to allow the Control Plane to operate at a higher cognitive level (and slower speed) than the conversational Data Plane.

---

**END OF DOCUMENT 11**
