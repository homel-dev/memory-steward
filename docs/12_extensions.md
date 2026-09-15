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

## 5. LIST Runtime Contract in Detail

LIST is deliberately narrow. It accepts an uploaded audio file and returns transcribed text. It does not receive chat history, prompt envelopes, memory payloads, Postgres credentials, or Qdrant access as part of its normal design.

| Route | Status | Behavior |
| --- | --- | --- |
| GET /healthz | Implemented | Liveness response |
| POST /v1/list/transcribe | Implemented | Multipart audio -> text + internal duration accounting |
| POST /v1/audio/transcriptions | Implemented alias | OpenAI-style transcription path alias |
| POST /v1/list/translate | Stub | Returns HTTP 501; translation is not implemented |

The model is loaded lazily/singleton-style through `TranscriptionService`. Startup attempts pre-load; a failure is logged and later requests can retry. The checked-in manifest defaults to CPU with `COMPUTE_TYPE=int8`; commented GPU settings are examples, not active allocation.

## 6. Agent Memory Protocol Request Types

The Router structured retrieval request supports:

- optional semantic `query`;
- optional `mode`;
- optional model hint;
- bounded recent messages for dialogue state;
- up to 32 artifact selectors;
- optional exact `reference_filters`.

At least a query or artifact selector must be present.

Artifact selectors can constrain fields including artifact type, repository, revision, schema version, producer type, and content hash. This lane is deterministic and exact rather than semantic Reference Memory.

## 7. Agent Outcome Contract

Structured agent outcomes provide:

- project/outcome/task/session identities;
- optional link to `context_request_id`;
- objective/result/evidence/verification context;
- zero or more reusable artifacts;
- an `admit_knowledge` switch controlling optional learned-fragment extraction.

Outcome idempotency is keyed by `(project_id, outcome_id)` plus a canonical request hash. A replay of the same payload returns the completed stored result. Reuse of the same ID with a different payload is rejected with HTTP 409.

## 8. Agent Artifact Persistence

| Property | Behavior |
| --- | --- |
| Persistence timing | Before optional knowledge extraction, so deterministic output can survive extraction failure |
| Primary table | agent_reference |
| Identity | Derived artifact key/content hash plus project/outcome provenance |
| Retrieval | Explicit ArtifactSelector matching in Router structured context |
| Authority | Reusable evidence/reference lane, lower/different authority than canonical external Reference Memory |
| Promotion | No implicit promotion to Reference Memory |

## 9. Context Feedback

Agents may report:

- memory IDs that were used;
- memory IDs that were irrelevant;
- missing context description;
- task/session identity.

Feedback is stored in `context_feedback` and summarized in telemetry. The current runtime does not automatically retrain or rewrite memory from this feedback; it provides an evidence loop for later analysis and policy evolution.

## 10. MCP AMP Adapters

| Tool | Backend operation |
| --- | --- |
| memory.retrieve_context | Adapter to Router /v1/context/retrieve |
| memory.reference.search | Adapter to Router reference search |
| memory.reference.get | Adapter to Router reference get |
| memory.submit_agent_outcome | Adapter to Steward structured outcome admission |
| memory.submit_context_feedback | Adapter to Steward context feedback |

The adapters preserve Router/Steward ownership. MCP does not reimplement retrieval or admission policy.

## 11. Terminal TUI Extension

`components/steward_tui` is an operator extension built with Textual. It discovers MCP tools live and generates scalar forms from JSON Schema. This keeps the UI synchronized with the server contract and avoids a hand-maintained duplicate command vocabulary.

The TUI default URL is loopback MCP and can be overridden with `STEWARD_MCP_URL`.

## 12. Extension Isolation Rules

Any new extension MUST answer:

1. Does it receive raw conversation content?
2. Does it need Postgres/Qdrant access?
3. Can it mutate durable memory?
4. Is it a client of an existing authority or a new authority?
5. Can its failure block chat?
6. Does it add a public network surface?
7. What schema/tool/API is the source of truth?
8. What tests prove it cannot cross intended boundaries?

Extensions should prefer existing Router/Steward/MCP contracts over direct database coupling.

## 13. AMP Verification Scenarios

- context retrieval with query only;
- context retrieval with artifact selectors only;
- combined semantic + exact artifact retrieval;
- reference filters passed through correctly;
- outcome first submission;
- exact outcome replay;
- conflicting outcome ID/payload -> 409;
- artifact persisted when `admit_knowledge=false`;
- optional learned fragments admitted when enabled;
- feedback persistence and telemetry;
- missing selected artifact produces bounded empty lane rather than accidental semantic substitution.

