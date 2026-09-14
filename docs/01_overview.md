# IMPLEMENTED ARCHITECTURE
## Memory Steward Runtime and Authority Boundaries
### Foundational Engineering Specification (Document 01 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 00 (Style Guide)](00_style_guide.md) | [Next: Document 02 (Operational Mode)](02_operational_mode.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Runtime Components](#1-runtime-components)
- [2. Component Responsibilities](#2-component-responsibilities)
- [3. Memory Classes](#3-memory-classes)
- [4. Authority Invariants](#4-authority-invariants)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers, operators, agent-runtime integrators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

This document describes the current deployable architecture.

[Back to top](#navigation)

---

## 1. Runtime Components

~~~mermaid
graph TD
    Client[OpenAI client / Open WebUI]
    Agent[Agent runtime]
    Router[memory-router]
    Steward[memory-steward]
    MCP[memory-steward-mcp]
    LIST[memory-steward-list]
    Emb[embeddings]
    Builder[Builder LLM]
    PG[(Postgres)]
    Q[(Qdrant)]

    Client -->|/v1/chat/completions| Router
    Agent -->|/v1/context/retrieve| Router
    Agent -->|MCP tools| MCP
    MCP -->|agent retrieval adapters| Router
    MCP -->|operator content/config/diagnostics| PG
    MCP -->|reference content/diagnostics| Q
    Router -->|dense embedding| Emb
    Router -->|static + artifact reads| PG
    Router -->|dynamic/reference retrieval| Q
    Router -->|chat inference| Builder
    Router -.->|async /admit| Steward
    Steward -->|embedding| Emb
    Steward -->|dynamic + artifacts + feedback| PG
    Steward -->|dynamic index| Q
    LIST -->|speech transcription only| Client
~~~

[Back to top](#navigation)

---

## 2. Component Responsibilities

### 2.1 Memory Router

The Router owns:

- OpenAI-compatible chat ingress.
- Project identity resolution.
- Static-memory reads.
- Dynamic/reference retrieval from Qdrant.
- Exact `agent_reference` reads from Postgres.
- MMR selection and context-token budgeting.
- Canonical Builder envelope construction.
- Builder dispatch.
- Structured AMP context retrieval without a Builder call.
- Asynchronous ordinary-chat admission dispatch to Memory Steward.

It does not write durable learned memory.

### 2.2 Memory Steward

The Steward owns:

- ordinary-chat extraction and admission through `POST /admit`;
- structured agent-outcome handling through `POST /v1/agent/outcomes`;
- idempotent agent outcome submissions;
- validated `agent_reference` persistence;
- context-feedback persistence through `POST /v1/context/feedback`;
- dynamic-memory persistence to Postgres and Qdrant.

The current Steward does **not** classify operational mode.

### 2.3 Memory Steward MCP

MCP is the internal operator and agent control surface. It registers content, stability/config, diagnostics, Git/repository, and AMP adapter tools. Its live tool schema is the command contract used by both `/glap` and terminal clients.

### 2.4 Storage

- Postgres is canonical for structured state, runtime configuration, telemetry, ingestion records, agent outcomes, feedback, and `agent_reference` artifacts.
- Qdrant is the semantic retrieval index for dynamic and canonical reference memory.
- Qdrant is not the sole canonical representation of structured `agent_reference` artifacts.

[Back to top](#navigation)

---

## 3. Memory Classes

- `static_memory` — human/operator-managed rules; Router reads active global rules and optionally mode-matched rules.
- `dynamic_memory` — Steward-admitted learned fragments, project-scoped.
- `reference_memory` — explicitly ingested canonical source material, retrieval-only at inference time.
- `agent_reference` — structured reusable agent/tool/analyzer artifacts stored in Postgres; distinct from canonical reference memory.
- telemetry/feedback — diagnostics data, not Builder memory.

[Back to top](#navigation)

---

## 4. Authority Invariants

- Builder inference does not decide durable memory writes.
- MCP adapters for AMP call the Router/Steward HTTP operations instead of reimplementing their policy.
- Reference memory is ingested explicitly; chat admission does not promote material into it.
- Telemetry is diagnostics data and is not automatically injected into Builder context.
- Current runtime behavior is defined by code/tests; proposal documents do not activate features.

[Back to top](#navigation)

---

## 5. Closing Statement

This document is the implementation-aligned map of deployable units, authority boundaries, memory classes, and request paths. Changes to those runtime facts MUST update this document in the same change set.

[Back to top](#navigation)

---

**END OF DOCUMENT 01**
