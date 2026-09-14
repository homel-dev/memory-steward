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

## 9. Closing Statement

This document is the implementation-aligned Kubernetes and runtime contract. Namespace, workloads, service discovery, lifecycle tasks, and observability ownership MUST match the manifests and Taskfiles in the same tree.

[Back to top](#navigation)

---

**END OF DOCUMENT 09**
