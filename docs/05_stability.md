# RUNTIME CONFIGURATION AND STABILITY
## Implemented Dynamic Configuration and Inactive Compatibility Keys
### Foundational Engineering Specification (Document 05 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 04 (Optimizations)](04_optimizations.md) | [Next: Document 06 (Telemetry)](06_telemetry.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Runtime Configuration Store](#1-runtime-configuration-store)
- [2. MCP Configuration Tools](#2-mcp-configuration-tools)
- [3. Not Implemented](#3-not-implemented)
- [4. Safe Evolution](#4-safe-evolution)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PARTIAL
**Audience:** Maintainers and operators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

[Back to top](#navigation)

---

## 1. Runtime Configuration Store

`memory-steward-mcp` persists operator configuration in the Postgres `runtime_config` table.

The Router currently reloads and consumes these keys:

- `MAX_CONTEXT_TOKENS`
- `BUILDER_BASE_URL`
- `BUILDER_MODEL`

The Router caches runtime-config reads for a bounded TTL to avoid a database read on every request.

[Back to top](#navigation)

---

## 2. MCP Configuration Tools

Implemented tools include:

- `config_set_budget`
- `config_force_mode`
- `config_set_hysteresis`
- `config_show`

`config_set_budget` has an active Router consumer.

`config_force_mode` and `config_set_hysteresis` currently persist compatibility keys only. The Router/Steward do not consume `FORCE_MODE` or `HYSTERESIS_WINDOW`; therefore those two operations MUST NOT be represented as changing live request behavior.

[Back to top](#navigation)

---

## 3. Not Implemented

There is currently no:

- mode transition state machine;
- hysteresis window enforcement;
- decay function;
- mode-jitter telemetry;
- forced-mode application in Router or Steward.

[Back to top](#navigation)

---

## 4. Safe Evolution

If mode stabilization is implemented later, the change MUST add a runtime consumer, tests proving transition semantics, bounded configuration validation, and telemetry showing the applied mode source.

[Back to top](#navigation)

---

## 5. Runtime Configuration Inventory

| Consumer | Variable/key | Default / checked-in value | Meaning |
| --- | --- | --- | --- |
| Router | POSTGRES_SERVICE_HOST / POSTGRES_SERVICE_PORT | required via Kubernetes service discovery | Postgres address |
| Router | POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB | required | Database credentials/database |
| Router | POSTGRES_SSLMODE | disable | Postgres TLS mode |
| Router | POSTGRES_APPLICATION_NAME | memory-router | Postgres application_name |
| Router | QDRANT_SERVICE_HOST / QDRANT_SERVICE_PORT | required | Qdrant address |
| Router | EMBEDDINGS_SERVICE_HOST / EMBEDDINGS_SERVICE_PORT | required | Embeddings address |
| Router | QDRANT_COLLECTION | required | Qdrant collection |
| Router | BUILDER_BASE_URL | service-derived when unset | Builder OpenAI-compatible base URL |
| Router | BUILDER_API_KEY | local-token | Builder API key |
| Router | BUILDER_MODEL | required | Builder model |
| Router | MEMORY_STEWARD_SERVICE_HOST / MEMORY_STEWARD_SERVICE_PORT | required | Steward address |
| Router | MAX_CONTEXT_TOKENS | 8192 code default; 128000 manifest value | Retrieval context budget |
| Router | MAX_TOTAL_TOKENS | 16384 code default; 262144 manifest value | Prompt-input planning ceiling |
| Router | DENSE_PREFETCH | 25 | Dense candidate prefetch |
| Router | TOP_K | 8 | Final candidate cap |
| Router | MMR_LAMBDA | 0.5 | MMR relevance/diversity balance |
| Router | DEBUG_PROMPTS | false-like default | Full prompt debug logging; disabled in deployment |
| Router | REFERENCE_RETRIEVAL_ENABLED | true-like default | Global reference lane toggle |
| Router | RUNTIME_CONFIG_TTL_SECONDS | 5 | runtime_config cache TTL |
| Router | MCP_URL | required by MCP bridge deployment | MCP endpoint for /glap |
| Steward | STEWARD_LLM_BASE_URL | required | Steward extraction LLM endpoint |
| Steward | STEWARD_LLM_API_KEY | local-token | Steward LLM API key |
| Steward | STEWARD_MODEL | empty -> server/provider behavior | Steward model selection |
| Steward | QDRANT_COLLECTION | required | Qdrant collection |
| Steward | POSTGRES_* | required | Structured persistence |
| Steward | EMBEDDINGS_SERVICE_HOST / PORT | required | Embedding service |
| LIST | DEVICE | cpu in manifest | Whisper device |
| LIST | COMPUTE_TYPE | int8 in manifest | Whisper compute type |
| LIST | WHISPER_MODEL_SIZE | component default | Whisper model size |
| TUI | STEWARD_MCP_URL | http://127.0.0.1:8081/mcp | MCP server URL |
| Embeddings | MODEL_NAME | BAAI/bge-small-en-v1.5 | Embedding model |
| Embeddings | EMBEDDING_THREADS | 4 in manifest/code default | ONNX intra/inter-op thread bound |
| Embeddings | EMBEDDING_CONCURRENCY | 1 in manifest/code default | Maximum concurrent model executions |
| Embeddings | EMBEDDING_BATCH_SIZE | 16 in manifest/code default | Internal FastEmbed batch bound |
| Embeddings | EMBEDDING_MAX_TEXTS | 64 in manifest/code default | Maximum texts accepted by one /embed request |

The table intentionally distinguishes code defaults from manifest values. Deployment manifests are the effective checked-in operating profile; code defaults are fallback behavior when an environment value is omitted.

## 6. Live `runtime_config` Semantics

The Router does not read every stored key as policy. It fetches the table into a short-lived cache and uses helper functions only for known active keys.

| Key | Current Router consumer | Failure fallback |
| --- | --- | --- |
| MAX_CONTEXT_TOKENS | effective_max_context_tokens() | Environment-derived MAX_CONTEXT_TOKENS_DEFAULT |
| BUILDER_BASE_URL | effective_builder_base_url() | Environment/service-derived Builder base URL |
| BUILDER_MODEL | effective_builder_model() | Environment BUILDER_MODEL |
| FORCE_MODE | None | No effect |
| HYSTERESIS_WINDOW | None in a mode engine | No effect |

A key is active only when code consumes it.

## 7. Service Health and Dependency Boundaries

| Service | Local health route | Critical dependencies for full function | Isolation note |
| --- | --- | --- | --- |
| memory-router | GET /healthz | Postgres, Qdrant, embeddings, Builder, Steward for async admission; MCP only for /glap | Health route itself is lightweight |
| memory-steward | GET /healthz | Postgres, Qdrant, embeddings, Steward LLM | Agent artifact persistence and extraction have different dependencies |
| memory-steward-mcp | /healthz on MCP service | Postgres/Qdrant plus Router/Steward for adapter tools | Internal control surface |
| memory-steward-list | GET /healthz | Local Whisper model/runtime | No memory database access by design |
| embeddings | GET /healthz | Embedding model loaded | Shared by Router, Steward, and reference ingestion; CPU/thread bounded |
| reference-ingest-worker | no HTTP endpoint | Postgres queue, embeddings, Qdrant, source URL egress | One durable URL job at a time per replica |

## 8. Operational Recovery Order

A practical recovery sequence is:

1. verify Kubernetes namespace and stateful stores;
2. verify Postgres and Qdrant readiness;
3. verify embeddings;
4. verify Router and Steward;
5. verify MCP and the reference-ingest worker;
6. verify optional LIST/Open WebUI;
7. run `task ops:service:health` or the repository health task;
8. inspect diagnostics and logs before destructive reset operations.

Stateful restarts are intentionally separate and prompted. Do not use a generic application restart as a substitute for diagnosing storage corruption or migration mismatch.

## 9. Failure Semantics

| Failure | Current behavior / expectation |
| --- | --- |
| runtime_config Postgres read fails | Router logs warning and uses cached/default values |
| invalid integer runtime value | Router logs warning and uses default |
| Builder endpoint fails | Chat request fails at upstream dispatch; telemetry records error |
| Steward async admission fails | Chat response may already be complete; admission failure is isolated |
| Qdrant fails | Semantic lanes fail; do not fabricate context |
| Reference worker or source fetch fails | Durable URL job becomes failed; no automatic application retry; explicit retry is required |
| Reference worker exits mid-job | Lease fencing prevents stale completion; expired running work is requeued |
| Oversized embedding request | Embeddings returns HTTP 413 rather than scheduling unbounded work |
| MCP process-local cache is stale | Only MCP static cache consumers are affected; Router does not consume that cache |
| LIST model load fails at startup | Startup handler logs failure; first request may retry model loading |
| TUI cannot reach MCP | TUI reports connection error and suggests port-forward; it does not mutate state |

## 10. Stability Anti-Patterns

Do not:

- describe a compatibility key as a live control without a code consumer;
- hide a stateful restart inside an unprompted convenience Task;
- depend on host-installed curl when repository verification can execute in-cluster;
- set `MAX_CONTEXT_TOKENS` greater than the practical provider/model input ceiling without reevaluating `MAX_TOTAL_TOKENS`;
- enable `DEBUG_PROMPTS` in routine deployment because it can emit complete assembled prompts;
- treat `latest` image tags as a reproducibility guarantee.

## 11. Change Review Checklist

For a stability/configuration change, verify:

1. environment source and default;
2. manifest value;
3. live runtime_config consumer if any;
4. cache/refresh semantics;
5. failure fallback;
6. diagnostics visibility;
7. restart requirements;
8. secret-handling implications;
9. tests for malformed/missing values;
10. documentation in this document and runtime contract.

---

## 5. Closing Statement

The live stability surface is the subset of runtime configuration that current components actually consume. Persisted compatibility keys MUST NOT be documented as effective behavior until a runtime reader exists.

[Back to top](#navigation)

---

**END OF DOCUMENT 05**
