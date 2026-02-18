# INDUSTRY LANDSCAPE & ARCHITECTURAL POSITIONING
## Why Memory Steward is Not "Just Another RAG"
### Foundational Engineering Specification (Document 10 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 09 (Runtime)](09_runtime_contract.md) | [Next: Document 11 (Design)](11_design_principles.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. The RAG Failure Pattern](#2-the-rag-failure-pattern)
- [3. Comparative Analysis](#3-comparative-analysis)
- [4. Unique Architectural Stance](#4-unique-architectural-stance)
- [5. Closing Statement](#5-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** Core maintainers, system architects
**Change policy:**
- Append-only
- No silent edits

[Back to top](#navigation)

---

## 1. Purpose

This document justifies the architectural existence of Memory Steward.
It serves as a defense against regression into simpler, failure-prone designs.

[Back to top](#navigation)

---

## 2. The RAG Failure Pattern

Standard RAG systems fail because they rely on:
1.  **Summarization:** Compressing history loses detail and nuance irreversibly.
2.  **Model-Driven Storage:** Letting the model decide what to keep leads to "ego bias" and hallucination loops.
3.  **Implicit Context:** Mixing chat logs with factual memory pollutes the knowledge base.

Memory Steward explicitly **rejects** all three.

[Back to top](#navigation)


---

## 3. Comparative Analysis

### 3.1 vs. MemGPT
* **MemGPT:** The reasoning model manages its own memory (OS-style).
* **Risk:** The model can hallucinate its own operating instructions.
* **Steward:** Memory is managed by a separate **Control Plane**. The reasoning model is a guest, not the admin.

### 3.2 vs. Zep
* **Zep:** heavily relies on summarization chains.
* **Risk:** Semantic drift over time ("Telephone game").
* **Steward:** Uses **Atomic Fragmentation**. Original facts are preserved verbatim, never re-summarized.

[Back to top](#navigation)

---

## 4. Unique Architectural Stance

Memory Steward is defined by its invariants:
* **Admission before Persistence:** Nothing enters DB without a decision.
* **Retrieval before Injection:** Context is a query result, not a window.
* **Atomicity over Aggregation:** Facts are stored as discrete units.

[Back to top](#navigation)

---

## 5. Closing Statement

Memory Steward is not a chatbot framework.
It is a **Cognitive Control Plane** designed to impose determinism on probabilistic systems.

---

**END OF DOCUMENT 10**
