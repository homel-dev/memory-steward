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
- `ref_ingest_status`
- `ref_ingest_jobs`
- `ref_ingest_cancel`
- `ref_ingest_retry`
- `ref_list`
- `ref_inspect`
- `ref_purge`

URL ingestion is durable and asynchronous. `ref_ingest_url` inserts a `reference_ingestion_jobs` row and returns its UUID immediately; `reference-ingest-worker` performs bounded fetch/chunk/embed/upsert work. `ref_ingest_text` and Git ingestion remain synchronous but share the same bounded batching implementation.

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

## 8. Canonical Reference Data Model

Reference Memory is identified semantically and operationally by `memory_type=reference_memory` in Qdrant payloads. Metadata provides exact narrowing and provenance. Current Router filter fields are whitelisted to prevent arbitrary payload-path filtering from becoming an accidental public query language.

| Filter key | Meaning | Matching rule |
| --- | --- | --- |
| product | Canonical product/system family | Exact match when explicitly provided |
| version | Documentation/product version | Exact match when explicitly provided |
| scope | Bounded corpus area such as pcb/api/cli | Exact match when explicitly provided |
| provider | Origin/provider classification | Exact match when explicitly provided |
| source | Source identifier/URL/repository path depending on ingestion path | Exact match when explicitly provided |

No additional narrowing is synthesized when the caller omits `reference_filters`. The only unconditional Qdrant condition for this lane is the memory-type discriminator.

## 9. Retrieval Filter Construction

~~~text
must = [memory_type == "reference_memory"]
for each supplied, whitelisted reference filter:
    must += [metadata.<field> == supplied value]
query Qdrant using query embedding + must filters
~~~

Unknown filter names are rejected at Pydantic request validation. This keeps the v1 filter surface intentionally small and auditable.

## 10. Ingestion Paths

| Path | Initiator | Input | Result |
| --- | --- | --- | --- |
| ref_ingest_url | Operator/MCP client | URL + metadata | Durable Postgres job; worker performs bounded fetch, chunking, embedding, Qdrant upsert, and provenance |
| ref_ingest_text | Operator/MCP client | Text + metadata | Chunking/embedding and Reference Memory upsert |
| git_ingest_repo | Operator/MCP Git plane | Registered repository selection | Repository content ingested into reference lane |
| git_ingest_file | Operator/MCP Git plane | One repository file | Selected file ingested into reference lane |

Reference ingestion is explicit. Ordinary chat admission does not promote conversational text into Reference Memory.

## 11. Durable URL Ingestion Lifecycle

The queue is canonical Postgres state in `reference_ingestion_jobs`. Workers claim one queued row using `FOR UPDATE SKIP LOCKED`, increment `attempt_count`, and fence every progress/final update by `(job_id, worker_id, attempt_count)`. A stale lease is requeued; if cancellation was already requested, lease expiry finalizes it as cancelled instead. Application failures are left `failed` and are retried only by explicit `ref_ingest_retry`.

The worker fetches at most 64 MiB of decompressed response data, then processes reference chunks in batches of 8. Each batch is embedded independently and synchronously upserted to Qdrant with `wait=true`. Deterministic point ids make partial work safe to retry; if a job fails after an earlier Qdrant batch, those already-written chunks remain visible until the job is retried to completion or the namespace is explicitly purged. Successful job completion and insertion of the immutable `reference_ingestion` provenance row use one Postgres transaction.

The embeddings service independently enforces its own limits: at most 64 texts per request, FastEmbed batch size 16, ONNX/native thread bounds, and a Kubernetes CPU limit. These service-side limits are a second barrier if another caller bypasses the reference worker.

## 12. Search and Get APIs

### 12.1 `POST /v1/reference/search`

Inputs:

- non-empty `query`;
- optional `reference_filters` dictionary using only the v1 whitelist;
- `limit` from 1 through 50.

The Router embeds the query, searches the reference lane, and returns normalized candidate payloads. Project identity is still resolved for request context/telemetry even though canonical reference documents are not learned project facts.

### 12.2 `GET /v1/reference/{chunk_id}`

Fetches one reference chunk by identifier. Missing chunks return HTTP 404 rather than an empty success object.

### 12.3 `POST /v1/context/retrieve`

Structured agent retrieval can combine reference material with static, dynamic, and explicitly selected deterministic artifacts. `reference_filters` are passed through unchanged to the same reference retrieval implementation.

## 13. MCP Reference Operations

