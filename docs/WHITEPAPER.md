
# BEYOND RAG: ARCHITECTING DETERMINISM
## The Memory Steward Engineering Manifesto

---

## 1. Abstract

Standard Retrieval-Augmented Generation (RAG) is failing production engineering. By relying on summarization, implicit context, and probabilistic storage, traditional RAG systems suffer from "context drift" and hallucination loops.

**Memory Steward** introduces a dual-plane architecture that treats memory as a **deterministic control system**, not a chat log. We propose a separation of concerns: a **Data Plane** for conversation and a **Control Plane** for memory governance, bridged by strict operational modes and an atomic persistence strategy.

---

## 2. The Problem: The "Alignment Tax" of Memory

Current LLM memory systems typically rely on two flawed mechanisms:

1. **Summarization:** Compressing conversation history into smaller prompts. This loses nuance and creates a "telephone game" effect where facts degrade over time.
2. **Implicit Injection:** Dumping "relevant" chunks into the context window without validating their utility or truth.

We call this **"Probabilistic Drift."** When the model is responsible for deciding what to remember, it creates a feedback loop of its own biases. To solve this, we must remove the "decision to remember" from the "act of chatting."


---

## 3. The Solution: Dual-Plane Architecture

Memory Steward splits the system into two distinct active components, separating the "act of speaking" from the "act of remembering."

### 3.1 The Data Plane (Memory Router)

The fast, stateless "receptionist." It handles user I/O, performs read-only vector search, and assembles the prompt. **Crucially, it never writes to long-term memory.**

The UI layer (AnythingLLM UI) is a presentation surface only and is not a source of truth, does not own memory, and does not participate in memory admission decisions.
The Builder LLM is used strictly as an inference backend and has no memory authority or persistence rights.

### 3.2 The Control Plane (Memory Steward)

The slow, thoughtful "librarian." It observes the chat asynchronously. It decides what facts are worth keeping, sanitizes them, and injects them into the database. **Crucially, it never speaks to the user.**

The Memory Steward acts as an explicit admission controller: it governs memory writes and never participates in prompt generation or user interaction.

### 3.3 C4 Container Diagram

~~~mermaid
graph TD
    User((User))
    UI[AnythingLLM UI - Non-authoritative]

    subgraph "Data Plane"
        Router[Memory Router]
        Builder[Builder LLM - Inference Backend]
    end

    subgraph "Control Plane"
        Steward[Memory Steward - Admission Controller]
    end

    subgraph "Persistence Layer"
        DB[(Postgres)]
        Qdrant[(Qdrant)]
        Logs[(Vector Agent - Log & Telemetry Sink)]
    end

    classDef plain fill:#ffffff,stroke:#333333,stroke-width:1px;
    classDef data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px;
    classDef control fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef store fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;

    class User,UI plain;
    class Router,Builder data;
    class Steward control;
    class DB,Qdrant,Logs store;

    User -->|1. Chat| UI
    UI -->|2. Fast Path| Router
    Router -->|3a. Read| DB
    Router -->|3b. Search| Qdrant
    Router -->|4. Generate| Builder
    Builder -->|Response| Router
    Router -->|5. Reply| UI

    Router -.->|Async Signal| Steward
    Steward -->|Persist| DB
    Steward -->|Upsert| Qdrant
    Steward -.->|Audit| Logs
~~~

---

## 4. The Async Lifecycle (Hot vs. Cold Paths)

To maintain low latency for the user while performing expensive memory operations (fact extraction, embedding, indexing), the system relies on an asynchronous admission pattern.

As shown below, the user receives their response *before* the system even begins to process the memory of that turn.

### 4.1 Request Sequence Diagram

~~~mermaid
sequenceDiagram
    participant U as User
    participant UI as UI
    participant R as Memory Router
    participant B as Builder LLM
    participant S as Memory Steward
    participant DB as Postgres / Qdrant

    rect rgb(227,242,253)
        note right of U: Hot Path (Synchronous)
        U->>UI: Chat Input
        UI->>R: Forward Request
        par Retrieval
            R->>DB: Query Context
            R->>R: Load Static Rules
        end
        R->>B: Generate Prompt
        B-->>R: Response
        R-->>UI: Final Answer
        UI-->>U: Reply
    end

    rect rgb(255,243,224)
        note right of R: Cold Path (Asynchronous)
        R->>)S: Fire-and-Forget Signal
        S->>S: Extract Atomic Facts
        S->>DB: Upsert Memory
    end
~~~

---

## 5. Philosophy: Atomicity & Operational Modes

### 5.1 Atomicity Over Aggregation

Most systems store "summaries." Memory Steward stores **Atoms**: discrete, immutable facts.

- **Example:** *"Project ID is 994"* (Atom) vs. *"The user talked about their project"* (Summary)
- **Result:** A self-healing knowledge graph, not a muddy log file.

### 5.2 Operational Modes & Hysteresis

A chat system should behave differently when debugging code vs. brainstorming ideas. The system detects intent and switches modes (e.g., **Engineering** vs. **Casual**).

To prevent "Mode Jitter," the system employs **Hysteresis**: a temporal decay function that resists changing modes unless the signal is overwhelming.

[Back to top](#navigation)

---

## 6. The "Glass Pane": ChatOps for Memory

Black-box AI systems are a liability. Memory Steward implements a **Management Interface** via the **Model Context Protocol (MCP)**. This allows operators to inspect, debug, and tune the Steward using natural language.

### 6.1 MCP Topology Diagram

~~~mermaid
graph TD
    Operator[Operator Agent]

    subgraph "The Glass Pane - MCP Server"
        MCP[steward-mcp]
        T1[Tool: ingest_reference]
        T2[Tool: set_token_budget]
        T3[Tool: explain_decision]
        R1[mem://static/global]
        R2[telemetry://logs/recent]
    end

    classDef plain fill:#ffffff,stroke:#333333,stroke-width:1px;
    classDef tool fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef res fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;

    class Operator,MCP plain;
    class T1,T2,T3 tool;
    class R1,R2 res;

    Operator <==>|MCP Protocol| MCP
    MCP --> T1
    MCP --> T2
    MCP --> T3
    MCP --> R1
    MCP --> R2

    T1 -->|Scrape| Qdrant[(Qdrant)]
    T3 -->|Query| Postgres[(Postgres)]
    R2 -.->|Tail| Logs[(Vector Agent)]
~~~
---

## 7. Closing Statement

Memory Steward is not a "better RAG." It is a rejection of RAG's laziness. By enforcing strict contracts, async admission, and deterministic operational modes, we transform the LLM from a probabilistic toy into a reliable engineering component.

We don't just "remember" things. We **steward** them.