---

## 5. Closing Statement

LIST and AMP are additive surfaces with different implementation maturity. Extension documentation MUST state which endpoints and semantics exist now and which remain incomplete.

[Back to top](#navigation)

---

**END OF DOCUMENT 12**

## Appendix A. AMP and Extension Schema Reference

### `ArtifactSelector`

| Field | Type | Constraint/default |
| --- | --- | --- |
| artifact_type | str | Field(..., min_length=1, max_length=128) |
| repository | Optional[str] | Field(default=None, max_length=1024) |
| revision | Optional[str] | Field(default=None, max_length=256) |
| schema_version | Optional[str] | Field(default=None, max_length=64) |
| producer_type | Optional[str] | Field(default=None, max_length=32) |
| content_hash | Optional[str] | Field(default=None, max_length=64) |
### `ContextRetrieveRequest`

| Field | Type | Constraint/default |
| --- | --- | --- |
| query | Optional[str] | Field(default=None, min_length=1) |
| mode | Optional[str] | None |
| model | Optional[str] | None |
| recent_messages | List[ChatMessage] | Field(default_factory=list) |
| artifact_selectors | List[ArtifactSelector] | Field(default_factory=list, max_length=32) |
| reference_filters | dict[str, str] \| None | None |
### `ReferenceSearchRequest`

| Field | Type | Constraint/default |
| --- | --- | --- |
| query | str | Field(..., min_length=1) |
| reference_filters | dict[str, str] \| None | None |
| limit | int | Field(default=8, ge=1, le=50) |
### `AdmitTurnRequest`

| Field | Type | Constraint/default |
| --- | --- | --- |
| request_id | str | Field(..., min_length=1) |
| project_id | str | Field(..., min_length=1) |
| scope | Optional[str] | None |
| messages | List[Dict[str, str]] | required |
| evidence_type | Optional[str] | None |
| evidence_ref | Optional[str] | None |
| max_fragments | int | Field(default=12, ge=1, le=64) |
### `AgentArtifact`

| Field | Type | Constraint/default |
| --- | --- | --- |
| artifact_type | str | Field(..., min_length=1, max_length=128) |
| schema_version | str | Field(..., min_length=1, max_length=64) |
| producer_type | Literal['agent', 'analyzer', 'tool'] | required |
| producer_version | str | Field(..., min_length=1, max_length=128) |
| content_hash | str | Field(..., min_length=64, max_length=64) |
| payload | Any | required |
| repository | Optional[str] | Field(default=None, max_length=1024) |
| revision | Optional[str] | Field(default=None, max_length=256) |
| producer_name | Optional[str] | Field(default=None, max_length=256) |
| provenance | List[Any] | Field(default_factory=list) |
### `AgentOutcomeRequest`

| Field | Type | Constraint/default |
| --- | --- | --- |
| outcome_id | str | Field(..., min_length=1, max_length=256) |
| project_id | str | Field(..., min_length=1, max_length=256) |
| task_id | Optional[str] | Field(default=None, max_length=256) |
| session_id | Optional[str] | Field(default=None, max_length=256) |
| context_request_id | Optional[str] | Field(default=None, max_length=256) |
| objective | str | Field(..., min_length=1) |
| result | Any | required |
| decisions | List[Any] | Field(default_factory=list) |
| findings | List[Any] | Field(default_factory=list) |
| verification | Dict[str, Any] | Field(default_factory=dict) |
| artifacts | List[AgentArtifact] | Field(default_factory=list) |
| repository_state | Dict[str, Any] | Field(default_factory=dict) |
| evidence | List[Any] | Field(default_factory=list) |
| scope | Optional[str] | None |
| admit_knowledge | bool | True |
| max_fragments | int | Field(default=12, ge=1, le=64) |
### `ContextFeedbackRequest`

| Field | Type | Constraint/default |
| --- | --- | --- |
| project_id | str | Field(..., min_length=1, max_length=256) |
| context_request_id | str | Field(..., min_length=1, max_length=256) |
| feedback_id | Optional[str] | Field(default=None, max_length=256) |
| task_id | Optional[str] | Field(default=None, max_length=256) |
| session_id | Optional[str] | Field(default=None, max_length=256) |
| used_memory_ids | List[str] | Field(default_factory=list) |
| irrelevant_memory_ids | List[str] | Field(default_factory=list) |
| missing_context | Optional[str] | Field(default=None, max_length=4000) |

## Appendix B. Artifact Integrity Rules

`AgentArtifact.content_hash` is fixed at 64 characters by the request model. Steward computes the canonical payload hash and verifies it against the supplied content hash before persistence. This prevents an artifact identity from claiming bytes different from its payload representation.

Artifact metadata separates:

- artifact type;
- schema version;
- producer type/name/version;
- repository/revision provenance;
- payload;
- provenance chain;
- source outcome identity.

This detail matters for agents that consume generated engineering artifacts across runs.

## Appendix C. Outcome Idempotency State

A structured outcome can be in processing, complete, or failed persistence state in `agent_outcome_submission`. The request hash binds an `outcome_id` to a canonical payload. This design supports retry after network uncertainty without allowing the same identity to mean two different outcomes.

Typical retry cases:

1. caller times out after server completed -> replay returns stored result;
2. caller repeats same payload -> idempotent replay;
3. caller reuses ID with modified payload -> 409 conflict;
4. server failed before completion -> state can be updated/retried according to current preparation logic;
5. deterministic artifacts may already exist under uniqueness constraints and should resolve to existing IDs rather than duplicate meaning.

## Appendix D. Context Feedback Semantics

`used_memory_ids` and `irrelevant_memory_ids` are explicit observations from the consuming agent. `missing_context` is free text bounded by the request schema. The current runtime stores feedback; it does not automatically delete or rewrite memory based on a single feedback event.

A future learning loop must define aggregation thresholds, adversarial-input handling, and review policy before using feedback as mutation authority.

## Appendix E. LIST Resource Model

LIST's model cache PVC is a performance/resource concern, not memory state. Recreating LIST should not mutate Postgres/Qdrant. A failed transcription should return an application error and record transcription telemetry without creating a partial memory write.

## Appendix F. TUI Schema Adaptation Rules

The TUI converts tool JSON Schema into fields at runtime:

- `type=boolean` -> `Switch`;
- integer/number/string -> `Input` with coercion;
- required field empty -> local `ValueError`;
- optional empty -> omitted argument;
- `anyOf` is scanned for a supported scalar type;
- unsupported/complex field forms conservatively fall back to string representation.

This is intentionally thin client behavior. Validation and business rules remain server-side.

## Appendix G. Extension Threat/Failure Model

| Extension boundary | Risk | Required mitigation/documentation |
| --- | --- | --- |
| LIST file upload | oversized/hostile media | request/resource limits and decoder isolation as deployment hardening |
| MCP URL ingestion | SSRF/egress abuse | outbound restrictions/allowlist/time/size controls |
| Git plane | external repository mutation | explicit credentials/authorization and operator intent |
| TUI | accidental destructive call | visible tool names/forms; server remains authority; consider confirmation UX for destructive tools |
| AMP outcome | ID collision/replay | request hash + 409 conflict semantics |
| Agent artifact | forged hash/provenance | canonical payload hash verification and provenance fields |
| Feedback | malicious quality signal | storage only today; no automatic mutation loop |

## Appendix H. End-to-End Agent Example

~~~text
1. agent asks memory.retrieve_context(query, selectors, reference_filters)
2. MCP adapter calls Router /v1/context/retrieve
3. Router returns context_request_id + structured lanes + accounting
4. agent performs engineering work
5. agent submits memory.submit_agent_outcome with outcome_id and artifacts
6. MCP adapter calls Steward /v1/agent/outcomes
7. Steward reserves idempotency, verifies/persists artifacts
8. optional admit_knowledge extracts durable fragments
9. agent optionally submits memory.submit_context_feedback using context_request_id
10. operator can correlate retrieval, outcome, and feedback in diagnostics
~~~

## Appendix I. Extension Acceptance Checklist

- API/tool schema is versionable and documented.
- Write authority is explicit.
- Retry/idempotency semantics are explicit where mutation occurs.
- Dependencies and failure isolation are documented.
- No new public network exposure appears accidentally.
- Secrets are injected rather than committed.
- Telemetry is sufficient to debug failures.
- Component tests cover invalid/negative inputs.
- Root/runtime docs are updated.
- Proposed automation is not described as active before code exists.
