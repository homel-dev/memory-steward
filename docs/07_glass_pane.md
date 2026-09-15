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
## http://127.0.0.1:8081/mcp
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
## Discover the live schema first.
task ops:mcp:tools:json

## List current reference namespaces/events.
task ops:ref:list

## Inspect one product/version.
task ops:ref:inspect -- product=kicad version=9.0 limit=10

## Ingest a URL.
task ops:ref:ingest:url -- url=https://example.invalid/docs product=kicad version=9.0 scope=pcb

## Search canonical Reference Memory through the Router-owned agent API adapter.
task ops:ref:search -- project_id=operator query="hierarchical sheet syntax"

## Purge is destructive and the Task wrapper prompts first.
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

## 7. Complete Tool Contract

| Plane | Tool | Class | Purpose |
| --- | --- | --- | --- |
| content | ref_ingest_url | Mutating | Fetch and ingest a reference URL into canonical Reference Memory |
| content | ref_ingest_text | Mutating | Ingest operator-provided reference text |
| content | ref_list | Read-only | List reference ingestion namespaces/events |
| content | ref_inspect | Read-only | Inspect stored reference chunks by metadata |
| content | ref_purge | Destructive | Delete reference data for an explicit selection |
| content | static_list | Read-only | List static memory rows |
| content | static_create | Mutating | Create static memory |
| content | static_update | Mutating | Update a static-memory row |
| content | static_toggle | Mutating | Enable or disable static memory |
| content | static_delete | Destructive | Delete a static-memory row |
| content | cache_control | Process-local | Control the MCP process-local static-memory cache only |
| stability | config_set_budget | Mutating | Persist MAX_CONTEXT_TOKENS consumed by Router |
| stability | config_force_mode | Compatibility | Persist FORCE_MODE; current Router/Steward do not consume it |
| stability | config_set_hysteresis | Compatibility | Persist HYSTERESIS_WINDOW; no current hysteresis engine consumes it |
| stability | config_show | Read-only | Show runtime_config values and current-consumer annotations |
| diagnostics | diag_health | Read-only | Aggregate service health information |
| diagnostics | diag_explain | Read-only | Inspect telemetry for a request |
| diagnostics | diag_explain_last | Read-only | Inspect most recent request telemetry |
| diagnostics | diag_metrics | Read-only | Summarize operational telemetry |
| diagnostics | diag_qdrant_stats | Read-only | Inspect Qdrant collection statistics |
| diagnostics | dyn_inspect | Read-only | Inspect dynamic-memory rows |
| diagnostics | dyn_simulate_retrieval | Read-only | Simulate dynamic retrieval for troubleshooting |
| diagnostics | diag_logs | Read-only | Read shared collected logs |
| git | repo_add | Mutating | Register repository metadata/connection |
| git | repo_list | Read-only | List registered repositories |
| git | repo_remove | Mutating | Remove repository registration |
| git | repo_test | Read-only/network | Test repository access |
| git | git_list_repos | Read-only | List Git repositories available through the Git plane |
| git | git_ingest_repo | Mutating | Ingest repository content into reference memory |
| git | git_ingest_file | Mutating | Ingest one repository file into reference memory |
| git | git_write_file | Mutating external | Write a repository file when explicitly invoked and authorized |
| agent | memory.retrieve_context | Read-only | Adapter to Router /v1/context/retrieve |
| agent | memory.reference.search | Read-only | Adapter to Router reference search |
| agent | memory.reference.get | Read-only | Adapter to Router reference get |
| agent | memory.submit_agent_outcome | Mutating | Adapter to Steward structured outcome admission |
| agent | memory.submit_context_feedback | Mutating | Adapter to Steward context feedback |

The tool list above is a current implementation inventory. Clients SHOULD still call MCP `list_tools` because FastMCP schemas define the exact runtime arguments and may evolve with code.

## 8. Terminal Glass Pane TUI

The repository contains `components/steward_tui`, a Textual MCP client. It is not a second management API. It discovers the server's tool list and JSON Schema live, groups tools by plane, renders fields dynamically, and invokes the selected tool through FastMCP.

