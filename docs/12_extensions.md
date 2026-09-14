# EXTENSIONS
## LIST and Agent Memory Protocol
### Foundational Engineering Specification (Document 12 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 11 (Design Principles)](11_design_principles.md) | [Next: Document 13 (Admission Control Proposal)](13_admission_control.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. LIST — Local Input Speech Transcriber](#1-list-local-input-speech-transcriber)
- [2. Agent Memory Protocol (AMP)](#2-agent-memory-protocol-amp)
- [3. `agent_reference`](#3-agentreference)
- [4. Extension Rule](#4-extension-rule)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PARTIAL
**Audience:** Maintainers, extension developers, agent-runtime integrators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

[Back to top](#navigation)

---

## 1. LIST — Local Input Speech Transcriber

`memory-steward-list` is an optional FastAPI service.

Implemented endpoints:

- `GET /healthz`
- `POST /v1/audio/transcriptions`
- `POST /v1/list/transcribe`

Transcription accepts one multipart `file` and returns JSON containing `text`.

`POST /v1/list/translate` exists but currently returns HTTP 501; translation is **not implemented**.

LIST does not own memory admission or Builder inference.

[Back to top](#navigation)

---

## 2. Agent Memory Protocol (AMP)

AMP reuses existing Router, Steward, and MCP deployables; it is not a separate service.

### 2.1 Router Operations

Implemented Router operations include:

- `POST /v1/context/retrieve`
- `POST /v1/reference/search`
- `GET /v1/reference/{chunk_id}`

Structured context retrieval can return static/dynamic/reference context and exact `agent_reference` artifacts without a Builder call.

### 2.2 Steward Operations

Implemented Steward operations include:

- `POST /v1/agent/outcomes`
- `POST /v1/context/feedback`

Agent outcomes support idempotency, knowledge extraction, artifact validation/persistence, and provenance fields represented by the current Pydantic models.

### 2.3 MCP Adapters

Implemented MCP tools include:

- `memory.retrieve_context`
- `memory.reference.search`
- `memory.reference.get`
- `memory.submit_agent_outcome`
- `memory.submit_context_feedback`

These tools are transport adapters. Retrieval remains owned by Router and outcome/feedback persistence remains owned by Steward.

[Back to top](#navigation)

---

## 3. `agent_reference`

`agent_reference` stores reusable structured artifacts produced by agents/analyzers/tools. It is distinct from canonical `reference_memory`. Exact artifact retrieval uses Postgres selectors; semantic Qdrant indexing is optional rather than required for identity-preserving retrieval.

[Back to top](#navigation)

---

## 4. Extension Rule

An extension is current only to the extent represented by code/tests. Proposed admission/auditor behavior in Document 13 is not activated merely because AMP can submit outcomes.

[Back to top](#navigation)

---

## 5. Closing Statement

LIST and AMP are additive surfaces with different implementation maturity. Extension documentation MUST state which endpoints and semantics exist now and which remain incomplete.

[Back to top](#navigation)

---

**END OF DOCUMENT 12**
