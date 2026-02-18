# RFC: DUAL-PLANE ARCHITECTURE
## Deterministic LLM Memory
### Foundational Engineering Specification (Root Document)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Architecture Cheat Sheet](ARCHITECTURE_CHEAT_SHEET.md) | [Next: Contributing](CONTRIBUTING.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Abstract](#1-abstract)
- [2. Motivation](#2-motivation)
- [3. The Standard: "Dual-Plane" Requirements](#3-the-standard-dual-plane-requirements)
- [4. Reference Implementation](#4-reference-implementation)
- [5. Security Considerations](#5-security-considerations)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** PROPOSAL (Request for Comments)
**Audience:** AI Systems Engineering
**Category:** Standards Track / System Architecture
**Date:** January 2026
**Change policy:**
- Append-only
- No silent edits

[Back to top](#navigation)

---

## 1. Abstract

This RFC proposes a standard architecture for managing long-term memory in production LLM applications. It addresses the "Probabilistic Drift" inherent in traditional RAG systems by enforcing a strict separation of concerns: a synchronous **Read-Only Data Plane** for user interaction and an asynchronous **Write-Exclusive Control Plane** for memory governance.

[Back to top](#navigation)

---

## 2. Motivation

Current "Chat with Doc" implementations suffer from three critical failures in production:
1. **Latency Penalty:** RAG ingestion and summarization slow down the user loop.
2. **Context Corruption:** LLMs implicitly "forget" or hallucinate when context windows fill with irrelevant summaries.
3. **Lack of Observability:** Memory is treated as a black box log rather than a managed database.

This proposal argues that memory must be treated as a **Control System**, not a chat log.

[Back to top](#navigation)

---

## 3. The Standard: "Dual-Plane" Requirements

To comply with this standard, a system must adhere to the following contracts:

### 3.1 Separation of Planes
> **Hard Invariant:** **The Data Plane** (Router) MUST handle all User I/O and MUST NOT possess write permissions to the canonical memory store.
> **Hard Invariant:** **The Control Plane** (Steward) MUST handle all memory mutations (CRUD) and MUST NOT possess a direct interface to the user.

### 3.2 Asynchronous Admission
- Memory ingestion MUST occur out-of-band (asynchronously) relative to the chat response.
- The system MUST return a `200 OK` to the user *before* beginning the "Analysis & Extraction" phase.

### 3.3 Atomic Fact Storage
- Systems SHOULD store data as "Atomic Facts" (discrete assertions) rather than raw conversation dumps or summaries.
- Each memory atom MUST carry a `confidence` score and `scope` (e.g., `user`, `project`, `global`).

[Back to top](#navigation)

---

## 4. Reference Implementation

A fully compliant reference implementation, **Memory Steward**, is available for review.
- **Repository:** [Link to your repo]
- **Architecture:** Kubernetes / Python / Qdrant / Postgres
- **License:** MIT (Proposed)

[Back to top](#navigation)

---

## 5. Security Considerations

- **Prompt Injection:** By isolating the Control Plane, prompt injection attacks in the Data Plane cannot directly corrupt long-term memory, as the Steward sanitizes inputs asynchronously.
- **Privilege Escalation:** The Data Plane (Router) operates with Read-Only database credentials, mitigating exfiltration risks.

[Back to top](#navigation)

---

## 6. Closing Statement

This RFC establishes the baseline requirements for preventing context corruption and ensuring high-grade engineering determinism in memory-augmented LLM architectures.

---

**END OF DOCUMENT RFC_PROPOSAL**
