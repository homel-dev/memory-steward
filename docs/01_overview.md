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

## 5. End-to-End Runtime Topology

~~~mermaid
flowchart LR
    Client[OpenAI client / Open WebUI] --> Router[memory-router]
    Agent[Agent / automation] --> Router
    Agent --> MCP[memory-steward-mcp]
    Operator[Operator] --> MCP
    TUI[Steward TUI] --> MCP
    Router --> Embed[embeddings]
    Router --> PG[(Postgres)]
    Router --> Q[(Qdrant)]
    Router --> Builder[Builder LLM]
    Router -. async admit .-> Steward[memory-steward]
    MCP --> Router
    MCP --> Steward
    MCP --> PG
    MCP --> Q
    Steward --> Embed
    Steward --> PG
    Steward --> Q
    LIST[memory-steward-list] --> Whisper[local Whisper model]
~~~

The graph shows runtime authority, not a claim that every connection is used on every request. Router owns context assembly and Builder dispatch. Steward owns durable learned-memory writes. MCP is an internal control/adapter surface. LIST is intentionally isolated from conversational memory payloads.

## 6. Public and Internal HTTP Contract

| Component | Method | Path | Purpose | Mutation |
| --- | --- | --- | --- | --- |
| memory-router | GET | /healthz | Liveness/availability check | No memory mutation |
| memory-router | GET | /v1/models | Expose effective Builder model | Reads runtime Builder model selection |
| memory-router | POST | /v1/chat/completions | OpenAI-compatible chat ingress | Retrieves context, calls Builder, dispatches ordinary-chat admission asynchronously |
| memory-router | POST | /v1/context/retrieve | Structured context retrieval for agents | No Builder call; returns governed context plus accounting |
| memory-router | POST | /v1/reference/search | Canonical Reference Memory search | Exact optional metadata filters; project context from request headers |
| memory-router | GET | /v1/reference/{chunk_id} | Fetch one reference chunk | 404 when absent |
| memory-steward | GET | /healthz | Steward liveness | No mutation |
| memory-steward | POST | /admit | Ordinary-chat durable-memory admission | LLM extraction followed by Postgres/Qdrant persistence |
| memory-steward | POST | /v1/agent/outcomes | Structured agent outcome submission | Idempotency, deterministic artifact persistence, optional durable-knowledge extraction |
| memory-steward | POST | /v1/context/feedback | Context usefulness feedback | Stores used/irrelevant/missing-context feedback and telemetry |
| memory-steward-list | GET | /healthz | LIST liveness | No database dependency |
| memory-steward-list | POST | /v1/audio/transcriptions | OpenAI-style transcription alias | Local Whisper transcription |
| memory-steward-list | POST | /v1/list/transcribe | Canonical LIST transcription route | Local Whisper transcription |
| memory-steward-list | POST | /v1/list/translate | Reserved translation route | Currently returns HTTP 501 |
| embeddings | GET | /healthz | Embedding service liveness | Reports model readiness |
| embeddings | POST | /embed | Dense embedding generation | Used by Router and Steward |

## 7. Ordinary Chat Request Lifecycle

### 7.1 Chat sequence

~~~text
Client -> Router: POST /v1/chat/completions
Router -> request context: resolve project identity/origin
Router -> token counter: estimate current user text
Router -> history budget: prune older history against MAX_TOTAL_TOKENS
Router -> Postgres: load active static memory (global + optional exact mode)
Router -> embeddings: embed query
Router -> Qdrant: dense dynamic-memory retrieval for project
Router -> Qdrant: reference retrieval only when eligible
Router -> Postgres: load exact agent_reference artifacts when selected by agent API (not ordinary chat selectors)
Router -> MMR/budget stage: select and bound candidates
Router -> context renderer: create canonical context envelope
Router -> Builder LLM: system context + pruned history + current message
Builder LLM -> Router -> Client: completion / stream
Router -> Steward: async POST /admit for ordinary-chat admission
Router -> telemetry: request/retrieval accounting
~~~


Important consequences:

- The Builder payload uses the **pruned** history, not the original unbounded history.
- Retrieval context and history have separate budgeting concerns.
- Ordinary-chat admission is dispatched after the response path and is not a prerequisite for returning the Builder answer.
- A Steward admission failure does not retroactively invalidate the already-produced chat response.

## 8. Structured Agent Context Lifecycle

### 8.1 Agent retrieval sequence

~~~text
Agent -> Router: POST /v1/context/retrieve
Router: require query or artifact_selectors
Router: assign context_request_id and project identity
Router: retrieve static, dynamic, optional reference, and selected deterministic artifacts
Router: apply context budget and accounting
Router -> Agent: structured lanes + selected items + dialogue_state + accounting
Router -> telemetry: request and retrieval rows
~~~


The structured endpoint does **not** call the Builder. It is an evidence/context service for agents that want to perform their own inference or deterministic processing.

## 9. Structured Agent Outcome Lifecycle

### 9.1 Outcome sequence

~~~text
Agent -> Steward or MCP adapter: submit outcome_id + project_id + structured outcome
Steward -> Postgres: reserve idempotency identity by project_id/outcome_id
Steward: reject same outcome_id with a different canonical request hash (HTTP 409)
Steward -> Postgres: persist deterministic reusable artifacts as agent_reference
Steward -> extraction LLM: only when admit_knowledge=true
Steward -> embeddings/Qdrant/Postgres: persist accepted durable fragments
Steward -> Postgres: mark outcome complete and store result payload
Replay -> Steward: return stored completed result with idempotent_replay=true
~~~


