
# RUNTIME CONTRACT & OBSERVABILITY
## Environment Variables, C4 Architecture, and Dashboards
### Foundational Engineering Specification (Document 09 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 08 (Verification)](08_verification.md) | [Next: Document 10 (Landscape)](10_industry_landscape.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. System Architecture (C4 Model)](#2-system-architecture-c4-model)
- [3. Request Lifecycle (Sequence)](#3-request-lifecycle-sequence)
- [4. Environment Variable Contract](#4-environment-variable-contract)
- [5. Dashboard Specification](#5-dashboard-specification)
- [7. Log Aggregation Component (Vector)](#7-log-aggregation-component-vector)
- [8. Closing Statement](#8-closing-statement)

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

This document defines the **Physical Architecture** and **Runtime Configuration** of the system.
It replaces ad-hoc READMEs with a strict contract.

[Back to top](#navigation)

---

## 2. System Architecture (C4 Model)

~~~mermaid
graph TD
    User((User))

    subgraph "Memory Steward System"
        UI[AnythingLLM / UI]
        Router[<b>Memory Router</b><br>Orchestrator]
        Steward[<b>Memory Steward</b><br>Admission Controller]
        Builder[<b>Builder LLM</b><br>vLLM / Inference]

        subgraph "Storage"
            DB[(Postgres<br>Canonical)]
            Vector[(Qdrant<br>Index)]
            Logs[(Log Sink<br>PVC)]
        end
    end

    User -->|Chat| UI
    UI -->|OpenAI Protocol| Router
    Router -->|Inference| Builder
    Router -->|Read Static| DB
    Router -->|Search| Vector

    Router -.->|Async Admit| Steward
    Steward -->|Write Dynamic| DB
    Steward -->|Upsert| Vector

    Router -.->|Logs| Logs
    Steward -.->|Logs| Logs
~~~

[Back to top](#navigation)

---

## 3. Request Lifecycle (Sequence)

~~~mermaid
sequenceDiagram
    participant U as User
    participant R as Router
    participant Q as Qdrant
    participant B as Builder
    participant S as Steward

    U->>R: POST /chat/completions
    par Retrieval
        R->>Q: Search (Project ID)
        R->>R: Load Static Rules
    end
    R->>R: Assemble Context
    R->>B: Generate(Prompt)
    B-->>R: Response
    R-->>U: Response

    rect rgb(240, 240, 240)
        Note right of R: Async Admission
        R->>S: Admit(User + Assistant Msg)
        S->>S: Extract Fragments
        S->>Q: Upsert Vector
    end
~~~

[Back to top](#navigation)

---

## 4. Environment Variable Contract

### 4.1 Memory Router
| Variable | Default | Description |
| :--- | :--- | :--- |
| `POSTGRES_DSN` | *Required* | Canonical storage connection. |
| `QDRANT_URL` | `http://qdrant:6333` | Vector store endpoint. |
| `BUILDER_BASE_URL` | *Required* | vLLM / OpenAI inference endpoint. |
| `STEWARD_URL` | *Required* | Async admission endpoint. |
| `MAX_CONTEXT_TOKENS` | `2000` | Safety cap for injection. |

### 4.2 Memory Steward
| Variable | Default | Description |
| :--- | :--- | :--- |
| `MIN_CONFIDENCE` | `0.7` | Threshold for memory persistence. |
| `EMBEDDINGS_URL` | *Required* | Service for vectorization. |

### 4.3 Log Aggregator (Vector) [New]
| Variable | Default | Description |
| :--- | :--- | :--- |
| `LOG_DIR` | `/var/log/memory_steward_logs` | Root directory for persisted logs. |
| `LOG_ROTATE_MAX_SIZE_MB` | `10` | Size threshold for rotation. |
| `LOG_ROTATE_MAX_FILES` | `10` | Max rotated files per log. |
| `LOG_RETENTION_DAYS` | `14` | Age horizon for purge. |
| `LOG_TOTAL_CAP_MB` | `5120` | Global cap for all logs under `LOG_DIR`. |

### 4.4 MCP Diagnostics [New]
| Variable | Default | Description |
| :--- | :--- | :--- |
| `MCP_MAX_LINES` | `1000` | Hard cap for `logs.read`. |
| `MCP_MAX_WINDOW_MINUTES` | `360` | Hard cap for `smart_search` time window. |
| `MCP_RESPONSE_MAX_BYTES` | `524288` | Response size ceiling (bytes). |

[Back to top](#navigation)

---

## 5. Dashboard Specification

Dashboards are powered by the **Diagnostics Plane** (Postgres `telemetry` schema).

### 5.1 Grafana Views (Canonical)
1.  **Router Overview:** RPS, Error Rate, Latency (p95).
2.  **Steward Health:** Admission Lag, Fragments Inserted per Minute.
3.  **Retrieval Quality:** "Zero Candidate" rate (Blind spots).

### 5.2 Verification
~~~sql
-- Check if telemetry is flowing
SELECT count(*) FROM telemetry.request WHERE created_at > now() - interval '1 hour';
~~~

[Back to top](#navigation)

---

## 7. Log Aggregation Component (Vector)

**Component name:** `vector-agent` (DaemonSet)

**Purpose:** Harvest all container logs, persist to PVC, enforce rotation and retention, and expose bounded diagnostics via MCP.

**Contracts**

- **Directories**
  - `LOG_DIR` (default `/var/log/memory_steward_logs`)
- **Rotation / Retention**
  - `LOG_ROTATE_MAX_SIZE_MB` (default **10**)
  - `LOG_ROTATE_MAX_FILES` (default **10**)
  - `LOG_RETENTION_DAYS` (default **14**)
  - `LOG_TOTAL_CAP_MB` (default **5120**)
- **Time**
  - `LOG_TZ` (default cluster timezone) for timestamp normalization

**Kubernetes Resources**
- **DaemonSet:** `vector-agent`
- **ConfigMap:** `vector-config` (immutable pipeline and retention rules)
- **PVC:** `vector-logs` (ReadWriteOnce) mounted at `LOG_DIR`
- **ServiceAccount:** `vector-agent` (read pod metadata only)

[Back to top](#navigation)

---

## 8. Closing Statement

This runtime contract ensures that deployment is deterministic.
If the Env Vars match, the C4 architecture holds true.

---

**END OF DOCUMENT 09**