| Tool | Class | Operational intent |
| --- | --- | --- |
| ref_ingest_url | Mutating | Queue durable URL ingestion and return the job id |
| ref_ingest_text | Mutating | Ingest operator-provided reference text |
| ref_ingest_status | Read-only | Inspect one queued/running/final URL-ingestion job |
| ref_ingest_jobs | Read-only | List recent URL-ingestion jobs |
| ref_ingest_cancel | Mutating | Cancel queued work or request cancellation between bounded batches |
| ref_ingest_retry | Mutating | Explicitly retry failed/cancelled work |
| ref_list | Read-only | List reference ingestion namespaces/events |
| ref_inspect | Read-only | Inspect stored reference chunks by metadata |
| ref_purge | Destructive | Delete reference data for an explicit selection |
| git_ingest_repo | Mutating | Ingest repository content into reference memory |
| git_ingest_file | Mutating | Ingest one repository file into reference memory |
| memory.reference.search | Read-only | Adapter to Router reference search |
| memory.reference.get | Read-only | Adapter to Router reference get |

Operators SHOULD use live tool discovery before automation because FastMCP is the schema authority for exact argument names.

## 14. Reference Eligibility vs Filtering

Two independent gates exist:

1. **eligibility**: whether the reference lane participates in ordinary/structured context assembly for the supplied mode and global toggle;
2. **filtering**: which reference documents are eligible after the lane is active.

Do not encode product/topic policy in mode. A KiCad request can use `mode=engineering` and `reference_filters={product:kicad, version:9.0}`; those fields solve different problems.

## 15. Reference Memory vs Agent Artifacts

| Property | Reference Memory | agent_reference |
| --- | --- | --- |
| Source | Explicit external/operator ingestion | Structured agent outcome artifact |
| Primary store/index | Qdrant semantic lane + ingestion metadata | Postgres exact structured rows |
| Selection | Semantic query + optional exact metadata filters | Explicit ArtifactSelector fields |
| Authority intent | Authoritative/source material | Reusable deterministic evidence/output |
| Automatic promotion | No | No promotion to Reference Memory |
| Typical example | Product manual/API documentation | Generated pin map, test result, machine-readable analysis artifact |

## 16. Provenance and Versioning Guidance

Reference metadata SHOULD be specific enough to prevent silent cross-version blending. When the source has a meaningful version, store it explicitly and have engineering agents request that version. Source and provider fields SHOULD remain stable identifiers rather than free-form commentary.

When replacing a corpus version, prefer explicit ingestion of the new version and an explicit purge/retention decision for the old version. Do not rely on semantic similarity to distinguish incompatible versions.

## 17. Failure and Safety Matrix

| Condition | Expected behavior |
| --- | --- |
| Unknown reference filter key | Request validation error; do not silently ignore |
| No filters | Search all reference_memory chunks eligible for the lane |
| No matching chunks | Return empty candidate set, not dynamic-memory fallback masquerading as reference |
| Missing chunk id | HTTP 404 |
| Qdrant unavailable | Reference semantic search fails and should be visible in request diagnostics |
| Embedding service unavailable | Reference query cannot be embedded; fail rather than use an unrelated lexical approximation |
| Purge requested | Require explicit operator invocation; Task shortcut prompts |
| URL ingestion targets sensitive/internal network | Current implementation needs egress/SSRF hardening; treat this as an operational security concern |

## 18. Verification Cases

Tests and operator checks SHOULD cover:

1. unconditional `memory_type=reference_memory` filter;
2. each whitelisted exact metadata filter independently;
3. multiple filters combined as AND conditions;
4. no-filter behavior without synthetic narrowing;
5. rejection of unknown filter names;
6. limit bounds;
7. search/get consistency;
8. context-retrieve pass-through of filters;
9. separation from dynamic memory and agent artifacts;
10. explicit purge behavior.

---

## 8. Closing Statement

Reference Memory is an explicit, versioned, operator-managed retrieval corpus. Runtime retrieval MUST remain read-only and MUST apply only the exact metadata narrowing requested by the caller.