### 8.1 TUI behavior

~~~text
StewardTUI starts
  -> resolve STEWARD_MCP_URL or default http://127.0.0.1:8081/mcp
  -> FastMCP Client.list_tools()
  -> convert each tool inputSchema to scalar form fields
  -> group/sort by inferred plane
  -> operator selects tool
  -> render required/optional fields
  -> coerce scalar input types
  -> Client.call_tool(..., raise_on_error=False)
  -> render structured content and text blocks in result log
~~~

Supported dynamic scalar form types are string, integer, number, and boolean. Complex schemas fall back conservatively rather than inventing client-side policy.

Keyboard bindings include `q` to quit and `r` to refresh the live tool inventory.

### 8.2 Connectivity

The default TUI URL is loopback MCP:

~~~text
http://127.0.0.1:8081/mcp
~~~

Use the repository port-forward Task before launching a local TUI/client:

~~~bash
task ops:mcp:forward
~~~

or set `STEWARD_MCP_URL` explicitly.

## 9. `/glap` ChatOps Bridge

Router recognizes user input beginning with `/glap` and delegates command interpretation to its MCP bridge. This is an optional conversational operator surface, not the MCP protocol itself. The bridge discovers live MCP tools/schemas instead of maintaining a divergent hard-coded tool contract.

Streaming chat requests are supported by wrapping the `/glap` result in the Router's SSE-compatible response path.

## 10. Client Choice Matrix

| Client | Best use | Schema source | Exposure |
| --- | --- | --- | --- |
| Task wrappers | Repeatable shell/operator procedures | FastMCP command invocation | In-cluster or loopback |
| FastMCP CLI | Ad hoc exact tool calls and schema inspection | Live MCP server | In-cluster or loopback |
| Steward TUI | Interactive full-screen operations | Live MCP server | Local client via loopback by default |
| Open WebUI /glap | Conversational ChatOps | Router MCP bridge + live schemas | Through existing Router/Open WebUI path |
| Agent MCP adapters | Programmatic context/outcome workflows | Live MCP server | Cluster/internal integration |

## 11. Tool-Safety Classification

Read-only tools may still expose sensitive operational information. Mutating tools must be treated as explicit operator actions. Destructive tools such as `ref_purge` and static deletion should never be invoked implicitly because a model merely discussed deletion.

The Git plane contains `git_write_file`. Its presence means the MCP server can expose an external mutation capability when configured/authorized. Operator policy MUST decide whether that capability is enabled/usable in a given deployment. Documentation and clients must not disguise it as a read-only ingestion tool.

## 12. MCP Resource Contract

The explicit resource `diagnostics://contract` exposes selected diagnostics/runtime values. Historical conceptual resources such as `mem://...` or `ref://...` are not current resources; memory/reference inspection is tool-driven in this implementation.

## 13. Authentication and Network Posture

Current repository guidance keeps MCP internal/ClusterIP and uses loopback port-forward for local clients. A public ingress for routine operator access is not part of the supported topology.

Authentication/authorization hardening is a deployment concern that must be explicit before exposing MCP beyond trusted cluster/local boundaries. Tool-level mutation authority, credentials, and Git write capability require particular care.

## 14. Reference Workflow Example

~~~bash
## Discover exact live tool schema.
task ops:mcp:tools:json

## Inspect available corpora.
task ops:ref:list

## Ingest authoritative source material.
task ops:ref:ingest:url -- url=https://example.invalid/docs product=kicad version=9.0 scope=pcb

## Inspect/filter stored reference content.
task ops:ref:inspect -- product=kicad version=9.0 limit=10

## Search through the Router-owned reference API adapter.
task ops:ref:search -- project_id=operator query="hierarchical sheet syntax"

## Destructive operation: wrapper prompts.
task ops:ref:purge -- product=kicad version=9.0
~~~

## 15. Troubleshooting Workflow

When an MCP client fails:

