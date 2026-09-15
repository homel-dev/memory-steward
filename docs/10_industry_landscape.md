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

## 4. Architectural Pattern Comparison

This section is background, not a claim about competitors or a normative runtime contract.

### 4.1 Chat-history accumulation

A common baseline is to keep adding prior turns until a model context window or summarizer intervenes. The advantage is implementation simplicity; the disadvantages are unbounded relevance decay, token growth, and weak authority separation.

Memory Steward instead treats history as one bounded input and uses explicit memory/evidence lanes. This does not imply that every application needs a control plane of this complexity; it reflects the repository's target use case: engineering/agent workloads where provenance and mutation authority matter.

### 4.2 Generic vector-memory stores

A vector store can provide useful semantic recall but does not by itself answer:

- who is allowed to write;
- whether the content is learned belief or authoritative reference;
- how deterministic artifacts are selected;
- how static policy outranks recalled facts;
- how an operator inspects or deletes a specific lane.

Memory Steward layers those concerns around Postgres/Qdrant rather than treating similarity search as the entire memory architecture.

### 4.3 Agent artifact stores

Engineering agents often emit structured artifacts that should be reusable without semantic rewriting. The `agent_reference` lane follows that pattern: deterministic artifacts remain exact and queryable by selectors, while optional extracted durable knowledge follows Steward admission.

### 4.4 Control-plane operator interfaces

The FastMCP control surface and Textual TUI are examples of schema-driven operations rather than a bespoke second REST management API. The benefit is one live tool schema shared across CLI, TUI, ChatOps bridge, and agents.

## 5. Tradeoff Matrix

| Architectural choice | Benefit | Cost / tradeoff |
| --- | --- | --- |
| Separate Router and Steward | Clear read/assemble vs write/admit authority | More services and failure boundaries |
| Postgres + Qdrant | Structured canonical state plus semantic retrieval | Cross-store operational consistency |
| Explicit Reference Memory | Version/provenance control | Requires ingestion lifecycle |
| Agent artifact lane | Deterministic reuse | Additional schema and selector semantics |
| Async ordinary admission | Protects response latency | No durable queue/retry guarantee today |
| MCP internal control plane | Shared schema across clients | Requires careful mutation authorization |
| Caller-supplied mode | Deterministic/simple current behavior | No automatic posture inference |

## 6. Evaluation Questions for Alternative Designs

When comparing another memory architecture to this repository, ask:

1. What is the unit of durable knowledge?
2. Who has write authority?
3. How are authoritative sources separated from learned facts?
4. Is retrieval semantic, deterministic, or both?
5. What is the precedence order when sources disagree?
6. How are token/context budgets enforced?
7. Can operators explain why an item was selected?
8. Can they delete or quarantine one lane without destroying all state?
9. Are structured agent outputs preserved exactly?
10. Does a background model silently change policy?
11. Which failures block user-facing inference?
12. Which claims are implementation vs proposal?

## 7. Scope Limitations

This document does not attempt to rank commercial products or declare a universal best architecture. The repository is optimized around self-hosted control, explicit authority, inspectability, and integration with agent workflows. Other systems may reasonably optimize for hosted simplicity, low operational burden, or consumer personalization instead.

---

## 4. Closing Statement

This background document explains Memory Steward’s repository-specific design stance. It MUST NOT be used as authority for third-party product behavior or for unimplemented Memory Steward features.

[Back to top](#navigation)

---

**END OF DOCUMENT 10**
