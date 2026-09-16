# RUNTIME CONTRACT
## Kubernetes Topology, Service Configuration, and Operator Entry Points
### Foundational Engineering Specification (Document 09 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 08 (Verification)](08_verification.md) | [Next: Document 10 (Landscape)](10_industry_landscape.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Workloads](#1-workloads)
- [2. Service Discovery](#2-service-discovery)
- [3. Router Token Budget Contract](#3-router-token-budget-contract)
- [4. Request Topology](#4-request-topology)
- [5. Lifecycle](#5-lifecycle)
- [6. Operator MCP Access](#6-operator-mcp-access)
- [7. Images](#7-images)
- [8. Observability](#8-observability)
- [9. Closing Statement](#9-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers, operators, platform engineers
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

The Kubernetes namespace is `ms`.

[Back to top](#navigation)

---

## 1. Workloads

| Workload | Kind | Primary Port |
| --- | --- | ---: |
| `postgres` | StatefulSet | 5432 |
| `qdrant` | StatefulSet | 6333 |
| `embeddings` | Deployment | 8000 |
| `memory-router` | Deployment | 8080 |
| `memory-steward` | Deployment | 8090 |
| `memory-steward-mcp` | Deployment | 8081 |
| `memory-steward-list` | Deployment | 8001 |
| `codegraph-listener` | Deployment | 8092 |
| `codegraph-controller` | Deployment | 8093 |
| `open-webui` | Deployment | 8080 |
| `vector-agent` | DaemonSet | n/a |

OCO is external to this namespace's application workloads; Memory Steward publishes OCO consumer ConfigMaps/RBAC.

[Back to top](#navigation)

---

## 2. Service Discovery

Application manifests primarily use Kubernetes service-environment variables and the shared `homel-runtime-contract` ConfigMap.

Important current values include:

- `MCP_URL=http://memory-steward-mcp:8081/mcp`
- `MEMORY_ROUTER_URL=http://memory-router:8080`
- `QDRANT_COLLECTION=homel_memory`

Router/Steward code also requires Postgres credentials and service host/port variables injected by Kubernetes/manifests.

The checked-in ConfigMap also contains `STATIC_MEMORY_REFRESH_SECONDS` for the MCP-local cache and `HYSTERESIS_WINDOW` as a compatibility/diagnostics value. `HYSTERESIS_WINDOW` MUST NOT be described as an active request-policy control. Stale keys with no code consumer are removed rather than documented as runtime behavior.

Do not document generic environment variable aliases unless the code reads them.

[Back to top](#navigation)

---

## 3. Router Token Budget Contract

The checked-in runtime contract sets:

- `MAX_CONTEXT_TOKENS=128000` — upper bound for injected static/dynamic/reference context;
- `MAX_TOTAL_TOKENS=262144` — Router prompt-input planning ceiling used when pruning chat history.

`MAX_TOTAL_TOKENS` MUST remain greater than the maximum context budget. The current manifest selects `gpt-5.2`; if the Builder model/provider changes, both token limits MUST be revalidated against that provider/model before deployment.

Full prompt logging is disabled by default (`DEBUG_PROMPTS=false`) because assembled prompts may contain user text and retrieved memory.

[Back to top](#navigation)

---

## 4. Request Topology

~~~mermaid
sequenceDiagram
    participant C as Client
    participant R as Router
    participant E as Embeddings
    participant P as Postgres
    participant Q as Qdrant
    participant B as Builder
    participant S as Steward

    C->>R: /v1/chat/completions
    R->>P: static/artifact reads
    R->>E: embed query
    R->>Q: dynamic/reference search
    R->>B: Builder request
    B-->>R: response
    R-->>C: response
    R-->>S: async /admit
    S->>P: admitted state
    S->>Q: dynamic index
~~~

[Back to top](#navigation)

---

## 5. Lifecycle

~~~bash
task up
task ops:service:wait
task ops:service:status
task ops:service:restart
task down
~~~

Stateful restarts are explicit, prompted operations:

~~~bash
task ops:storage:restart:postgres
task ops:storage:restart:qdrant
~~~

[Back to top](#navigation)

---

## 6. Operator MCP Access

MCP remains cluster-internal. Use `kubectl exec` through Task wrappers or a loopback-only port-forward; do not add a public ingress for routine administration.

[Back to top](#navigation)

---

## 7. Images

Current manifests contain a mix of fixed and floating image tags. This document does not claim reproducible image pinning where the manifests do not provide it. A production deployment that requires reproducibility SHOULD pin immutable tags/digests as a separate verified change.

[Back to top](#navigation)

---

## 8. Observability

Memory Steward owns telemetry semantics and OCO provisioning content. OCO owns shared Grafana presentation. Vector is the log collector. Removing OCO affects visualization, not canonical Memory Steward storage.

[Back to top](#navigation)

---

## 9. Detailed Service Contract

| Component | Default in-cluster role | Primary port/path |
| --- | --- | --- |
| memory-router | OpenAI-compatible ingress + structured retrieval | 8080 |
| memory-steward | Admission/outcome/feedback service | 8090 |
| memory-steward-mcp | FastMCP internal control/adapter service | 8081 /mcp |
| memory-steward-list | Optional speech transcription | 8001 |
| codegraph-listener | MinIO CodeGraph object-event ingress | 8092 /events/minio |
| codegraph-controller | PostgreSQL-backed CodeGraph lifecycle/index controller | 8093 /healthz + worker callback |
| embeddings | Dense embedding service | 8000 |
| Postgres | Structured state/telemetry | 5432 |
| Qdrant | Vector index | 6333 |
| Open WebUI | Optional frontend | 8080 service-local |
| Vector | Log collection | agent/collector role |

## 10. Environment and Runtime Configuration

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
| CodeGraph listener | POSTGRES_* | required | CodeGraph discovery registry persistence |
| CodeGraph listener | CODEGRAPH_MINIO_BUCKETS / CODEGRAPH_MINIO_PREFIXES | empty | Optional event filters |
| CodeGraph listener | CODEGRAPH_MINIO_WEBHOOK_TOKEN | empty | Optional bearer token for MinIO webhook delivery |
| CodeGraph controller | POSTGRES_* | required | CodeGraph registry queue and LISTEN/NOTIFY |
| CodeGraph controller | CODEGRAPH_CONTROLLER_BATCH_SIZE | 16 | Maximum discovery rows claimed per drain |
| CodeGraph controller | CODEGRAPH_CONTROLLER_POLL_SECONDS | 5 | Fallback registry scan interval |
| CodeGraph controller | CODEGRAPH_VERSION | 0.20.1 | Pinned CodeGraph producer version expected by index workers |
| CodeGraph controller | CODEGRAPH_INDEX_PROFILE | graph-only | Initial structural indexing profile |
| CodeGraph controller | CODEGRAPH_WORKER_IMAGE | memory-steward image | Image used for isolated index Jobs |
| CodeGraph controller | CODEGRAPH_WORKER_SECRET_NAME | homel-codegraph | Optional Secret injected into workers |
| CodeGraph worker | MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY | required for indexing | MinIO/S3-compatible object access |
| CodeGraph worker | CODEGRAPH_WORKER_CALLBACK_TOKEN | optional | Bearer token shared with controller callback endpoint |
| LIST | DEVICE | cpu in manifest | Whisper device |
| LIST | COMPUTE_TYPE | int8 in manifest | Whisper compute type |
| LIST | WHISPER_MODEL_SIZE | component default | Whisper model size |
| TUI | STEWARD_MCP_URL | http://127.0.0.1:8081/mcp | MCP server URL |
| Embeddings | MODEL_NAME | BAAI/bge-small-en-v1.5 | Embedding model |

Kubernetes service-link variables (`*_SERVICE_HOST`/`*_SERVICE_PORT`) are used by Router/Steward code for several dependencies. The runtime ConfigMap also contains URL-style compatibility/operator values consumed by other components. Do not assume every ConfigMap key is read by every service.

## 11. Checked-In Runtime Contract ConfigMap

The current ConfigMap contains:

~~~yaml
QDRANT_URL: http://qdrant:6333
EMBEDDINGS_URL: http://embeddings:8000
BUILDER_BASE_URL: https://api.openai.com/v1
STEWARD_URL: http://memory-steward:8090
MEMORY_ROUTER_URL: http://memory-router:8080
STEWARD_LLM_BASE_URL: http://llm-large.llm-runtime.svc.cluster.local:8000
MCP_URL: http://memory-steward-mcp:8081/mcp
MAX_CONTEXT_TOKENS: "128000"
MAX_TOTAL_TOKENS: "262144"
QDRANT_COLLECTION: homel_memory
DENSE_PREFETCH: "25"
TOP_K: "8"
STATIC_MEMORY_REFRESH_SECONDS: "1800"
HYSTERESIS_WINDOW: "8"  # compatibility/diagnostics only
OPEN_WEBUI_URL: http://open-webui:8080
~~~

`OPEN_WEBUI_API_KEY` is intentionally documented as secret material rather than committed into the ConfigMap.

## 12. Taskfile Lifecycle Inventory

| Task | Operational purpose |
| --- | --- |
| up | Deploy namespace/resources and wait for core services |
| down | Delete namespace ms |
| status:all | Show workload/resource state |
| nuke | Destructive cleanup path |
| build | Build local development images inside Minikube; does not rewrite GHCR manifests |
| k8s:deploy | Apply Kubernetes manifests |
| k8s:wait | Wait for configured workloads |
| k8s:restart | Restart application workloads |
| db:init | Initialize Postgres schema |
| db:init-qdrant | Initialize Qdrant collection |
| db:reset | Reset state with destructive confirmation |
| db:shell | Open Postgres shell |
| migrate:up | Apply canonical SQL migrations |
| migrate:status | Inspect migration status |
| backup | Create state backup |
| restore | Restore backup with safeguards |
| export:memory | Export memory data |
| export:fetch | Fetch exported data |
| verify:health | Run in-cluster health verification |
| verify:amp | Run Agent Memory Protocol checks |
| logs:router | Tail Router logs |
| logs:steward | Tail Steward logs |
| ops:service:status | Show complete service status |
| ops:service:wait | Wait for full service set |
| ops:service:health | Call health endpoints from an in-cluster context |
| ops:app:stop | Scale/stop application workloads |
| ops:app:start | Start application workloads |
| ops:service:restart | Restart application services |
| ops:service:restart:router | Restart Router |
| ops:service:restart:steward | Restart Steward |
| ops:service:restart:mcp | Restart MCP |
| ops:service:restart:list | Restart LIST |
| ops:service:restart:embeddings | Restart embeddings |
| ops:service:restart:webui | Restart Open WebUI |
| ops:service:restart:vector | Restart Vector |
| ops:storage:restart:postgres | Prompted Postgres restart |
| ops:storage:restart:qdrant | Prompted Qdrant restart |
| ops:mcp:tools | List live MCP tools |
| ops:mcp:tools:json | List live MCP tools as JSON |
| ops:mcp:call | Call arbitrary live MCP tool |
| ops:mcp:forward | Loopback-only MCP port-forward |
| ops:ref:list | Reference list shortcut |
| ops:ref:inspect | Reference inspect shortcut |
| ops:ref:ingest:url | Reference URL ingestion shortcut |
| ops:ref:ingest:text | Reference text ingestion shortcut |
| ops:ref:purge | Prompted reference purge shortcut |
| ops:ref:search | Reference search shortcut |
| ops:ref:get | Reference get shortcut |
| ops:config:show | Show runtime config |
| ops:diag:health | Diagnostics health shortcut |

## 13. Stateful Data

| State | Persistence | Operational concern |
| --- | --- | --- |
| Postgres | PVC/stateful deployment according to manifests | Contains canonical structured memory/config/telemetry; backup before destructive reset |
| Qdrant | Persistent vector store according to manifests | Contains semantic dynamic/reference index; consistency with Postgres metadata matters |
| Whisper/HF model cache | `hf-cache` PVC | Avoids multi-GB model re-download for LIST |
| Vector log volume | `vector-logs` PVC where configured | Shared log access for diagnostics |
| Backups | backup PVC / repository backup workflow | Used by backup/restore tasks |

## 14. Deployment Ordering

Recommended readiness order:

~~~text
namespace + secrets/config
  -> Postgres + migrations
  -> Qdrant + collection initialization
  -> embeddings
  -> memory-steward
  -> memory-router
  -> memory-steward-mcp
  -> optional LIST / Open WebUI / Vector / OCO consumer resources
~~~

The repository Tasks encode most of this lifecycle. Operators should prefer those Tasks over ad hoc host commands because the Taskfile captures namespace/resource assumptions.

## 15. Image Semantics

`task build` creates local development images in Minikube. Checked-in manifests reference GHCR images. Therefore a successful local build does not by itself change what `task up` deploys. To test local images, the manifest/image policy must be intentionally overridden or a dedicated development workflow used.

Published image workflows are distinct from runtime deployment. CI image success does not prove Kubernetes health.

## 16. MCP Network Posture

MCP is intended to remain internal. Local operator access uses loopback port-forward:

~~~bash
task ops:mcp:forward
~~~

The resulting client endpoint is `http://127.0.0.1:8081/mcp`. Do not create a public MCP ingress merely to simplify local operation.

## 17. Cross-Namespace LLM Dependency

The checked-in Steward LLM endpoint targets `llm-large.llm-runtime.svc.cluster.local:8000`. This is an external runtime dependency from the `ms` namespace and must be reachable under cluster networking policy. Builder routing may use the configured external OpenAI-compatible endpoint or service-derived default depending on environment/runtime configuration.

## 18. Operational Troubleshooting Matrix

| Symptom | First checks |
| --- | --- |
| Router 5xx | Router logs, Builder reachability, Postgres/Qdrant/embeddings, token/config values |
| No reference results | Reference eligibility mode, REFERENCE_RETRIEVAL_ENABLED, exact filters, Qdrant payload/index |
| No durable memory after chat | Steward availability, async admission logs, extraction LLM, embeddings/Qdrant/Postgres |
| AMP artifact missing | outcome idempotency row, artifact selectors/hash, agent_reference table |
| MCP client fails | MCP pod/service, /mcp URL, port-forward, live tool list |
| LIST fails | Whisper model cache, CPU/GPU DEVICE/COMPUTE_TYPE, pod resources |
| Config change not immediate | Router runtime-config TTL/cache and whether key has an active consumer |

---

## 9. Closing Statement

This document is the implementation-aligned Kubernetes and runtime contract. Namespace, workloads, service discovery, lifecycle tasks, and observability ownership MUST match the manifests and Taskfiles in the same tree.

[Back to top](#navigation)

---

**END OF DOCUMENT 09**


## Appendix A. HTTP Endpoint Inventory

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
