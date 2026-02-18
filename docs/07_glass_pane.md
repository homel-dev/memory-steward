
# MANAGEMENT INTERFACE & MCP STRATEGY
## The "Glass Pane": Unified Control via Model Context Protocol
### Foundational Engineering Specification (Document 07 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 06 (Telemetry)](06_telemetry.md) | [Next: Document 08 (Verification)](08_verification.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. Architectural Concept: The Glass Pane](#2-architectural-concept-the-glass-pane)
- [3. Protocol Strategy: MCP Adoption](#3-protocol-strategy-mcp-adoption)
- [4. Tool Taxonomy (The Levers)](#4-tool-taxonomy-the-levers)
- [5. UX Workflows (Assisted Management)](#5-ux-workflows-assisted-management)
- [6. Safety and Permissions](#6-safety-and-permissions)
- [7. Implementation Guidance](#7-implementation-guidance)
- [8. Hard Invariants](#8-hard-invariants)
- [9. Relationship to Other Documents](#9-relationship-to-other-documents)
- [10. Summary](#10-summary)
- [11. Diagnostics: Log Access & Smart Search (MCP)](#11-diagnostics-log-access--smart-search-mcp)
- [12. Closing Statement](#12-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** Core maintainers, operators
**Change policy:**
- Append-only
- No silent edits

[Back to top](#navigation)

---

## 1. Purpose

This document defines the **Management Interface** for the Memory Steward system.
It specifies:
- How operators interact with the Control Plane.
- How memory is ingested, tuned, and debugged.
- The adoption of **Model Context Protocol (MCP)** as the standard interconnect.

This document establishes the **"Glass Pane"**: a unified, natural-language command center that replaces disparate dashboards (SQL viewers, Vector GUIs, Log consoles) with a single, agentic interface.

[Back to top](#navigation)

---

## 2. Architectural Concept: The Glass Pane

### 2.1 Definition

The **Glass Pane** is a "Single Pane of Glass" abstraction that exposes the internal state and levers of the Memory Steward to an authorized Agent.
It is **not** a visual dashboard (React/Web).
It is a **Tool Set** exposed to the Host LLM (e.g., AnythingLLM).

### 2.2 The "ChatOps" Paradigm

Management actions are performed via **Natural Language Commands** in the chat interface.
- **Input:** "Why did you ignore the Terraform docs?"
- **Action:** System calls `explain_last_decision()`.
- **Output:** System renders the telemetry trace directly in the chat.

This unifies **Execution** (The Chat) with **Administration** (The Dashboard).

[Back to top](#navigation)

---

## 3. Protocol Strategy: MCP Adoption

The system adopts the **Model Context Protocol (MCP)** to standardize the "glue" between the Host (Interface) and the Steward (Backend).

### 3.1 Mapping Control Plane to MCP

The Control Plane components defined in Documents 01–06 map to MCP primitives as follows:

| Component | MCP Primitive | Example URI / Signature | Purpose |
| :--- | :--- | :--- | :--- |
| **Static Memory** | **Resource** | `mem://static/global` | Read-only access to immutable rules. |
| **Reference Data** | **Resource** | `ref://{namespace}/{doc_id}` | Direct inspection of chunked knowledge. |
| **Telemetry** | **Resource** | `telemetry://logs/recent` | Pull-only observability logs. |
| **Ingestion** | **Tool** | `ingest_reference(...)` | Active fetching and indexing of documentation. |
| **Configuration** | **Tool** | `set_token_budget(...)` | Runtime tuning of stability parameters. |
| **Mode Logic** | **Prompt** | `mode_selection` | Standardized templates for Steward intent classification. |

### 3.2 Topology

~~~text
[ Host: AnythingLLM / Agent ]
        |
        | (MCP Protocol via Stdio/SSE)
        v
[ MCP Server: steward-mcp ]
   |-- Tools (Ingest, Config, Purge)
   |-- Resources (Static Files, Logs)
   |-- Prompts (System Instructions)
        |
        +--> [ Vector DB (Qdrant) ]
        +--> [ Postgres (Telemetry) ]
        +--> [ Local Filesystem (Static Rules) ]
~~~

[Back to top](#navigation)

---

## 4. Tool Taxonomy (The Levers)

The Glass Pane exposes three distinct categories of tools, aligned with the system planes.

### 4.1 Content Plane Tools (Memory Management)

Tools to manipulate what the system "knows."

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `ingest_reference` | `url`, `product`, `version` | Scrapes, validates, and indexes new documentation. |
| `inspect_memory` | `query`, `namespace` | Debug tool to perform raw vector search and see retrieved chunks. |
| `update_static` | `layer`, `content` | Overwrites `static_global` or `static_mode_conditioned` text. |
| `purge_reference` | `namespace` | **Destructive.** Removes a specific versioned knowledge base. |

### 4.2 Stability Plane Tools (Configuration)

Tools to tune how the system behaves.

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `set_token_budget` | `max_tokens` | Adjusts `context_budget_max` (e.g., raise for GPT-4, lower for local models). |
| `force_mode` | `mode`, `lock` | Overrides the Steward's classifier (e.g., lock to `engineering`). |
| `configure_hysteresis` | `decay_rate` | Tunes the "stickiness" of operational modes. |

### 4.3 Diagnostics Plane Tools (Observability)

Tools to inspect system health and decisions.

| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `get_system_health` | *none* | Returns connectivity status of Vector DB, Postgres, and Embedding service. |
| `get_recent_logs` | `minutes` | Shows recent error rates and latency spikes. |
| `explain_decision` | `request_id` (optional) | Returns the "Blame Trace" for the last request (dropped reasons, scores). |

[Back to top](#navigation)

---

## 5. UX Workflows (Assisted Management)

The Glass Pane enforces **High-Grade** rigor without manual toil via "Assisted" workflows.

### 5.1 The Ingestion Interview (No-Boilerplate)

**Goal:** Ingest documentation without manually writing YAML manifests.

1.  **Trigger:** User pastes a URL. *"Add these docs."*
2.  **Analysis (Agent):** The Agent scrapes the header, detects `Product`, `Version`, and `Scope`.
3.  **Proposal:** Agent displays a "Manifest Card" in chat.
    > "Detected: Kubernetes v1.29 (Implementation). **[ Confirm ]**?"
4.  **Execution:** User confirms. Agent calls `ingest_reference`.
5.  **Result:** System handles chunking, embedding, and atomic aliasing in the background.

### 5.2 Contextual Debugging

**Goal:** Diagnose hallucination or retrieval failure instantly.

1.  **Trigger:** User asks *"Why did you miss the firewall rule?"*
2.  **Execution:** Agent calls `explain_decision()`.
3.  **Result:**
    > "I dropped the firewall chunk because:
    > 1. **Budget:** Static memory took 80% of tokens.
    > 2. **Similarity:** Score (0.72) was below the `high_precision` threshold."

[Back to top](#navigation)

---

## 6. Safety and Permissions

### 6.1 Destructive Action Safeguards

Tools that mutate state (Delete, Update, Purge) MUST:
- Be exposed only to authorized Admin Agents.
- Implement a "Human-in-the-Loop" confirmation parameter where possible.
- Log the `user_id` of the operator performing the action in Telemetry.

### 6.2 Asynchronous Execution

Long-running tools (Ingestion, Re-indexing) MUST NOT block the chat.
- **Pattern:** The Tool returns a "Job Started" signal immediately.
- **Notification:** The System notifies the user upon completion (via a future turn or notification event).

[Back to top](#navigation)

---

## 7. Implementation Guidance

The Glass Pane is implemented as a **FastMCP Server** (Python).

~~~python
# steward_mcp.py (Conceptual)
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Steward-GlassPane")

@mcp.tool()
async def explain_decision() -> str:
    """Explains why specific memories were included or dropped."""
    # Connects to Telemetry Plane [Doc 06]
    return telemetry_service.get_last_blame()

@mcp.tool()
async def ingest_reference(url: str, product: str) -> str:
    """Ingests documentation. Returns Job ID."""
    # Connects to Content Plane [Doc 03]
    job_id = ingestion_queue.add(url, product)
    return f"Job {job_id} started."
~~~

[Back to top](#navigation)

---

## 8. Hard Invariants

> **Hard Invariant:** **No Implicit Writes:** The system never ingests memory without explicit tool invocation and confirmation.
> **Hard Invariant:** **Pull-Only Diagnostics:** Telemetry is never injected into the prompt context unless explicitly requested via `explain_decision`.
> **Hard Invariant:** **Identity Isolation:** The Management Interface uses a distinct `client_id` in telemetry to distinguish Ops actions from User chats.
> **Hard Invariant:** **Atomic Config:** Configuration changes (e.g., Budget) take effect immediately for the next request.

[Back to top](#navigation)

---

## 9. Relationship to Other Documents

- **Consumes Doc 03:** Provides the UI for Reference Memory Ingestion.
- **Consumes Doc 05:** Provides the controls for Stability/Hysteresis tuning.
- **Consumes Doc 06:** Exposes the Telemetry data defined in the Diagnostics Plane.

[Back to top](#navigation)

---

## 10. Summary

The **Glass Pane** transforms the Memory Steward from a "Black Box" into a "Transparent Engine."
By leveraging MCP and ChatOps, it achieves **High-Grade** manageability (audit trails, explicit confirmation, rigorous schemas) with **Consumer-Grade** usability (natural language, zero-boilerplate).

[Back to top](#navigation)

---

## 11. Diagnostics: Log Access & Smart Search (MCP)

The Glass Pane provides operator-grade access to system logs via MCP tools.
Interfaces are **read-only**, time-bounded, and designed for rapid triage and explainability.

### 11.1 Tool: `diagnostics.logs.read`
**Parameters**
- `service` (string; required): One of `memory-router`, `memory-steward`, `memory-steward-mcp`, `embeddings`, `qdrant`, `postgres`, `vllm-builder`, `vllm-steward`, `anythingllm`.
- `lines` (int; default **200**; max **1000**): Tail line count.
- `grep` (string; optional): Substring or RE2 pattern.
- `since` / `until` (RFC 3339; optional): Time window.
- `stream` (`stdout` | `stderr` | `both`; default **both**).

**Returns**
- `service`, `range` (resolved time bounds), `lines[]` (ordered, newest-last), `truncated` (bool).

### 11.2 Tool: `diagnostics.logs.smart_search`
LLM-assisted retrieval and slicing over logs with strict caps.

**Parameters**
- `service` (required), `query` (string), `minutes` (int; default **60**; max **360**).

**Capabilities**
- Pattern clustering (repeated errors, bursts).
- Error-to-cause link hints (e.g., connection refused → upstream health).
- Structured extracts: timestamps, pod, severity.

**Returns**
- `summary`, `clusters[]` (pattern, count, exemplar lines), `snippets[]` (bounded slices), `limits` (caps applied).

### 11.3 Tool: `diagnostics.health.predict`
Heuristic health scoring from recent logs and telemetry.

**Parameters**
- `window_minutes` (default **30**)

**Returns**
- `risk_score` (0–1), `signals[]` (e.g., rotation spikes, write errors), `recommendations[]`.

### 11.4 Safety & Bounds
- All tools are **read-only**.
- Hard caps: `lines ≤ 1000`, `window ≤ 6 h`, response size ≤ 512 KB.
- Secrets redaction MAY be applied at agent or MCP layer.

### 11.5 Operator UX (AnythingLLM)
- A “Diagnostics” panel surfaces: recent errors, tail views per service, and Smart Search with preset windows.
- MCP prompts are issued automatically; operators can refine with `grep`, `since`, `until`.

[Back to top](#navigation)

---

## 12. Closing Statement

The Management Interface transforms the Steward from a passive service into an interactive partner. By exposing safe, bounded tools, we enable the system to participate in its own maintenance and debugging.

---

**END OF DOCUMENT 07**
