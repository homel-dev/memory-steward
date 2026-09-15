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

## 5. Retrieval Pipeline in Detail

The current optimization strategy favors bounded work over speculative complexity. The Router retrieval path can be reasoned about as a finite sequence:

1. load active static rows from Postgres;
2. embed the query once;
3. prefetch bounded dense dynamic candidates (`DENSE_PREFETCH`);
4. optionally query bounded Reference Memory candidates;
5. load exact deterministic artifacts only for supplied selectors;
6. apply MMR to dynamic candidates where appropriate;
7. stitch lanes under `MAX_CONTEXT_TOKENS`;
8. emit accounting for candidates, selections, token estimates, and drops.

The pipeline does not maintain an autonomous long-lived vector cache or a hidden relevance model.

## 6. Token-Budget Model

| Budget/constant | Current role |
| --- | --- |
| MAX_CONTEXT_TOKENS | Upper bound for retrieved/system context; environment default 8192, checked-in manifest 128000, live runtime_config override supported |
| MAX_TOTAL_TOKENS | Prompt-input planning ceiling used to derive history allowance; code default 16384, manifest 262144 |
| 200 token reserve | Small fixed planning reserve in chat history calculation |
| user_text_tokens | Counted before history pruning |
| context token estimates | Tracked by lane for retrieval accounting |

History allowance is computed before Builder dispatch. Older history is traversed from newest to oldest and the Router stops adding history once the allowance would be exceeded. The final upstream payload uses that pruned history.

## 7. Dense Prefetch and Final Selection

`DENSE_PREFETCH` controls how many semantic candidates are requested before final selection. `TOP_K` bounds the final selected dynamic set. These are separate so MMR can trade relevance against redundancy inside a bounded candidate pool.

`MMR_LAMBDA` defaults to `0.5`, balancing query relevance and diversity. Changing it is a ranking-policy change and requires retrieval regression tests rather than only performance benchmarking.

## 8. Runtime Configuration Cache

Router reads `runtime_config` using a short best-effort process-local cache. The TTL defaults to five seconds (`RUNTIME_CONFIG_TTL_SECONDS`). On a Postgres read failure the Router warns and uses its cached/default values rather than treating the configuration table as a synchronous dependency for every request.

Current active live keys include:

- `MAX_CONTEXT_TOKENS`;
- `BUILDER_BASE_URL`;
- `BUILDER_MODEL`.

Compatibility keys without consumers are not optimizations and do not change request behavior.

## 9. Async Admission as Latency Isolation

Ordinary chat dispatches Steward admission asynchronously after the user-facing response path. This protects Builder response latency from extraction/persistence cost but introduces an explicit durability tradeoff: if the asynchronous request fails, that turn may not be admitted to durable memory.

This is not a queue. There is no durable retry broker in the current tree. Documentation MUST NOT promise eventual admission after process failure.

## 10. Deterministic Agent Artifact Fast Path

Structured agent artifacts are persisted independently of optional LLM knowledge extraction. This is an important optimization and correctness boundary: deterministic outputs can remain reusable even if the Steward extraction LLM is unavailable or `admit_knowledge=false`.

## 11. Optimization Knobs

| Knob | Layer | Effect | Risk if mis-set |
| --- | --- | --- | --- |
| DENSE_PREFETCH | Router retrieval | Candidate pool size | Too low reduces recall; too high increases Qdrant/vector work |
| TOP_K | Router retrieval | Final dynamic selection cap | Too high consumes context; too low can omit relevant facts |
| MMR_LAMBDA | Router ranking | Relevance/diversity balance | Extreme values bias redundancy or diversity |
| MAX_CONTEXT_TOKENS | Router assembly | Retrieved context ceiling | Must fit inside total/provider context constraints |
| MAX_TOTAL_TOKENS | Router history planning | Global input planning ceiling | If below context budget, history allowance can collapse |
| RUNTIME_CONFIG_TTL_SECONDS | Router config | Frequency of Postgres runtime_config refresh | Very low increases DB load; high delays operator changes |
| STATIC_MEMORY_REFRESH_SECONDS | MCP-local cache | MCP process-local static cache refresh | Does not accelerate Router static retrieval |