1. check `task ops:service:status`;
2. check `task ops:diag:health`;
3. verify the port-forward if the client is local;
4. refresh/list tools to rule out stale schema assumptions;
5. inspect MCP logs;
6. inspect Router/Steward dependencies for adapter tools;
7. distinguish protocol/connectivity errors from tool-returned application errors.

The TUI deliberately returns tool errors as rendered results instead of crashing the UI whenever FastMCP returns an error result.

## 16. MCP Change Checklist

A new/changed tool requires:

- exact name and plane classification;
- input-schema validation;
- mutation/safety classification;
- component test coverage;
- Task/TUI implications;
- documentation inventory update here;
- operator example only if it improves a supported workflow;
- explicit backend authority (MCP-local, Router, Steward, Postgres/Qdrant, or external Git).

---

## 7. Closing Statement

The MCP server is the single schema-driven operator/agent control surface. Terminal, Open WebUI, and future TUI clients SHOULD consume the same live MCP schemas rather than create parallel command contracts.

[Back to top](#navigation)

---

**END OF DOCUMENT 07**


## Appendix A. Tool-by-Tool Review Checklist

For every tool below, reviewers should verify that its live schema, backend authority, mutation class, error behavior, and documentation remain aligned.

| Plane | Tool | Class | Purpose |
| --- | --- | --- | --- |
| content | ref_ingest_url | Mutating | Fetch and ingest a reference URL into canonical Reference Memory |
| content | ref_ingest_text | Mutating | Ingest operator-provided reference text |
| content | ref_list | Read-only | List reference ingestion namespaces/events |
| content | ref_inspect | Read-only | Inspect stored reference chunks by metadata |
| content | ref_purge | Destructive | Delete reference data for an explicit selection |
| content | static_list | Read-only | List static memory rows |
| content | static_create | Mutating | Create static memory |
| content | static_update | Mutating | Update a static-memory row |
| content | static_toggle | Mutating | Enable or disable static memory |
| content | static_delete | Destructive | Delete a static-memory row |
| content | cache_control | Process-local | Control the MCP process-local static-memory cache only |
| stability | config_set_budget | Mutating | Persist MAX_CONTEXT_TOKENS consumed by Router |
| stability | config_force_mode | Compatibility | Persist FORCE_MODE; current Router/Steward do not consume it |
| stability | config_set_hysteresis | Compatibility | Persist HYSTERESIS_WINDOW; no current hysteresis engine consumes it |
| stability | config_show | Read-only | Show runtime_config values and current-consumer annotations |
| diagnostics | diag_health | Read-only | Aggregate service health information |
| diagnostics | diag_explain | Read-only | Inspect telemetry for a request |
| diagnostics | diag_explain_last | Read-only | Inspect most recent request telemetry |
| diagnostics | diag_metrics | Read-only | Summarize operational telemetry |
| diagnostics | diag_qdrant_stats | Read-only | Inspect Qdrant collection statistics |
| diagnostics | dyn_inspect | Read-only | Inspect dynamic-memory rows |
| diagnostics | dyn_simulate_retrieval | Read-only | Simulate dynamic retrieval for troubleshooting |
| diagnostics | diag_logs | Read-only | Read shared collected logs |
| git | repo_add | Mutating | Register repository metadata/connection |
| git | repo_list | Read-only | List registered repositories |
| git | repo_remove | Mutating | Remove repository registration |
| git | repo_test | Read-only/network | Test repository access |
| git | git_list_repos | Read-only | List Git repositories available through the Git plane |
| git | git_ingest_repo | Mutating | Ingest repository content into reference memory |
| git | git_ingest_file | Mutating | Ingest one repository file into reference memory |
| git | git_write_file | Mutating external | Write a repository file when explicitly invoked and authorized |
| agent | memory.retrieve_context | Read-only | Adapter to Router /v1/context/retrieve |
| agent | memory.reference.search | Read-only | Adapter to Router reference search |
| agent | memory.reference.get | Read-only | Adapter to Router reference get |
| agent | memory.submit_agent_outcome | Mutating | Adapter to Steward structured outcome admission |
| agent | memory.submit_context_feedback | Mutating | Adapter to Steward context feedback |
