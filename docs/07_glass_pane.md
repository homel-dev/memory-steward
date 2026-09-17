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
  - [2.1 Open WebUI `/glap`](#21-open-webui-glap)
  - [2.2 Terminal inside Kubernetes](#22-terminal-inside-kubernetes)
  - [2.3 Glass Pane TUI](#23-glass-pane-tui)
  - [2.4 Local MCP-capable clients](#24-local-mcp-capable-clients)
- [3. Complete MCP Tool Contract](#3-complete-mcp-tool-contract)
  - [3.1 Content plane](#31-content-plane)
  - [3.2 Stability/config plane](#32-stabilityconfig-plane)
  - [3.3 Diagnostics plane](#33-diagnostics-plane)
  - [3.4 Git/repository plane](#34-gitrepository-plane)
  - [3.5 Agent plane](#35-agent-plane)
- [4. MCP Resources](#4-mcp-resources)
- [5. Glass Pane TUI Runtime Contract](#5-glass-pane-tui-runtime-contract)
  - [5.1 Launch and connectivity](#51-launch-and-connectivity)
  - [5.2 Schema-driven form generation](#52-schema-driven-form-generation)
  - [5.3 Keyboard and focus model](#53-keyboard-and-focus-model)
  - [5.4 Theme model](#54-theme-model)
  - [5.5 Validation and result rendering](#55-validation-and-result-rendering)
- [6. Reference-Memory Operator Workflow](#6-reference-memory-operator-workflow)
- [7. `/glap` ChatOps Bridge](#7-glap-chatops-bridge)
- [8. Tool Safety and Authority](#8-tool-safety-and-authority)
- [9. Authentication and Network Posture](#9-authentication-and-network-posture)
- [10. Troubleshooting Workflow](#10-troubleshooting-workflow)
- [11. MCP and TUI Change Checklist](#11-mcp-and-tui-change-checklist)
- [12. Verification](#12-verification)
- [13. Current Limits](#13-current-limits)
- [14. Closing Statement](#14-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers, operators, agent-runtime integrators, and TUI maintainers
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

This document defines the implemented Memory Steward MCP management surface and its supported clients, including the Textual Glass Pane TUI.

The checked-in MCP server, client implementation, Kubernetes/Task configuration, and executable tests are authoritative for current behavior. The live MCP schema remains authoritative for exact tool argument types and required/optional fields.

[Back to top](#navigation)

---

## 1. Architecture

`memory-steward-mcp` is a FastMCP HTTP server in namespace `ms`. Kubernetes exposes it as the internal Service `memory-steward-mcp` on TCP/8081. Routine operator access does not require a public ingress.

~~~mermaid
graph LR
    Operator[Operator terminal]
    LocalClient[Local MCP client]
    TUI[steward-tui ephemeral Pod]
    WebUI[Open WebUI /glap]
    Agent[Agent runtime]
    MCP[memory-steward-mcp]
    Router[memory-router]
    Steward[memory-steward]
    PG[(Postgres)]
    Q[(Qdrant)]

    Operator -->|kubectl exec / Task wrappers| MCP
    LocalClient -->|loopback port-forward| MCP
    TUI -->|ClusterIP Service :8081| MCP
    WebUI -->|Router MCP bridge| MCP
    Agent -->|MCP| MCP
    MCP -->|AMP retrieval adapters| Router
    MCP -->|AMP outcome/feedback adapters| Steward
    MCP -->|operator state/config/diagnostics| PG
    MCP -->|reference ingestion/inspection| Q
~~~

The live MCP tool schemas are the command contract. Clients MUST discover or consume those schemas rather than maintain a divergent hard-coded command API.

[Back to top](#navigation)

---

## 2. Clients

### 2.1 Open WebUI `/glap`

Memory Router intercepts `/glap` commands and delegates to its MCP bridge. The bridge queries the live MCP tool list and current schemas for command discovery and argument requirements.

### 2.2 Terminal inside Kubernetes

~~~bash
task ops:mcp:tools
task ops:mcp:tools:json
task ops:mcp:call -- ref_list
task ops:ref:inspect -- product=kicad version=9.0 limit=10
~~~

The Task wrappers invoke FastMCP from the deployed cluster context. The workstation does not need a separate Python/FastMCP environment for these operations.

### 2.3 Glass Pane TUI

~~~bash
task tui
~~~

`task tui` launches `ghcr.io/homel-dev/memory-steward/steward-tui:latest` as an ephemeral interactive Pod in namespace `ms` and injects:

~~~text
STEWARD_MCP_URL=http://memory-steward-mcp:8081/mcp/
~~~

The TUI talks directly to the internal MCP Service. This path does not use host Docker, host Python, or an MCP port-forward.

### 2.4 Local MCP-capable clients

For a separately installed local MCP client:

~~~bash
task ops:mcp:forward
## http://127.0.0.1:8081/mcp
~~~

The port-forward is loopback-only. This local-client path is separate from `task tui`.

[Back to top](#navigation)

---

## 3. Complete MCP Tool Contract

The table below reflects the tools registered by the current MCP implementation. Exact runtime argument schemas MUST still be discovered from MCP `list_tools`.

### 3.1 Content plane

| Tool | Class | Purpose |
| --- | --- | --- |
| `ref_ingest_url` | Mutating | Queue durable background ingestion of a reference URL |
| `ref_ingest_text` | Mutating | Ingest operator-provided reference text |
| `ref_ingest_status` | Read-only | Inspect one durable URL-ingestion job and progress |
| `ref_ingest_jobs` | Read-only | List recent durable URL-ingestion jobs |
| `ref_ingest_cancel` | Mutating | Cancel queued work or request cancellation between batches |
| `ref_ingest_retry` | Mutating | Explicitly requeue failed/cancelled work |
| `ref_list` | Read-only | List recorded Reference Memory ingestion namespaces/events |
| `ref_inspect` | Read-only | Inspect stored reference chunks by exact metadata |
| `ref_purge` | Destructive | Delete canonical reference chunks for an explicit product/version |
| `static_list` | Read-only | List Postgres static-memory rows |
| `static_create` | Mutating | Create static memory |
| `static_update` | Mutating | Update a static-memory row |
| `static_toggle` | Mutating | Enable or disable static memory |
| `static_delete` | Destructive | Permanently delete a static-memory row |
| `cache_control` | Process-local | Refresh or evict the MCP process-local `StaticMemoryCacheManager` |

`cache_control` does not clear Router request-path state. The current Router reads static memory from Postgres and does not use the MCP process-local `StaticMemoryCacheManager`.

### 3.2 Stability/config plane

| Tool | Class | Purpose |
| --- | --- | --- |
| `config_set_budget` | Mutating | Persist `MAX_CONTEXT_TOKENS`; Router consumes this runtime key |
| `config_force_mode` | Compatibility | Persist `FORCE_MODE`; no current Router/Steward policy consumer |
| `config_set_hysteresis` | Compatibility | Persist `HYSTERESIS_WINDOW`; no current hysteresis engine |
| `config_show` | Read-only | Show persisted runtime configuration and current-consumer annotations |

Persisting a compatibility key does not imply active runtime behavior.

### 3.3 Diagnostics plane

| Tool | Class | Purpose |
| --- | --- | --- |
| `diag_health` | Read-only | Check Qdrant, Postgres, embeddings, LIST, and Router connectivity/state |
| `diag_explain` | Read-only | Read the telemetry blame trace for a request ID |
| `diag_explain_last` | Read-only | Explain the most recent telemetry request |
| `diag_metrics` | Read-only | Summarize bounded request/retrieval/admission/step metrics |
| `diag_qdrant_stats` | Read-only | Show Qdrant collection status and counts by memory type |
| `dyn_inspect` | Read-only | Inspect dynamic-memory rows for a project |
| `dyn_simulate_retrieval` | Read-only | Run a diagnostic dense Qdrant lookup for a project/query |

`dyn_simulate_retrieval` is a diagnostic candidate lookup. It is not a bit-for-bit reproduction of the Router's complete retrieval, MMR, and token-budget pipeline.

### 3.4 Git/repository plane

| Tool | Class | Purpose |
| --- | --- | --- |
| `repo_add` | Mutating | Register or replace repository connection metadata/credentials |
| `repo_list` | Read-only | List registered repository connections |
| `repo_remove` | Mutating | Remove a repository connection |
| `repo_test` | Read-only/network | Test a configured provider connection |
| `git_list_repos` | Read-only | List repositories visible through a connection |
| `git_ingest_repo` | Mutating | Ingest matching repository files into Reference Memory |
| `git_ingest_file` | Mutating | Ingest one repository file into Reference Memory |
| `git_write_file` | Mutating external | Create or update a repository file when the connection is `read-write` |

The current provider adapters cover GitLab, GitHub, and Bitbucket. Connection credentials are persisted by the Git-plane implementation. The MCP service therefore belongs on a trusted internal operator boundary.

### 3.5 Agent plane

| Tool | Class | Purpose |
| --- | --- | --- |
| `memory.retrieve_context` | Read-only | Delegate governed structured retrieval to Router `/v1/context/retrieve` |
| `memory.reference.search` | Read-only | Delegate canonical Reference Memory semantic search to Router |
| `memory.reference.get` | Read-only | Delegate exact reference-chunk fetch to Router |
| `memory.submit_agent_outcome` | Mutating | Delegate structured agent outcome admission/persistence to Steward |
| `memory.submit_context_feedback` | Mutating | Delegate retrieval-quality feedback to Steward |

`memory.retrieve_context` accepts optional `reference_filters`. The current agent adapter forwards caller-provided filters to Router and does not synthesize product/version narrowing when they are absent.

AMP handlers are transport adapters. They MUST NOT independently reimplement Router retrieval policy or Steward admission policy.

[Back to top](#navigation)

---

## 4. MCP Resources

The current server registers one explicit MCP resource:

- `diagnostics://contract` — JSON view of selected runtime/diagnostic values from `diagnostics_plane.py`.

The repository does not currently register historical conceptual `mem://...`, `ref://...`, or telemetry resource families. Memory and Reference Memory inspection are tool operations in the current implementation.

[Back to top](#navigation)

---

## 5. Glass Pane TUI Runtime Contract

The repository contains `components/steward_tui`, a Textual MCP client. It is a presentation layer over the live MCP contract, not a second management API.

### 5.1 Launch and connectivity

The repository-supported path is:

~~~bash
task tui
~~~

The Task:

1. removes a stale `steward-tui` Pod if one exists;
2. runs a new interactive Pod in namespace `ms`;
3. uses the published `steward-tui` image;
4. sets `STEWARD_MCP_URL=http://memory-steward-mcp:8081/mcp/`;
5. attaches the operator terminal to the Pod;
6. removes the Pod when the interactive run exits.

The client code retains `http://127.0.0.1:8081/mcp` as its fallback URL when `STEWARD_MCP_URL` is not set. That fallback supports explicitly local launches; `task tui` overrides it with the in-cluster Service URL.

### 5.2 Schema-driven form generation

At startup the TUI calls FastMCP `Client.list_tools()` and converts each live tool input schema into `ToolField` objects.

Implemented dynamic field types are:

- `string`;
- `integer`;
- `number`;
- `boolean`;
- `object`;
- `array`.

For FastMCP optional unions such as `dict[str, str] | None`, the client selects the supported concrete JSON type from `anyOf`.

Object and array values are entered as JSON text and decoded before invocation. Invalid JSON or a decoded value with the wrong container type is rejected client-side.

### 5.3 Keyboard and focus model

The current interaction path is:

~~~text
TUI starts
  -> tool list receives focus
  -> operator selects a tool with Enter
  -> form is rebuilt from the live schema
  -> first required field receives focus
  -> Tab / Shift+Tab navigate the form
  -> Ctrl+Enter invokes the selected tool
  -> Esc returns focus to the tool list
~~~

The current application bindings are:

| Key | Action |
| --- | --- |
| `q` | Quit |
| `r` | Refresh live tool inventory |
| `Esc` | Return focus to tool list |
| `Ctrl+Enter` | Invoke current tool |
| `F2` | Open Textual theme chooser |

The footer is generated from these bindings.

### 5.4 Theme model

The TUI uses Textual's theme system.

At mount time it reads:

~~~text
STEWARD_TUI_THEME
~~~

If the variable is absent, the default theme is:

~~~text
nord
~~~

If the requested theme is not registered, the TUI falls back to `nord`.

`F2` invokes Textual's theme search/chooser at runtime. The current implementation does not define a separate Memory Steward theme registry or persist the selected theme outside the running TUI process.

### 5.5 Validation and result rendering

Required fields are derived from the live JSON Schema.

When coercion fails:

- the invalid widget receives the `input-error` class;
- focus moves to that widget;
- the result pane reports the validation error;
- the MCP call is not sent.

For valid input, the client calls:

~~~text
Client.call_tool(..., raise_on_error=False)
~~~

Result rendering prefers structured content, falls back to text content blocks, and keeps tool-returned errors in the result pane instead of terminating the TUI.

The headless Textual tests cover:

- tool selection;
- focus on the first required field;
- `Tab` navigation across required fields;
- invalid required-field focus/error styling;
- `Ctrl+Enter` invocation;
- `Esc` returning focus to the tool list.

[Back to top](#navigation)

---

## 6. Reference-Memory Operator Workflow

Reference ingestion is explicit. URL ingestion is durable and asynchronous; raw-text and Git ingestion remain synchronous but are resource-bounded.

~~~bash
## Discover the live schema first.
task ops:mcp:tools:json

## List current reference ingestion records.
task ops:ref:list

## Inspect one product/version.
task ops:ref:inspect -- product=kicad version=9.0 limit=10

## Queue an authoritative URL.
task ops:ref:ingest:url -- url=https://example.invalid/docs product=kicad version=9.0 scope=pcb

## Follow durable ingestion state.
task ops:ref:ingest:jobs
task ops:ref:ingest:status -- job_id=<uuid>

## Search canonical Reference Memory through the Router-owned agent adapter.
task ops:ref:search -- project_id=operator query="hierarchical sheet syntax"

## Destructive: the wrapper prompts before purge.
task ops:ref:purge -- product=kicad version=9.0
~~~

For multiline/raw text ingestion, use `ops:mcp:call` with the live FastMCP schema rather than inventing client-side argument syntax.

[Back to top](#navigation)

---

## 7. `/glap` ChatOps Bridge

Memory Router recognizes user input beginning with `/glap` and delegates command interpretation to its MCP bridge.

The bridge discovers live MCP tools and schemas. It MUST NOT maintain a second authoritative tool contract.

Streaming chat requests wrap the `/glap` result in the Router's SSE-compatible response path.

`/glap` is an optional conversational operator surface. It is not the MCP protocol itself.

[Back to top](#navigation)

---

## 8. Tool Safety and Authority

Read-only tools may still expose sensitive operational information.

Mutating and destructive operations MUST remain explicit and auditable. In particular:

- `ref_purge` deletes canonical reference chunks for an explicit product/version;
- `static_delete` permanently deletes a static-memory row;
- `git_write_file` mutates an external repository and requires a `read-write` connection;
- repository connection records contain provider credentials and belong on a trusted internal boundary;
- `ref_ingest_url` queues work; `reference-ingest-worker` performs the server-side URL fetch and therefore has SSRF/egress implications.

The MCP transport layer MUST NOT be treated as the authority for Router retrieval policy or Steward admission policy.

[Back to top](#navigation)

---

## 9. Authentication and Network Posture

The supported topology keeps `memory-steward-mcp` internal as a ClusterIP Service.

`task tui` runs inside namespace `ms` and connects directly to the Service. A public MCP ingress is not required for routine TUI operation.

Separately installed local MCP clients MAY use the loopback-only `task ops:mcp:forward` path.

Cross-namespace clients require an explicit network-policy allowance. Authentication/authorization hardening, credential rotation, and tool-level authorization MUST be explicit before MCP is exposed beyond trusted cluster/local boundaries.

[Back to top](#navigation)

---

## 10. Troubleshooting Workflow

When an MCP/TUI operation fails:

1. run `task ops:service:status`;
2. run `task ops:diag:health`;
3. run `task ops:mcp:tools:json` to verify live discovery;
4. for `task tui`, verify that the temporary `steward-tui` Pod can reach `memory-steward-mcp:8081`;
5. for a separately installed local client, verify the loopback port-forward;
6. inspect MCP logs;
7. inspect Router or Steward health for agent-adapter tools;
8. distinguish protocol/connectivity failures from tool-returned application errors;
9. compare the live tool schema with the TUI-generated fields before changing client-side logic.

A tool-returned application failure may be rendered as a normal result because the TUI invokes FastMCP with `raise_on_error=False`.

[Back to top](#navigation)

---

## 11. MCP and TUI Change Checklist

A new or changed MCP tool requires:

- exact tool name and plane classification;
- input-schema validation;
- mutation/safety classification;
- explicit backend authority;
- component test coverage;
- Task/TUI impact review;
- this document's tool-contract update.

A TUI behavior change requires:

- live-schema compatibility review;
- focus/navigation behavior review;
- keyboard binding review;
- validation/error-state review;
- theme behavior review when visual tokens or theme selection change;
- headless Textual test coverage;
- `task tui`/network-path verification;
- this document's TUI contract update.

[Back to top](#navigation)

---

## 12. Verification

The implementation-level checks for this document include the MCP component tests and the `steward_tui` headless tests.

For operator verification:

~~~bash
task ops:mcp:tools:json
task ops:diag:health
task tui
~~~

For the TUI, verify at minimum:

1. the live tool list loads;
2. selecting `ref_ingest_url` focuses `url`;
3. `Tab` advances through `product` and `version`;
4. an omitted required field is highlighted and focused;
5. `Ctrl+Enter` invokes a valid form;
6. `Esc` returns to the tool list;
7. `F2` opens the theme chooser;
8. object fields such as `reference_filters` accept valid JSON objects and reject invalid JSON.

[Back to top](#navigation)

---

## 13. Current Limits

The current implementation has these explicit limits:

- the TUI renders schemas dynamically but does not implement specialized widgets for every JSON-Schema keyword;
- enum metadata is carried in `ToolField` but the current form renderer does not expose a dedicated enum selector;
- object and array fields use JSON text entry rather than structured nested editors;
- theme choice is process-local; there is no Memory Steward theme persistence layer;
- the MCP service has no public-ingress requirement for supported operator workflows;
- authentication/authorization hardening remains a deployment concern beyond the current trusted internal boundary;
- `config_force_mode` and `config_set_hysteresis` persist compatibility values without active Router/Steward consumers;
- `dyn_simulate_retrieval` is diagnostic and does not reproduce the complete Router retrieval pipeline.

[Back to top](#navigation)

---

## 14. Closing Statement

`memory-steward-mcp` is the single schema-driven operator and agent control surface. Task wrappers, the in-cluster Glass Pane TUI, Open WebUI `/glap`, local MCP clients, and agent adapters consume the same live MCP schemas rather than defining parallel command contracts.

[Back to top](#navigation)

---

**END OF DOCUMENT 07**