## 12. Explicitly Not Implemented

The current tree does not implement these often-proposed optimization mechanisms:

- semantic response cache;
- cross-request prompt cache owned by Memory Steward;
- learned adaptive top-k controller;
- mode-classifier shortcut/hysteresis;
- durable async admission queue;
- background compaction/summarization loop;
- Router consumption of the MCP process-local static cache.

These MAY be future work, but current operational guidance must not rely on them.

## 13. Performance Measurement Contract

Any optimization change SHOULD report at least:

- request latency percentiles;
- embedding call count;
- Qdrant query count and prefetch size;
- dense candidates vs selected candidates;
- estimated context tokens by lane;
- budget drops;
- Builder prompt token count when available;
- admission dispatch/failure observations for hot-path changes.

Performance improvement is not sufficient if it changes authority boundaries or silently drops required context.

## 14. Optimization Regression Scenarios

1. long-history request proves dropped history does not re-enter the Builder payload;
2. empty dynamic lane still preserves static/reference behavior;
3. oversized candidate set respects context budget;
4. runtime budget update takes effect after cache refresh;
5. Postgres runtime-config read failure uses cached/default behavior;
6. reference-disabled configuration does not query the reference lane;
7. structured agent artifacts remain available with `admit_knowledge=false`;
8. asynchronous admission failure does not block a completed Builder response.

---

## 5. Closing Statement

Optimization claims in this repository MUST be grounded in current code. Speculation, semantic caches, and other future fast paths remain non-contractual until implemented and covered by executable tests.

