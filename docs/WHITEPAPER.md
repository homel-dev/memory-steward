# BEYOND CHAT HISTORY
## Memory Steward Architecture Note
### Background Architecture Note
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 13 (Admission Control Proposal)](13_admission_control.md) | [Next: README](../README.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Problem](#1-problem)
- [2. Implemented Separation](#2-implemented-separation)
- [3. Memory Classes](#3-memory-classes)
- [4. Asynchronous Ordinary-Chat Admission](#4-asynchronous-ordinary-chat-admission)
- [5. Operational Mode: Current Reality](#5-operational-mode-current-reality)
- [6. Operator Surface](#6-operator-surface)
- [7. Engineering Principle](#7-engineering-principle)
- [8. Closing Statement](#8-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** BACKGROUND
**Audience:** Architects, maintainers, evaluators
**Change policy:** Living background note; implementation claims MUST match the current tree.

This paper explains the architecture without creating runtime requirements beyond the checked-in code and tests.

[Back to top](#navigation)

---

## 1. Problem

Long-running LLM and agent workloads need durable context without treating an ever-growing transcript as the memory database. Memory Steward separates retrieval, inference, durable-memory admission, explicit reference ingestion, operator control, and diagnostics so each has a bounded contract.

[Back to top](#navigation)

---

## 2. Implemented Separation

~~~mermaid
graph TD
    Client[Client / Open WebUI]
    Agent[Agent]
    Router[memory-router]
    Builder[Builder LLM]
    Steward[memory-steward]
    MCP[memory-steward-mcp]
    PG[(Postgres)]
    Q[(Qdrant)]

    Client --> Router
    Router --> PG
    Router --> Q
    Router --> Builder
    Router -.-> Steward
    Agent --> Router
    Agent --> MCP
    MCP --> Router
    MCP --> Steward
    Steward --> PG
    Steward --> Q
~~~

The Router owns retrieval/context assembly and Builder dispatch. The Steward owns durable learned-memory admission and structured agent outcomes. MCP is an internal schema-driven operator/agent surface. Postgres carries canonical structured state; Qdrant carries semantic indexes.

[Back to top](#navigation)

---

## 3. Memory Classes

Memory Steward distinguishes:

- static operator-managed rules;
- dynamic Steward-admitted learned fragments;
- canonical Reference Memory explicitly ingested through MCP;
- structured `agent_reference` artifacts from agents/analyzers/tools;
- telemetry and feedback, which are diagnostics rather than learned memory.

This separation is more important than whether any individual retrieval technique is called RAG.

[Back to top](#navigation)

---

## 4. Asynchronous Ordinary-Chat Admission

The chat path returns the Builder result without waiting for ordinary admission. The Router then dispatches `/admit` to Memory Steward in a daemon thread. The system therefore accepts a short consistency window between a user statement and its availability as retrieved dynamic memory.

[Back to top](#navigation)

---

## 5. Operational Mode: Current Reality

The current implementation does not detect operational mode and does not implement hysteresis. `mode` is optional caller-supplied metadata used by Router selection logic. Persisted `FORCE_MODE` and `HYSTERESIS_WINDOW` compatibility keys have no current runtime consumer.

Any future classifier/hysteresis implementation must land with code and tests before it is described as active behavior.

[Back to top](#navigation)

---

## 6. Operator Surface

Memory Steward MCP exposes live tools. Open WebUI `/glap` is one client; terminal FastMCP commands are another. The server is kept internal to the cluster for normal operation, and local clients can use loopback-only `kubectl port-forward`.

The current MCP server is tool-oriented; this paper does not claim unimplemented MCP resources or prompts.

[Back to top](#navigation)

---

## 7. Engineering Principle

Determinism here means explicit authority, schemas, filters, budgets, idempotency, and observable decisions around probabilistic models. It does not mean that LLM inference itself becomes deterministic.

[Back to top](#navigation)

---

## 8. Closing Statement

Memory Steward is defined by explicit runtime boundaries: governed retrieval, separate durable-memory admission, schema-driven MCP control, and diagnostics that do not masquerade as learned memory. Architectural claims in this note remain subordinate to the implementation.

[Back to top](#navigation)

---

**END OF DOCUMENT WHITEPAPER**
