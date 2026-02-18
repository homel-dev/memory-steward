`
# ARCHITECTURE CHEAT SHEET
## Control Plane • Async Admission • Atomic Persistence
### Foundational Engineering Specification (Root Document)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: README](README.md) | [Next: RFC Proposal](RFC_PROPOSAL.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. The System Map (C4 Container)](#1-the-system-map-c4-container)
- [2. The Runtime Contract](#2-the-runtime-contract)
- [3. The Async Lifecycle (Timing)](#3-the-async-lifecycle-timing)
- [4. The Glass Pane (ChatOps)](#4-the-glass-pane-chatops)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** System Operators and Maintainers
**Change policy:**
- Append-only
- No silent edits

[Back to top](#navigation)

---

## 1. The System Map (C4 Container)

*The strict separation between "Thinking" (Router) and "Remembering" (Steward).*

~~~mermaid
graph TD
    User((User))
    UI[AnythingLLM UI]

    subgraph "Data Plane (Read-Only)"
        Router[Memory Router]
        Builder[Builder LLM]
    end

    subgraph "Control Plane (Write-Only)"
        Steward[Memory Steward]
    end

    subgraph "Persistence"
        DB[(Postgres)]
        Qdrant[(Qdrant)]
    end

    %% Styling
    classDef plain fill:#fff,stroke:#333,stroke-width:1px;
    classDef data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef control fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef store fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    class User,UI plain;
    class Router,Builder data;
    class Steward control;
    class DB,Qdrant store;

    User --> Router
    Router -->|Read| Qdrant
    Router -.->|Async Signal| Steward
    Steward -->|Write| Qdrant
    Steward -->|Metadata| DB
~~~

[Back to top](#navigation)

---

## 2. The Runtime Contract

### 2.1 Environmental Constraints

| Variable | Description |
| :--- | :--- |
| `MEMORY_MODE` | Defines strictness (`engineering` vs `casual`). |
| `TOKEN_BUDGET` | Hard cap on context injection to prevent overflow. |
| `ASYNC_TIMEOUT` | Max duration for Steward analysis before abortion. |

### 2.2 Database Roles

- **Qdrant:** Semantic Search (Vectors). High-speed retrieval.
- **Postgres:** Canonical Truth (Metadata). Relational integrity.
- **Vector Agent:** Telemetry & Logs. Observability sink.

> **Hard Invariant (Golden Rule):** The Router *never* writes. The Steward *never* speaks.

[Back to top](#navigation)

---

## 3. The Async Lifecycle (Timing)

*Ensuring the "Cost of Remembering" is never paid by the user.*

~~~mermaid
sequenceDiagram
    participant U as User
    participant R as Router
    participant S as Steward
    participant Q as Qdrant

    rect rgb(227, 242, 253)
        note right of U: THE HOT PATH (Sync)
        U->>R: Chat Request
        R->>U: Reply (200 OK)
    end

    rect rgb(255, 243, 224)
        Note right of R: THE COLD PATH (Async)
        R->>S: Fire-and-Forget Signal
        S->>S: Extract Atomic Facts
        S->>Q: Upsert Memory
    end
~~~

[Back to top](#navigation)

---

## 4. The Glass Pane (ChatOps)

*The MCP Interface for Operators to debug and tune the system.*

### 4.1 MCP Tools (The Levers)

1.  **`ingest_reference`**
    - **Action:** Force-feed documentation chunks.
    - **Target:** Qdrant (Reference Memory).
2.  **`set_token_budget`**
    - **Action:** Tune retrieval density on the fly.
    - **Target:** Runtime Config.
3.  **`explain_decision`**
    - **Action:** Debug "Why did the system say that?"
    - **Target:** Postgres Telemetry Tables.

[Back to top](#navigation)

---

## 5. Closing Statement

This cheat sheet serves as an operational quick-reference for the core invariants, interactions, and diagnostic tooling defined by the Memory Steward Canonical Architecture.

---

**END OF DOCUMENT ARCHITECTURE_CHEAT_SHEET**