[Back to top](#navigation)

---

**END OF DOCUMENT 04**

## Appendix A. Retrieval Function Map

| Function | Signature summary | Role |
| --- | --- | --- |
| count_tokens | model: str, text: str | Token estimation through tiktoken/model encoding |
| pg_static_load | mode: Optional[str] = None | Load active static rows, optionally exact mode-conditioned rows |
| extract_static_rules | static_rows: List[Tuple[str, str, str]] | Normalize static rows into context lanes |
| pg_agent_reference_load | project_id: str, selectors: List[ArtifactSelector] | Load exact deterministic artifacts for selectors |
| embed_one | text: str | Call embeddings service once for one query |
| qdrant_dense | project_id: str, vec: List[float], limit: int | Project-scoped semantic dynamic-memory prefetch |
| qdrant_reference | vec: List[float], limit: int, reference_filters: dict[str, str] \| None = None, | Reference-memory semantic query with exact whitelist filters |
| reference_candidate_payload | candidate: Candidate | Normalize reference candidate response |
| qdrant_reference_get | chunk_id: str | Fetch exact reference chunk |
| maximal_marginal_relevance | query_vec: List[float], candidates: List[Candidate], top_k: int, lambda_mult: float, | Bounded relevance/diversity selection |
| stitch_context_structured | candidates: List[Candidate], max_tokens: int, model: str, *, count_fn=None, | Assemble lanes under token budget |
| selected_candidate_refs | candidates: List[Candidate], max_tokens: int, model: str, *, count_fn=None, | Expose selected item identities/metadata |
| retrieve_context_structured | request_id: str, project_id: str, query: Optional[str], model: str, mode: Optional[str] = None, artifact_selectors: Optional[List[ArtifactSelector]] = None, reference_filters: dict | Orchestrate structured retrieval |
| render_context_envelope | retrieval: Dict[str, Any], query: str, recent_messages: List[ChatMessage] | Render context for Builder system message |
| assemble_context | request_id: str, project_id: str, query: str, model: str, recent_messages: List[ChatMessage], mode: Optional[str] = None, | Compatibility assembly helper |

## Appendix B. Budget Reasoning

The chat path effectively reserves input space in layers:

~~~text
history_allowance = MAX_TOTAL_TOKENS
                  - effective_MAX_CONTEXT_TOKENS
                  - current_user_text_tokens
                  - fixed_reserve(200)
~~~

Then history is accumulated newest-first until the next message would exceed the allowance. Separately, retrieval stitching respects the effective context budget.

This model has several engineering consequences:

1. `MAX_TOTAL_TOKENS` must remain greater than the effective context budget plus realistic current-message/reserve usage;
2. increasing context budget can reduce retained history;
3. a huge model context window does not justify unbounded retrieval because irrelevant context still harms quality/latency;
4. token counts are estimates tied to tokenizer/model behavior and should be treated as planning values;
5. response/output allowance is a provider concern and should be reconsidered when changing Builder models.

## Appendix C. MMR Behavior

Maximal Marginal Relevance attempts to select candidates that are both relevant to the query and not redundant with already selected candidates. Conceptually:

~~~text
score(candidate) = lambda * relevance_to_query
                 - (1 - lambda) * max_similarity_to_selected
~~~

With `MMR_LAMBDA=0.5`, relevance and diversity contribute symmetrically. The implementation operates on a bounded candidate pool, so complexity remains controlled by `DENSE_PREFETCH` and `TOP_K`.

MMR is not applied as an authority mechanism. A diverse candidate is not more trusted than an authoritative reference source merely because of ranking score; lane type and policy remain separate.

## Appendix D. Optimization Failure Modes

| Misconfiguration/change | Symptom | Verification |
| --- | --- | --- |
| `MAX_CONTEXT_TOKENS >= MAX_TOTAL_TOKENS` | no/negative history allowance | unit test long history + inspect Builder payload |
| `DENSE_PREFETCH` too small | relevant memory never reaches selection | retrieval recall fixture |
| `TOP_K` too large | context budget pressure | token accounting/drop counters |
| `MMR_LAMBDA` extreme | over-relevance or over-diversity | deterministic vector fixture |
| runtime-config TTL too high | operator change appears stale | timed config test |
| runtime-config TTL too low | unnecessary Postgres load | load/DB observation |
| debug prompts enabled | sensitive prompt logging | deployment env review |
| async admission assumed durable | lost admission on failure | kill/failure injection test |
| MCP cache assumed shared | Router behavior unchanged by cache_control | architecture test/documentation review |

## Appendix E. Measurement Plan for Retrieval Changes

A meaningful before/after benchmark should hold corpus/query fixtures constant and collect:

- embedding latency;
- Qdrant search latency;
- Postgres static/artifact query latency;
- candidates prefetched;
- candidates selected;
- MMR selection time;
- stitch/budget time;
- context tokens by lane;
- history tokens retained;
- Builder prompt tokens;
- end-to-end first-byte and complete latency;
- retrieval relevance judged against expected fixture IDs;
- error rate under dependency degradation.

## Appendix F. Optimization Change Classes

### F.1 Safe mechanical optimization

Example: reduce repeated serialization while preserving exact output. Requires tests proving output identity.

### F.2 Ranking optimization

Example: change MMR weighting. Requires relevance/regression fixtures because output selection may change.

### F.3 Budget optimization

Example: change context ceiling or history reserve. Requires long-history and oversized-context tests.

### F.4 Dependency/caching optimization

Example: cache static rows in Router. Requires cache ownership, invalidation, failure fallback, and consistency documentation. The existing MCP-local cache is not reusable evidence that Router caching is already solved.

### F.5 Async/durability optimization

Example: add a durable admission queue. Requires delivery semantics, retry identity, poison-message handling, observability, and shutdown behavior; it cannot be introduced as a mere latency tweak.

## Appendix G. Current Non-Goals

The optimization layer does not attempt to:

- predict user intent with a second model before every request;
- summarize every conversation turn into a single rolling blob;
- fuse reference and dynamic stores into one undifferentiated score;
- auto-tune thresholds from telemetry without explicit policy;
- persist model-provider cache state as Memory Steward memory;
- claim exact token guarantees across arbitrary provider tokenizers.

## Appendix H. Review Checklist for Performance Patches

1. Exact base and benchmark fixture recorded.
2. No authority boundary moved accidentally.
3. No lane silently removed from context.
4. Budget arithmetic remains non-negative for deployment values.
5. Failure fallback remains deterministic/documented.
6. Telemetry remains sufficient to explain selection changes.
7. No sensitive payload logging added.
8. Unit/integration tests cover behavior, not only speed.
9. Deployment/runtime-config docs updated.
10. Operator knobs are not added unless there is a real runtime consumer.
