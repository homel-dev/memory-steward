# INDUSTRY LANDSCAPE
## Background and Architectural Positioning
### Foundational Engineering Specification (Document 10 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 09 (Runtime Contract)](09_runtime_contract.md) | [Next: Document 11 (Design Principles)](11_design_principles.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Positioning](#1-positioning)
- [2. Repository-Specific Differentiators](#2-repository-specific-differentiators)
- [3. Non-Authority](#3-non-authority)
- [4. Closing Statement](#4-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** BACKGROUND
**Audience:** Architects and maintainers
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

This document is rationale, not a runtime contract. Product comparisons age quickly and MUST NOT be used to infer current behavior of third-party systems without fresh source verification.

[Back to top](#navigation)

---

## 1. Positioning

Memory Steward is designed around explicit separation between inference, retrieval, durable-memory admission, operator control, and diagnostics. The implementation favors explicit schemas and bounded storage/retrieval contracts over implicit model-managed persistence.

[Back to top](#navigation)

---

## 2. Repository-Specific Differentiators

Current implementation characteristics include:

- a dedicated Router for context assembly and Builder dispatch;
- a separate Steward admission service;
- explicit canonical reference ingestion through MCP;
- structured AMP retrieval/outcome contracts;
- Postgres-backed structured state and telemetry;
- Qdrant-backed semantic indexes;
- schema-driven MCP operator tooling.

[Back to top](#navigation)

---

## 3. Non-Authority

Claims about MemGPT, Zep, LangChain, or other external projects are not architectural invariants of Memory Steward. If comparative analysis is added, cite current upstream documentation and date the comparison.

[Back to top](#navigation)

---

## 4. Closing Statement

This background document explains Memory Steward’s repository-specific design stance. It MUST NOT be used as authority for third-party product behavior or for unimplemented Memory Steward features.

[Back to top](#navigation)

---

**END OF DOCUMENT 10**
