# MANAGEMENT INTERFACE AND MCP
## Schema-Driven Operator and Agent Control Surface
### Foundational Engineering Specification (Document 07 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 06 (Telemetry)](06_telemetry.md) | [Next: Document 08 (Verification)](08_verification.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Architecture](#1-architecture)
- [2. Clients](#2-clients)
- [3. Implemented Tool Inventory](#3-implemented-tool-inventory)
- [4. MCP Resources](#4-mcp-resources)
- [5. Reference-Memory Terminal Workflow](#5-reference-memory-terminal-workflow)
- [6. Safety and Scope Notes](#6-safety-and-scope-notes)
- [7. Closing Statement](#7-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers and operators
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

This document describes the tools registered by the current `memory-steward-mcp` server. The live MCP schema remains authoritative for parameter types and optional fields.

[Back to top](#navigation)

---

## 1. Architecture

`memory-steward-mcp` is a FastMCP HTTP server in namespace `ms`. Kubernetes exposes it as the internal Service `memory-steward-mcp`; routine operator access does not require a public ingress.

~~~mermaid
graph LR
    Operator[Operator terminal / MCP client]
    WebUI[Open WebUI /glap]
    Agent[Agent runtime]
    MCP[memory-steward-mcp]
    Router[memory-router]
    Steward[memory-steward]
    PG[(Postgres)]
    Q[(Qdrant)]

    Operator -->|kubectl exec or loopback port-forward| MCP
    WebUI -->|Router MCP bridge| MCP
    Agent -->|MCP| MCP
    MCP -->|AMP retrieval adapters| Router
    MCP -->|AMP outcome/feedback adapters| Steward
    MCP -->|operator state/config/diagnostics| PG
    MCP -->|reference ingestion/inspection| Q
~~~

The live MCP tool schemas are the command contract. Clients SHOULD discover those schemas rather than maintain a second hard-coded command model.

[Back to top](#navigation)

---

## 2. Clients

### 2.1 Open WebUI `/glap`

Memory Router intercepts `/glap` commands and delegates to its MCP bridge. The bridge queries the live MCP tool list and uses current schemas for command help and argument requirements.

### 2.2 Terminal inside Kubernetes

~~~bash
task ops:mcp:tools
task ops:mcp:tools:json
task ops:mcp:call -- ref_list
task ops:ref:inspect -- product=kicad version=9.0 limit=10
~~~

The Task wrappers invoke FastMCP inside the already-deployed MCP pod, so the workstation does not need a separate Python/FastMCP environment.

### 2.3 Local MCP-capable clients

~~~bash
task ops:mcp:forward
# http://127.0.0.1:8081/mcp
~~~

The port-forward binds loopback only. FastMCP can also derive a typed CLI from live tool schemas; a future full-screen TUI SHOULD remain a presentation layer over this same MCP contract rather than define another command API.

[Back to top](#navigation)

---

## 3. Implemented Tool Inventory

### 3.1 Content plane

| Tool | Current responsibility |
| --- | --- |
| `ref_ingest_url` | Fetch a URL, chunk/embed it, and upsert canonical Reference Memory. |
| `ref_ingest_text` | Chunk/embed caller-supplied text and upsert canonical Reference Memory. |
| `ref_list` | List recorded reference-ingestion namespaces/events. |
| `ref_inspect` | Inspect chunks for a product/version. |
| `ref_purge` | Delete canonical reference chunks for a product/version. |
| `static_list` | List Postgres static-memory rules. |
| `static_create` | Create a static-memory rule. |
| `static_update` | Update a static-memory rule. |
| `static_toggle` | Enable/disable a static-memory rule. |
| `static_delete` | Permanently delete a static-memory rule. |
| `cache_control` | Refresh/evict the MCP process's `StaticMemoryCacheManager`. |

`cache_control` MUST NOT be described as clearing the Router's request-path static-memory cache: the current Router reads static memory from Postgres and does not use `memory_steward_mcp.cache.StaticMemoryCacheManager`.

### 3.2 Stability/config plane

| Tool | Current responsibility |
| --- | --- |
| `config_set_budget` | Persist `MAX_CONTEXT_TOKENS`; Router consumes it through `runtime_config`. |
| `config_force_mode` | Persist legacy `FORCE_MODE`; no current Router/Steward consumer. |
| `config_set_hysteresis` | Persist legacy `HYSTERESIS_WINDOW`; no current hysteresis engine. |
| `config_show` | Show persisted runtime-config keys and their current consumer status. |

### 3.3 Diagnostics plane

| Tool | Current responsibility |
| --- | --- |
| `diag_health` | Check Qdrant, Postgres, embeddings, LIST, and Router connectivity/state. |
| `diag_explain` | Read the telemetry blame trace for a request ID. |
| `diag_explain_last` | Explain the most recent telemetry request. |
| `diag_metrics` | Summarize bounded request/retrieval/admission/step metrics. |
| `diag_qdrant_stats` | Show collection status and counts by memory type. |
| `dyn_inspect` | Inspect dynamic-memory rows for a project. |
| `dyn_simulate_retrieval` | Run a diagnostic dense Qdrant lookup for a project/query. |
| `diag_logs` | Read a bounded tail from the configured log directory. |

`dyn_simulate_retrieval` is a diagnostic candidate lookup, not a bit-for-bit reproduction of the Router's complete retrieval/MMR/budget pipeline.

### 3.4 Git/repository plane

| Tool | Current responsibility |
| --- | --- |
| `repo_add` | Register a named Git provider connection in Postgres. |
| `repo_list` | List configured repository connections. |
| `repo_remove` | Remove a configured connection. |
| `repo_test` | Test a configured connection. |
| `git_list_repos` | List repositories visible through a connection. |
| `git_ingest_repo` | Ingest repository files into Reference Memory. |
| `git_ingest_file` | Ingest one repository file into Reference Memory. |
| `git_write_file` | Create/update a repository file when the connection is `read-write`. |

The current provider adapters cover GitLab, GitHub, and Bitbucket. Connection credentials are persisted by the current Git-plane implementation; the MCP service therefore belongs on a trusted internal operator boundary.

### 3.5 Agent plane

| Tool | Current responsibility |
| --- | --- |
| `memory.retrieve_context` | Delegate governed structured retrieval to Router. |
| `memory.reference.search` | Delegate Reference Memory semantic search to Router. |
| `memory.reference.get` | Delegate exact reference-chunk fetch to Router. |
| `memory.submit_agent_outcome` | Delegate structured outcome admission/persistence to Steward. |
| `memory.submit_context_feedback` | Delegate retrieval-quality feedback to Steward. |

AMP handlers are transport adapters; they MUST NOT independently implement Router retrieval policy or Steward admission policy.

[Back to top](#navigation)

---

## 4. MCP Resources

The current server registers one explicit MCP resource:

- `diagnostics://contract` — JSON view of selected diagnostics/runtime values exposed by `diagnostics_plane.py`.

The repository does **not** currently register the old conceptual `mem://...`, `ref://...`, or telemetry resource families from earlier design drafts. Reference and memory inspection are tool operations in the current implementation.

[Back to top](#navigation)

---

## 5. Reference-Memory Terminal Workflow

Reference ingestion is explicit and synchronous.

~~~bash
# Discover the live schema first.
task ops:mcp:tools:json

# List current reference namespaces/events.
task ops:ref:list

# Inspect one product/version.
task ops:ref:inspect -- product=kicad version=9.0 limit=10

# Ingest a URL.
task ops:ref:ingest:url -- url=https://example.invalid/docs product=kicad version=9.0 scope=pcb

# Search canonical Reference Memory through the Router-owned agent API adapter.
task ops:ref:search -- project_id=operator query="hierarchical sheet syntax"

# Purge is destructive and the Task wrapper prompts first.
task ops:ref:purge -- product=kicad version=9.0
~~~

For multiline/raw text ingestion, use `ops:mcp:call`/FastMCP argument encoding directly; the live tool schema defines the accepted parameters.

[Back to top](#navigation)

---

## 6. Safety and Scope Notes

- Do not add a public MCP ingress merely for operator convenience.
- Prefer `kubectl exec` or loopback-only port-forward for local operation.
- Destructive tools MUST remain explicit and auditable.
- Git write operations MUST use a `read-write` connection; read-only connections are rejected by the Git plane.
- `ref_ingest_url` performs server-side URL fetching. Deployments with strict SSRF/egress requirements SHOULD add destination validation and network egress policy before treating arbitrary URLs as safe input.
- MCP configuration text MUST distinguish persisted compatibility keys from keys that have active runtime consumers.

[Back to top](#navigation)

---

## 7. Closing Statement

The MCP server is the single schema-driven operator/agent control surface. Terminal, Open WebUI, and future TUI clients SHOULD consume the same live MCP schemas rather than create parallel command contracts.

[Back to top](#navigation)

---

**END OF DOCUMENT 07**