[Back to top](#navigation)

---

**END OF DOCUMENT 03**

## Appendix A. Request Schemas Relevant to Reference Retrieval

### ArtifactSelector

| Field | Type | Constraint/default |
| --- | --- | --- |
| artifact_type | str | Field(..., min_length=1, max_length=128) |
| repository | Optional[str] | Field(default=None, max_length=1024) |
| revision | Optional[str] | Field(default=None, max_length=256) |
| schema_version | Optional[str] | Field(default=None, max_length=64) |
| producer_type | Optional[str] | Field(default=None, max_length=32) |
| content_hash | Optional[str] | Field(default=None, max_length=64) |
### ContextRetrieveRequest

| Field | Type | Constraint/default |
| --- | --- | --- |
| query | Optional[str] | Field(default=None, min_length=1) |
| mode | Optional[str] | None |
| model | Optional[str] | None |
| recent_messages | List[ChatMessage] | Field(default_factory=list) |
| artifact_selectors | List[ArtifactSelector] | Field(default_factory=list, max_length=32) |
| reference_filters | dict[str, str] \| None | None |
### ReferenceSearchRequest

| Field | Type | Constraint/default |
| --- | --- | --- |
| query | str | Field(..., min_length=1) |
| reference_filters | dict[str, str] \| None | None |
| limit | int | Field(default=8, ge=1, le=50) |

## Appendix B. Reference Lifecycle

### B.1 Create/ingest

1. operator chooses an authoritative source and metadata;
2. MCP content/Git tool validates requested operation;
3. source text is fetched/read;
4. content is chunked;
5. chunks are embedded;
6. Qdrant points are written with `memory_type=reference_memory` and metadata;
7. ingestion metadata is persisted for inspection/lifecycle operations;
8. operator verifies with list/inspect/search.

### B.2 Query

1. caller supplies query;
2. Router embeds query once;
3. Router constructs `must` with the unconditional memory type discriminator;
4. each explicitly supplied whitelisted field adds an exact match;
5. Qdrant returns bounded semantic candidates;
6. candidates are normalized and optionally stitched into context under budget.

### B.3 Purge

Purge is an explicit lifecycle operation. The operator should select the narrowest product/version/scope target that matches the intended corpus. The Task wrapper is designed to make the destructive nature visible.

## Appendix C. Corpus Design Guidance

Reference corpora are more reliable when metadata has stable semantics:

- `product`: canonical lowercase product family, e.g. `kicad`;
- `version`: source version meaningful to compatibility, e.g. `9.0`;
- `scope`: bounded area such as `pcb`, `schematic`, `cli`, `api`;
- `provider`: vendor/source family when multiple providers exist;
- `source`: stable source identity such as URL or repository path.

Do not put conversational confidence, user preference, or transient request state into these fields.

## Appendix D. Cross-Version Safety

A semantic query can easily find lexically similar material from an incompatible version. For engineering agents, version filtering is therefore a correctness tool, not merely an optimization. When version is known, agents should request it explicitly. When version is unknown, the system should return identifiable provenance so the caller can decide whether a result is acceptable.

## Appendix E. Reference Candidate Review Checklist

For a returned candidate, an agent/operator should be able to answer:

1. What is the chunk identifier?
2. Is `memory_type` reference memory?
3. What product/version/scope produced it?
4. What source/provider produced it?
5. Was the query narrowed explicitly or unfiltered?
6. Is the chunk content intact enough to support the engineering claim?
7. Is a direct source retrieval needed before making a high-impact change?
8. Could an older corpus version still exist and contaminate unfiltered search?

## Appendix F. Security Notes for URL Ingestion

Server-side URL fetching is operationally powerful. In untrusted environments, the deployment should enforce outbound network restrictions, URL allowlists or equivalent policy, redirect limits, size/time limits, and content-type handling. This repository documentation treats those as hardening requirements rather than claiming they are already a complete SSRF defense.

## Appendix G. Reference vs Other Lanes: Decision Examples

| Information | Correct lane | Reason |
| --- | --- | --- |
| KiCad 9 official file-format documentation | Reference Memory | Authoritative external source |
| User prefers metric units | Dynamic memory | Learned user/project fact |
| Project rule "do not access old/" | Static or project policy memory | Explicit instruction/invariant |
| Agent-generated netlist analysis JSON | agent_reference | Deterministic reusable artifact |
| Request latency | telemetry | Operational evidence |
| Proposed admission-gate decision | admission-control proposal tables only when runtime implemented | Not a reference source |

## Appendix H. Reference API Error Semantics

- invalid filter name: validation error;
- empty search query: validation error;
- invalid limit (<1 or >50): validation error;
- missing chunk ID on get: HTTP 404;
- dependency failure during semantic query: request failure surfaced through Router error handling/telemetry;
- zero matching candidates: valid empty result, not an error;
- no filters: valid broad reference query inside lane eligibility.
