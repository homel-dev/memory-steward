# DESIGN PRINCIPLES
## Separation, Bounded Context, and Asynchronous Admission
### Foundational Engineering Specification (Document 11 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 10 (Landscape)](10_industry_landscape.md) | [Next: Document 12 (Extensions)](12_extensions.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Separation of Responsibilities](#1-separation-of-responsibilities)
- [2. Retrieval over Raw History Growth](#2-retrieval-over-raw-history-growth)
- [3. Asynchronous Ordinary-Chat Admission](#3-asynchronous-ordinary-chat-admission)
- [4. Structured Agent Outcomes](#4-structured-agent-outcomes)
- [5. Failure Isolation](#5-failure-isolation)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers and architects
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

[Back to top](#navigation)

---

## 1. Separation of Responsibilities

The Router retrieves and assembles Builder context. The Steward performs durable-memory admission. MCP exposes explicit control/agent operations. LIST is an optional input service. Diagnostics are not treated as learned memory.

[Back to top](#navigation)

---

## 2. Retrieval over Raw History Growth

The Router uses selected static/dynamic/reference context and bounded chat history rather than treating all prior conversation as durable memory.

[Back to top](#navigation)

---

## 3. Asynchronous Ordinary-Chat Admission

Chat response delivery does not wait for ordinary admission completion. The Router dispatches admission asynchronously after the Builder response. Consequently, newly stated facts may not be available to retrieval immediately.

[Back to top](#navigation)

---

## 4. Structured Agent Outcomes

Agents submit structured outcomes/artifacts rather than synthetic chat transcripts. Durable knowledge extraction remains governed by Steward logic; validated reusable artifacts can be persisted separately as `agent_reference`.

[Back to top](#navigation)

---

## 5. Failure Isolation

Best-effort side paths (telemetry, async admission) should not replace a successful primary response merely because their own operation fails. This rule applies only where the code explicitly implements that isolation.

[Back to top](#navigation)

---

## 6. Closing Statement

These principles summarize behavior already visible in the implementation. They guide changes but do not override executable contracts in code, tests, manifests, or API schemas.

[Back to top](#navigation)

---

**END OF DOCUMENT 11**