`agent_reference` is a distinct, lower-authority reusable evidence lane. It is not silently promoted to canonical external Reference Memory.

## 10. Storage Authority Matrix

| Store/table or collection | Writer(s) | Reader(s) | Purpose |
| --- | --- | --- | --- |
| Postgres static_memory | MCP/operator tooling | Router, MCP | Global and exact-mode static rules |
| Postgres dynamic_memory | Steward | Router, MCP diagnostics | Durable learned fragments and metadata |
| Postgres runtime_config | MCP configuration tools | Router for active keys; MCP diagnostics | Live configuration key/value store |
| Postgres agent_outcome_submission | Steward | Steward | Outcome idempotency and completed response persistence |
| Postgres agent_reference | Steward | Router structured retrieval | Deterministic reusable agent artifacts |
| Postgres context_feedback | Steward | Diagnostics/analysis | Used/irrelevant/missing-context feedback |
| Postgres telemetry.* | Router/Steward | MCP diagnostics / observability | Operational evidence; not prompt memory |
| Qdrant homel_memory | Steward and explicit reference ingestion | Router / MCP diagnostics | Semantic index for dynamic and reference memory |

## 11. Memory-Type Semantics

### 11.1 Static global memory

Human/operator-authored rules selected without semantic search. Global rows are eligible on every Router context assembly.

### 11.2 Static mode-conditioned memory

Human/operator-authored rows selected by exact caller-supplied mode. The current runtime does not infer the mode.

### 11.3 Dynamic memory

Steward-admitted durable fragments. Retrieval is project-scoped and semantic. Dynamic memory represents learned facts/decisions/preferences, not authoritative external documentation.

### 11.4 Reference memory

Explicitly ingested authoritative material. Qdrant payloads are marked `memory_type=reference_memory`; Router reference queries always require that discriminator and may add only explicitly supplied exact metadata filters.

### 11.5 Agent reference artifacts

Structured artifacts produced by agents and persisted deterministically in Postgres. They are selected by explicit artifact selectors rather than semantic reference-memory search.

### 11.6 Telemetry

Operational diagnostics. Telemetry is never a cognitive memory lane and is not injected into Builder prompts by default.

## 12. Authority and Non-Authority Boundaries

The following boundaries are current implementation requirements:

- Router MAY read memory and assemble prompts; it MUST NOT independently decide which conversational facts deserve durable admission.
- Steward MAY write dynamic durable memory; it MUST NOT assemble Builder prompts or answer the user.
- MCP MAY expose operator mutations, but tools remain explicit operations and do not create hidden background policy.
- The model backend is replaceable and does not own memory state.
- Reference ingestion is explicit; ordinary conversations do not become Reference Memory.
- Deterministic agent artifacts and learned durable facts remain separate lanes.
- A migration that provisions an admission-control table does not establish an active admission gate/auditor pipeline.

## 13. Failure Isolation

| Failure | Expected boundary | Result |
| --- | --- | --- |
| Builder unavailable | Router chat path | Chat request fails; stored memory is not mutated by the Builder failure itself |
| Embeddings unavailable | Retrieval/admission path | Semantic retrieval or admission requiring embeddings fails; health diagnostics should surface dependency failure |
| Qdrant unavailable | Semantic lane | Dynamic/reference semantic retrieval fails; exact Postgres lanes remain conceptually separate |
| Postgres unavailable | Static/config/telemetry/exact-artifact lanes | Affected Router/Steward operations fail or use documented cache/default behavior where implemented |
| Steward unavailable during async chat admission | Post-response admission | User response may already have succeeded; durable admission is lost/failed for that dispatch |
| Steward LLM unavailable | Durable extraction | Deterministic agent artifacts can be persisted independently before optional knowledge extraction; ordinary admission fails |
| MCP unavailable | Operator/adapter plane | Direct Router/Steward HTTP APIs remain separate runtime surfaces |
| LIST unavailable | Speech extension | Core Router/Steward memory paths remain independent |

## 14. Current Configuration Boundaries

The Router has environment defaults plus a short-lived Postgres `runtime_config` cache. Only keys with current consumers should be described as active live controls. `MAX_CONTEXT_TOKENS`, `BUILDER_BASE_URL`, and `BUILDER_MODEL` have active Router consumers. `FORCE_MODE` and `HYSTERESIS_WINDOW` are compatibility/diagnostic values without a current mode engine.

## 15. Architectural Review Checklist

When changing this architecture, verify:

1. which component now owns the decision;
2. whether a new write path was introduced;
3. whether semantic and deterministic evidence lanes remain distinguishable;
4. whether a new dependency can block the user-facing hot path;
5. whether a runtime_config key has a real consumer;
6. whether telemetry contains payload data or only bounded diagnostics;
7. whether operator mutations are explicit and auditable;
8. whether documentation, tests, Task wrappers, and manifests describe the same topology.

---

## 5. Closing Statement

This document is the implementation-aligned map of deployable units, authority boundaries, memory classes, and request paths. Changes to those runtime facts MUST update this document in the same change set.

[Back to top](#navigation)

---

**END OF DOCUMENT 01**
