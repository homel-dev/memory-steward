
# CONTROL-PLANE EXECUTION OPTIMIZATIONS
## Latency, Parallelism, and Deterministic Speculation
### Foundational Engineering Specification (Document 04 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 03 (Reference)](03_reference.md) | [cite_start][Next: Document 05 (Stability)](05_stability.md) →** [cite: 531]

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. Problem Statement](#2-problem-statement)
- [3. Principle: Determinism First, Performance Second](#3-principle-determinism-first-performance-second)
- [4. [cite_start]Speculative Routing (Primary Optimization)](#4-speculative-routing-primary-optimization) [cite: 532]
- [5. Semantic Caching (The Fast Path)](#5-semantic-caching-the-fast-path)
- [6. Scatter-Gather Speculation (Parallel Gating)](#6-scatter-gather-speculation-parallel-gating)
- [7. Asynchronous Context Loading](#7-asynchronous-context-loading)
- [8. [cite_start]Ingestion and Versioning Optimizations](#8-ingestion-and-versioning-optimizations) [cite: 533]
- [9. [cite_start]Explicit Non-Goals](#9-explicit-non-goals) [cite: 534]
- [10. Summary](#10-summary)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** Core maintainers, performance engineers
**Change policy:**
- Append-only
- No silent edits

This document defines non-canonical execution optimizations.

[Back to top](#navigation)

---

## 1. Purpose

[cite_start]This document defines **non-canonical execution optimizations** applicable to the Memory Steward and Router control plane. [cite: 535]
These optimizations:
- improve throughput and latency
- preserve determinism
- preserve authority boundaries
- preserve auditability

All mechanisms described here are:
- **optional**
- **orthogonal**
- **non-semantic**
- **non-authoritative**

They must **never alter** canonical semantics defined in Documents 1–3.

[Back to top](#navigation)

---

## 2. Problem Statement

The canonical request lifecycle enforces a serial dependency:

1. Steward classifies Mode and Intent
2. Steward gates memory eligibility
3. Router assembles prompt
4. Model performs inference

This yields:

$$T_{total} = T_{steward} + T_{router} + T_{model}$$

While architecturally correct, this introduces **pre-inference latency**, where $T_{steward}$ may dominate in high-throughput or interactive scenarios.

[Back to top](#navigation)

---

## 3. Principle: Determinism First, Performance Second

Any optimization MUST preserve the following invariants:

- [cite_start]Steward remains the **sole authority** for: [cite: 536]
  - operational mode
  - intent classification
  - memory eligibility
- Router execution must be **fully discardable**
- Model output must **never influence** control-plane decisions
- Incorrect speculative execution must be **abortable without side effects**

[cite_start]Performance is subordinate to correctness. [cite: 537]

[Back to top](#navigation)

---

## 4. Speculative Routing (Primary Optimization)

### 4.1 Concept

[cite_start]Speculative routing allows the Router to **begin prompt assembly** before the Steward has finalized classification. [cite: 538]
[cite_start]This is done using a **predicted operational mode**, while the Steward executes classification **in parallel**. [cite: 539]

### 4.2 Execution Flow

~~text
User Request
     |
     +--> Steward (classification) -----------+
     |                                        |
+--> Router (speculative assembly)       |
                                              |
Steward Result ------+
                                 |
Validate / Abort
~~

### 4.3 Speculation Rules

Speculation is permitted only when **all** of the following hold:

- Prior mode confidence ≥ configured threshold
- No explicit mode override is present
- Session state is stable (no recent mode transitions)

[cite_start]The speculative assumption MUST be the **most restrictive plausible mode**. [cite: 543]

### 4.4 Abort Semantics

If the Steward’s authoritative result differs from the speculative assumption:
- [cite_start]Router MUST discard the partially assembled prompt. [cite: 544]
- Router MUST re-assemble using authoritative classification.
- [cite_start]No speculative context may reach the Model. [cite: 545]
Abort behavior MUST be silent and complete.

[Back to top](#navigation)

---

## 5. Semantic Caching (The Fast Path)

[cite_start]To significantly reduce $T_{steward}$, the system MAY implement a semantic cache for mode classification. [cite: 546]

### 5.1 Mechanism
- [cite_start]Store the embedding of the user's prompt mapped to the Steward's classification (`Mode` + `Intent`). [cite: 547]
- [cite_start]**TTL Required:** Cache entries must expire (e.g., 24h) to prevent stale behavioral rules. [cite: 548]

### 5.2 Lookup Logic
On a new request:
1. Embed the input.
2. [cite_start]Query the cache. [cite: 549]
3. If a hit is found with **high similarity** (e.g., $>0.95$):
   - [cite_start]Bypass the Steward LLM entirely. [cite: 550]
   - Use the cached mode.

[cite_start]**Benefit:** Reduces $T_{steward}$ from LLM inference time (~400ms+) to Vector lookup time (~10ms) for recurrent patterns. [cite: 551]

[Back to top](#navigation)

---

## 6. Scatter-Gather Speculation (Parallel Gating)

[cite_start]This optimization refines standard Speculative Routing by trading compute resources for latency reduction. [cite: 552]

### 6.1 Mechanism
[cite_start]Instead of speculating on a single mode, the Router initiates retrieval for the **top-N** (e.g., 2) most likely modes immediately and in parallel. [cite: 553]

### 6.2 Barrier Synchronization
1. **Launch:** Router spawns retrieval threads for Mode A and Mode B.
2. [cite_start]**Barrier:** Threads halt at the "Prompt Assembly" phase. [cite: 554]
3. [cite_start]**Commit:** When Steward returns the authoritative mode (e.g., Mode A), the Router instantly **commits** the matching thread and **discards** the others. [cite: 555]

**Benefit:** Eliminates the "Abort & Retry" penalty. [cite_start]The correct branch is always ready; incorrect branches are simply dropped. [cite: 556]

[Back to top](#navigation)

---

## 7. Asynchronous Context Loading

[cite_start]Decouples non-blocking operations from the critical request path. [cite: 557]

### 7.1 Static Memory Pre-load
- [cite_start]`static_global` memory SHOULD be pre-loaded into hot memory (RAM) at system startup. [cite: 558]
- [cite_start]Do not fetch static rules from the database per request. [cite: 559]

### 7.2 Background Telemetry
- [cite_start]Telemetry writes (`telemetry.request_end`, `telemetry.step`) MUST be written asynchronously (e.g., via background worker or `asyncio.create_task`). [cite: 560]
- [cite_start]**Hard Invariant:** Never block the HTTP response waiting for a database write. [cite: 561]

[Back to top](#navigation)

---

## 8. Ingestion and Versioning Optimizations

[cite_start]While primarily operational, these optimizations ensure that **Reference Memory** updates do not impact runtime latency or availability. [cite: 562]

### 8.1 Knowledge-as-Code (GitOps)
[cite_start]Treat memory ingestion as a deployment pipeline, not a database operation. [cite: 563]
- [cite_start]**Source of Truth:** A Git repository containing a `knowledge.yaml` manifest. [cite: 564]
  ~~~yaml
  - product: "terraform"
    version: "1.6.0"
    status: "active"
    source_url: "..."
  ~~~
- **Ingestion Operator:** A service watches this repo.
  On version bump:
  1. [cite_start]Ingests/embeds new docs into a **shadow namespace**. [cite: 565]
  2. Runs sanity checks (chunk count, embedding distribution).
  3. [cite_start]Marks old version as `archived`. [cite: 566]

### 8.2 Atomic Alias Switching
[cite_start]To prevent downtime during updates, use **Collection Aliasing**. [cite: 567]
- **Physical Storage:** Immutable collections (`ref_terraform_v1_5`, `ref_terraform_v1_6`).
- [cite_start]**Logical Alias:** Router queries `ref_terraform_active`. [cite: 568]
- **Switching:** The Operator updates the alias pointer in a single atomic operation.

[cite_start]**Benefit:** Zero downtime for knowledge updates; instant rollback capability. [cite: 569]

### 8.3 Strict Schema Enforcement
[cite_start]A validation layer MUST exist before embedding. [cite: 570]
- **Mechanism:** Use Pydantic/JSON Schema to validate every chunk.
- [cite_start]**Check:** Ensure `product`, `version`, and `scope` match Control Plane enums. [cite: 571]
- [cite_start]**Benefit:** Prevents "metadata pollution" and fragmentation (e.g., "Terraform" vs "terraform-core"). [cite: 572]

[Back to top](#navigation)

---

## 9. Explicit Non-Goals

This document explicitly forbids:

- Model-driven speculation
- Partial prompt reuse across modes
- Heuristic or probabilistic memory injection
- Latency-driven weakening of gates
- Any optimization that changes canonical behavior

[Back to top](#navigation)

---

## 10. Summary

| Challenge | Solution | Key Benefit |
| :--- | :--- | :--- |
| **Latency ($T_{steward}$)** | **Semantic Caching** | [cite_start]Skips LLM inference for common queries. [cite: 574] |
| **Latency (Speculation)** | **Scatter-Gather** | [cite_start]Removes "Abort & Retry" penalty; parallelizes retrieval. [cite: 575] |
| **Latency (Writes)** | **Async/Backgrounding** | Telemetry writes never block user response. |
| **Namespace (Ops)** | **GitOps / Knowledge-as-Code** | [cite_start]Audit trail, CI/CD for data, automated ingestion. [cite: 577] |
| **Namespace (Safety)** | **Atomic Aliasing** | Zero-downtime updates, instant rollbacks. |

[cite_start]Control-plane execution optimizations are acceptable **only** when they preserve determinism and authority boundaries. [cite: 578]
[cite_start]Speculative routing and caching are **performance enhancements**, not behavioral changes. [cite: 579]

---

**END OF DOCUMENT 04**
