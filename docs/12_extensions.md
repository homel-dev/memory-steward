
# EXTENSIONS AND ADDITIONS
## Canonical Extension Specification Layer for Memory Steward
### Foundational Engineering Specification (Document 12 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 11 (Design Principles)](11_design_principles.md) | [Next: Whitepaper](WHITEPAPER.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. Extension Model](#2-extension-model)
- [3. Extension Index](#3-extension-index)
- [4. Extension 12.1: Local Input Speech Transcriber (LIST)](#4-extension-121-local-input-speech-transcriber-list)
- [5. Extension 12.2: Agent Memory Protocol (AMP)](#5-extension-122-agent-memory-protocol-amp)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** Core maintainers, extension implementers, operators
**Change policy:**
- Append-only
- No silent edits

This document defines the canonical mechanism by which additive capabilities are introduced without altering or contradicting Documents 00–11.

[Back to top](#navigation)

---

## 1. Purpose

This document defines the system’s **extension surface**.

An extension is a bounded subsystem or capability that:
- Adds functionality not present in the core specification set (Documents 00–11).
- MUST NOT alter core semantics, authority boundaries, or invariants.
- MUST be optional by design (the system MUST remain functional when the extension is absent).
- MUST integrate via explicit, versioned contracts.

Extensions documented here MUST:
- Declare responsibility boundaries.
- Declare external contracts.
- Declare runtime expectations.
- Declare telemetry expectations (aligned to Document 06 telemetry canon).

[Back to top](#navigation)

---

## 2. Extension Model

### 2.1 Extension Definition

An extension is an additive subsystem that MUST satisfy all of the following:
- **Additive:** Adds new capability without modifying core semantics.
- **Optional:** Can be disabled without breaking the system.
- **Bounded:** Has clear responsibility boundaries and non-goals.
- **Contracted:** Integrates only through explicit, versioned interfaces.

An extension MUST NOT:
- Bypass core control planes.
- Introduce implicit coupling (hidden dependencies).
- Redefine memory semantics or inference semantics.
- Expand the authority surface of existing components without explicit contract changes.

### 2.2 Document Structure Rules

All extensions MUST be specified within this document as numbered sections:
- New extensions MUST be appended as new top-level sections (e.g., `12.2`, `12.3`).
- Existing extensions MUST NOT be renumbered.
- Extensions MUST NOT create new foundational documents or reorder Documents 00–11.

[Back to top](#navigation)

---

## 3. Extension Index

- **12.1 Local Input Speech Transcriber (LIST)**
- **12.2 Agent Memory Protocol (AMP)**

(Future extensions MUST be appended to this index.)

[Back to top](#navigation)

---

## 4. Extension 12.1: Local Input Speech Transcriber (LIST)

### 4.1 Purpose

Local Input Speech Transcriber (LIST) provides an input-plane capability that converts explicitly recorded user speech into plain UTF-8 text for insertion into a chat input field.

LIST exists to:
- Enable push-to-talk speech input with explicit start/stop control.
- Produce deterministic transcripts without streaming heuristics.
- Preserve strict separation from memory and inference pipelines.

### 4.2 Architectural Position

LIST sits strictly before message submission and outside memory and inference.

~~mermaid
graph TD
    User((User))
    UI[Chat UI]
    EXT[LIST Client Extension]
    LIST[memory-steward-list]
    LLM[LLM Pipeline]

    User -->|speech| UI
    UI -->|start/stop recording| EXT
    EXT -->|audio blob| LIST
    LIST -->|plain text| EXT
    EXT -->|insert text| UI
    UI -->|user sends| LLM
~~

> **Hard Invariant:** The LLM pipeline MUST NOT receive raw audio.
> **Hard Invariant:** LIST MUST NOT receive prompts, chat context, or memory payloads.

### 4.3 Responsibility Boundaries

LIST (service) MUST:
- Accept a complete audio recording as a single payload.
- Return plain UTF-8 text.
- Support transcription mode and translation mode.

LIST (service) MUST NOT:
- Stream partial transcripts.
- Perform silence-based end-of-speech detection.
- Submit messages to the LLM.
- Access memory, embeddings, or chat context.

The LIST client extension MUST:
- Provide explicit record and stop controls.
- Capture audio locally.
- Send the completed audio blob to LIST.
- Insert the returned text into the chat input field.
- Preserve the draft and allow user editing prior to send.

The LIST client extension MUST NOT:
- Auto-stop recording based on silence.
- Auto-send the transcript as a message.
- Overwrite existing draft text without deterministic insertion rules.

### 4.4 Interaction Model

Authoritative flow:
1. User explicitly starts recording.
2. User explicitly stops recording.
3. Client extension sends one audio blob to LIST.
4. LIST returns plain text.
5. Client extension inserts text into the input field.
6. User edits and sends manually.

Silence-based termination is forbidden.

### 4.5 External Contract Summary

LIST MUST expose a versioned HTTP interface:

- `POST /v1/list/transcribe`
- `POST /v1/list/translate`

Request requirements:
- `Content-Type: multipart/form-data`
- Field name: `file` (single audio file)

Response requirements (success):
- HTTP `200`
- JSON payload containing `text` (required)

Response requirements (error):
- Non-2xx status
- JSON payload containing `error` and `message`

### 4.6 Runtime Expectations

LIST runtime MUST be:
- Stateless
- Independently deployable
- Optional (absence MUST NOT break chat UI or LLM pipeline)

LIST runtime details (ports, health checks, payload limits, timeouts) MUST be defined in the Runtime Contract document.

### 4.7 Telemetry Expectations


LIST telemetry MUST align to Document 06 telemetry canon.

LIST MUST emit, at minimum:
- Request counts by mode (transcribe / translate)
- Error counts by error class
- Processing latency distributions

LIST SHOULD emit:
- Detected language distribution (when available)
- Audio duration distribution (when available)

LIST MUST NOT introduce a parallel telemetry schema.
LIST MUST use the canonical telemetry tables/steps defined in Document 06.

### 4.8 Non-Goals

LIST does not implement:
- Streaming ASR or incremental transcripts
- Speech synthesis (TTS)
- Speaker identification or diarization
- Content moderation or redaction
- Authentication / authorization (v1)

### 4.9 Failure Semantics

If LIST is unavailable or returns an error:
- The chat UI MUST remain functional.
- The client extension MUST preserve any existing draft input.
- The client extension MUST surface a user-visible error state.
- The client extension MUST NOT auto-retry without explicit user action.

[Back to top](#navigation)

---

## 5. Extension 12.2: Agent Memory Protocol (AMP)

### 5.1 Status and Purpose

**Status:** FOUNDATIONAL
**Implementation status:** NOT COMPLETE
**Audience:** Core maintainers, agent-runtime implementers, operators

Agent Memory Protocol (AMP) exposes bounded Memory Steward retrieval and admission operations to autonomous and semi-autonomous agents without creating a new deployable service and without granting agents unrestricted access to the Glass Pane control surface.

AMP exists to:
- Let an agent retrieve the same governed context used by the chat path without invoking an upstream chat completion.
- Let an agent submit structured execution outcomes for governed admission.
- Let agents publish reusable, versioned analysis artifacts with explicit provenance.
- Reuse the existing Router retrieval path, Steward admission path, and MCP runtime.
- Preserve existing Memory Steward authority boundaries.

> **Hard Invariant:** AMP MUST NOT introduce a separate retrieval service, admission service, or memory database.
>
> **Hard Invariant:** MCP handlers MUST NOT implement retrieval or admission policy independently of the Router and Steward application operations.

### 5.2 Architectural Position

AMP is an additive protocol surface over existing deployable units.

~~~mermaid
graph TD
    Chat[Chat Client]
    Agent[Agent Runtime]
    Router[Memory Router]
    Steward[Memory Steward]
    MCP[Memory Steward MCP]
    Builder[Upstream LLM]
    PG[(Postgres Canonical Store)]
    Q[(Qdrant Retrieval Index)]

    Chat -->|POST /v1/chat/completions| Router
    Agent -->|POST /v1/context/retrieve| Router
    Agent -->|memory.retrieve_context| MCP
    MCP -->|shared retrieval operation| Router

    Router -->|retrieve| PG
    Router -->|retrieve| Q
    Router -->|chat only| Builder

    Router -.->|ordinary chat admission| Steward
    Agent -->|POST /v1/agent/outcomes| Steward
    Agent -->|memory.submit_agent_outcome| MCP
    MCP -->|shared outcome operation| Steward

    Steward -->|canonical persistence| PG
    Steward -->|semantic index where applicable| Q
~~~

The existing deployable topology remains authoritative. AMP adds contracts; it does not add a service.

### 5.3 Shared Retrieval Operation

The Router MUST expose one internal structured retrieval operation used by both chat and agent paths.

The operation MUST perform the same policy-controlled retrieval steps as the chat path, including:
- Project resolution.
- Static-memory loading.
- Dynamic-memory retrieval.
- Reference-memory retrieval when allowed by operational mode.
- Reranking and token-budget enforcement.
- Selection accounting and telemetry.

The operation MUST return structured data before chat-specific rendering.

The chat path MUST:
1. Invoke the shared structured retrieval operation.
2. Render the result into the canonical envelope.
3. Inject the rendered envelope into the upstream LLM request.

The agent path MUST:
1. Invoke the same shared structured retrieval operation.
2. Return the structured retrieval result directly.
3. MUST NOT invoke the upstream Builder solely to serve retrieval.

The current Router implementation combines retrieval and canonical-envelope rendering in `_assemble_context()`. AMP implementation MUST split these responsibilities so retrieval has one canonical implementation and rendering is a chat-specific projection.

The structured result MUST preserve stable memory identifiers and source metadata for selected items so later outcome and feedback records can refer to the exact context supplied to the agent.

### 5.4 Router HTTP Contract

The Memory Router MUST expose:

`POST /v1/context/retrieve`

The request MUST carry enough information to resolve:
- `project_id` using the Router's canonical project-resolution mechanism.
- The agent query or objective, unless the request is an exact artifact-only lookup.
- Optional operational `mode`.
- Optional bounded recent dialogue or task context when required by the caller.
- Optional `artifact_selectors` for exact Postgres retrieval of versioned `agent_reference` artifacts. Selectors MAY constrain repository, revision, artifact type, schema version, producer type, or content hash.

The request MUST include at least one of: an agent query/objective, or one or more `artifact_selectors`. Exact artifact selection MUST NOT require embedding or semantic retrieval when the caller already knows artifact identity.

The response MUST include:
- `context_request_id`.
- `project_id`.
- Structured `policy_layer`.
- Structured `system_ontology`.
- Structured `retrieval_context`.
- Requested exact `agent_reference` artifacts, when selectors were supplied.
- Selected memory/reference identifiers and provenance metadata.
- Retrieval accounting sufficient for diagnostics and feedback.

The response MUST NOT be a pre-rendered chat prompt as its only representation.

### 5.5 Structured Agent Outcome Contract

The Memory Steward MUST expose:

`POST /v1/agent/outcomes`

Agent outcomes are structured execution evidence. They MUST NOT be represented as synthetic user/assistant chat transcripts.

The request MUST support:
- `outcome_id` or an equivalent idempotency key.
- `project_id`.
- `task_id` when available.
- `session_id` when available.
- `context_request_id` when the agent previously retrieved context.
- `objective`.
- `result`.
- `decisions`.
- `findings`.
- `verification`.
- `artifacts`.
- `repository_state` when the task is repository-scoped.
- Evidence/provenance references where available.
- Optional `admit_knowledge` (default `true`). Setting it to `false` is permitted for artifact-only/evidence-only submissions that must not invoke LLM durable-knowledge extraction. This flag MUST NOT cause any claim to bypass governed admission; it only suppresses creation of durable learned-memory candidates.

Repeated submission of the same idempotency identity with the same canonical request payload MUST NOT create duplicate durable memory or duplicate reusable artifacts. Reuse of an existing idempotency identity with a different canonical request payload MUST be rejected as a conflict.

The Steward MUST use an agent-outcome-specific normalizer/extractor. Ordinary chat admission and agent outcome admission MAY use different extraction prompts and policies, but they MUST converge on the same governed admission core for durable knowledge.

The audited admission model defined by Document 13, when enabled, governs the durable-knowledge decision stage. AMP does not create a parallel admission engine.

### 5.6 Reusable Agent and Analyzer Artifacts

`artifacts` MAY contain reusable structured material produced during agent execution or deterministic repository analysis.

Canonical examples include:
- Repository reconnaissance reports.
- AST or syntax-derived summaries.
- Symbol, dependency, call, and interface graphs.
- Generated dependency maps.
- Bounded investigation results.
- Reusable analysis artifacts.
- Generated summaries of large code surfaces.
- Product-model or objective-decomposition artifacts.

Reusable artifacts MUST carry sufficient identity and provenance to distinguish one repository/product state from another. `content_hash` is the lowercase SHA-256 of the UTF-8 encoded canonical JSON payload, with object keys sorted, no insignificant whitespace, and non-ASCII characters preserved. Repository-scoped artifacts SHOULD include:
- Repository identity.
- Revision or tree hash.
- Artifact type.
- Schema version.
- Producer type and producer version.
- Content hash.
- Provenance/evidence references.

AMP defines the durable class `agent_reference` for reusable agent- or tool-produced material that is not canonical static memory and is not ordinary conversational dynamic memory.

`agent_reference` is distinct from the canonical `reference_memory` defined by Document 03. Agent- or tool-produced material MUST NOT enter the `reference_memory` namespace merely because it is reusable. Promotion into canonical Reference Memory requires the explicit curated/versioned ingestion semantics of Document 03.

Producer type MUST distinguish at least:
- `agent` — material inferred or synthesized by an agent/LLM.
- `analyzer` — material produced by a deterministic analyzer.
- `tool` — material produced by another deterministic tool or pipeline.

Deterministic analyzer/tool artifacts MAY be persisted without LLM admission when their identity, schema, producer, revision, and content hash are validated deterministically. Such artifacts MUST remain reference/evidence material and MUST NOT be silently promoted to durable learned facts.

Agent-inferred claims and decisions that are candidates for durable knowledge MUST pass the governed admission path.

Postgres MUST remain the canonical store for structured artifact identity, provenance, and payload. Qdrant MAY index semantic projections of an artifact when semantic discovery is useful; Qdrant MUST NOT become the sole canonical representation of the structured artifact. Exact retrieval of a known artifact MUST use the shared Router retrieval operation with `artifact_selectors` rather than requiring a semantic Qdrant round-trip.

### 5.7 Shared Admission Core

Ordinary chat and agent outcomes have different input contracts but share the same durable-memory control plane.

Authoritative flow:

~~~text
chat turn -> chat normalizer/extractor -----------+
                                                  |
agent outcome -> agent normalizer/extractor ------+--> candidate normalization
                                                        -> contradiction/dedup checks
                                                        -> confidence/durability policy
                                                        -> admit/reject/merge/supersede
~~~

The agent path MUST NOT bypass deterministic gates, contradiction handling, audit policy, or provenance requirements applicable to durable memory.

### 5.8 MCP Surface

The existing Memory Steward MCP deployment MUST remain the MCP transport surface. AMP MUST add thin MCP adapters over the same application operations exposed through HTTP.

Canonical agent operations:
- `memory.retrieve_context` -> shared Router retrieval operation.
- `memory.submit_agent_outcome` -> shared Steward agent-outcome operation.

AMP SHOULD also support:
- `memory.submit_context_feedback` -> records retrieval-quality feedback without directly modifying memory.

Context feedback MAY include:
- `context_request_id`.
- `used_memory_ids`.
- `irrelevant_memory_ids`.
- A bounded description of missing context.

Feedback MUST NOT directly create, delete, merge, or supersede memory.

### 5.9 Capability Boundaries

The Glass Pane MCP contains operator and destructive capabilities. Connecting an agent to the MCP transport MUST NOT imply access to every registered tool.

The authorization contract MUST distinguish at least these capability classes:

| Capability | Intended access | Representative operations |
|---|---|---|
| `agent-read` | Ordinary agents | `memory.retrieve_context`, `get_project_memory`, `inspect_reference`, `list_static`, `simulate_retrieval`, explanation/read-only repository tools |
| `agent-write` | Agents allowed to report outcomes | All `agent-read` operations plus `memory.submit_agent_outcome` and `memory.submit_context_feedback` |
| `memory-curator` | Curators/controlled ingestion jobs | Static-memory maintenance and reference ingestion operations |
| `memory-admin` | Operators only | Destructive purge/delete, repository connection administration, runtime/stability controls, and unrestricted repository write operations |

Deployments MAY implement finer-grained capabilities, but MUST default-deny tools not explicitly granted to an agent identity or role.

Ordinary agents MUST NOT automatically receive authority to:
- Delete or disable static memory.
- Purge reference namespaces.
- Add or remove repository connections.
- Change global token budgets or operating modes.
- Reconfigure hysteresis or cache control.
- Write arbitrary repository files through the Memory Steward control plane.

#### 5.9.1 Current Glass Pane Tool Inventory

At the time AMP is specified, the existing MCP implementation exposes these tool groups:

- **Content:** `ingest_reference_url`, `ingest_reference_text`, `list_reference_namespaces`, `inspect_reference`, `purge_reference`, `list_static`, `create_static`, `update_static`, `toggle_static`, `delete_static`, `control_cache`.
- **Git:** `repo_add`, `repo_list`, `repo_remove`, `repo_test`, `git_list_repos`, `git_ingest_repo`, `git_ingest_file`, `git_write_file`.
- **Diagnostics:** `get_system_health`, `explain_decision`, `explain_last_decision`, `get_metrics`, `get_qdrant_stats`, `get_project_memory`, `simulate_retrieval`, `diagnostics.logs.read`.
- **Stability:** `set_token_budget`, `force_mode`, `configure_hysteresis`, `get_stability_config`.

This inventory does not grant agent authority. Each operation remains subject to the capability policy above. Tool additions MUST be classified before they are exposed to agent identities.

### 5.10 Retrieval-Lane Isolation Requirement

Project-scoped Qdrant retrieval MUST explicitly select the intended memory type.

Before AMP introduces additional project-scoped vectorized memory classes, the Router dynamic-memory retrieval path MUST filter on both:
- `project_id`.
- `memory_type = dynamic_memory`.

A `project_id` filter alone is insufficient once `agent_reference`, failure memory, or other project-scoped classes share a collection.

> **Hard Invariant:** Adding a new memory class MUST NOT make it silently eligible for an existing retrieval lane.

### 5.11 Correlation, Provenance, and Idempotency

AMP MUST preserve correlation between what an agent knew and what it later reported.

At minimum:
- Every retrieval MUST receive a unique `context_request_id`.
- Agent outcomes SHOULD carry the originating `context_request_id` when applicable.
- `task_id` and `session_id` SHOULD be preserved when provided by the agent runtime.
- Durable claims MUST preserve evidence/provenance references when available.
- Outcome submission MUST be idempotent.

These identifiers are diagnostic and governance metadata; they MUST NOT be treated as evidence that an agent conclusion is correct.

### 5.12 Failure Semantics

If agent retrieval fails:
- The Router MUST return an explicit failure response.
- The Router MUST NOT silently substitute unrelated or cross-project context.
- The caller MAY continue without Memory Steward only if the caller's own policy permits it.

If agent outcome submission fails:
- The Steward MUST NOT partially create duplicate durable records on retry.
- A retry using the same idempotency identity MUST be safe.

If capability enforcement is unavailable or ambiguous:
- Agent access to privileged Glass Pane tools MUST fail closed.

### 5.13 Telemetry Expectations

AMP telemetry MUST align with Document 06 and reuse existing Router/Steward telemetry planes where possible.

AMP MUST record, at minimum:
- Agent retrieval request identity and project.
- Retrieval candidate/selection counts and token accounting.
- Outcome submission identity and admission result.
- Correlation identifiers when supplied.
- Artifact persistence result for reusable artifacts.
- Authorization denials for MCP agent operations.

AMP MUST NOT introduce an independent telemetry schema solely for MCP transport.

### 5.14 Non-Goals

AMP does not:
- Create a new deployable service.
- Give agents direct Postgres or Qdrant access.
- Make the MCP server a second implementation of Router or Steward logic.
- Treat agent statements as trusted facts merely because they are structured.
- Grant ordinary agents unrestricted Glass Pane administration authority.
- Require semantic vector indexing for exact-key structured artifacts.
- Redefine static, dynamic, or canonical reference authority.

[Back to top](#navigation)

---

## 6. Closing Statement

This document establishes a stable extension surface that preserves the authority and invariants of the foundational specification set (Documents 00–11). Extensions defined here are additive, optional, and contract-driven. LIST defines the input-plane extension pattern. AMP defines the bounded agent-facing memory protocol while preserving Router, Steward, storage, and MCP authority boundaries.

---

**END OF DOCUMENT 12**
