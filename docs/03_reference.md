# REFERENCE MEMORY
## Authoritative Retrieval, Versioning, and Injection Mechanics
### Foundational Engineering Specification (Document 03 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 02 (Operational Modes)](02_operational_mode.md) | [cite_start][Next: Document 04 (Optimizations)](04_optimizations.md) →** [cite: 615]

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. [cite_start]Definition and Non-Negotiable Invariants](#1-definition-and-non-negotiable-invariants) [cite: 616]
- [2. [cite_start]What Qualifies as Reference Memory](#2-what-qualifies-as-reference-memory) [cite: 617]
- [3. [cite_start]Logical Separation from Other Memory Types](#3-logical-separation-from-other-memory-types) [cite: 618]
- [4. [cite_start]Metadata Model (Required)](#4-metadata-model-required) [cite: 619]
- [5. [cite_start]Ingestion Workflow (Steward-Owned)](#5-ingestion-workflow-steward-owned) [cite: 620]
- [6. [cite_start]Retrieval Gating (Critical Section)](#6-retrieval-gating-critical-section) [cite: 621]
- [7. [cite_start]Retrieval Flow (Implementation-Grade)](#7-retrieval-flow-implementation-grade) [cite: 622]
- [8. [cite_start]Injection Semantics](#8-injection-semantics) [cite: 623]
- [9. [cite_start]Version Correctness Guarantees](#9-version-correctness-guarantees) [cite: 624]
- [10. [cite_start]Failure Modes and Safe Behavior](#10-failure-modes-and-safe-behavior) [cite: 625]
- [11. Telemetry Requirements](#11-telemetry-requirements)
- [12. [cite_start]Hard Invariants (Reference Memory)](#12-hard-invariants-reference-memory) [cite: 626]
- [13. Relationship to Other Documents](#13-relationship-to-other-documents)
- [14. Closing Statement](#14-closing-statement)
- [15. [cite_start]Amendment: Namespace Clarification](#15-amendment-namespace-clarification) [cite: 627]

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL / CANONICAL
**Audience:** Control-plane architects, Steward/Router implementers
**Depends on:**
- Document 1 — Canonical Memory Architecture
- Document 2 — Operational Modes & Routing Semantics

**Change policy:**
- Append-only
- No silent edits
- Any rule weakening requires explicit justification

[cite_start]This document defines **Reference Memory** at **implementation-grade detail**. [cite: 628]

[Back to top](#navigation)

---

## 1. Definition and Non-Negotiable Invariants

### 1.1 Definition

[cite_start]**Reference Memory** is a curated, authoritative, read-only knowledge corpus used **exclusively for retrieval**. [cite: 629]
It is **not** conversational memory and **not** belief memory.

### 1.2 Hard Invariants

> **Hard Invariant:** Reference Memory MUST:
> - Be explicitly versioned
> - Be explicitly scoped
> - Be read-only at inference time
> - Be retrieval-only
> - Never be treated as “truth” without citation
> - Never silently override static rules

> **Hard Invariant:** Reference Memory MUST NOT:
> - Learn from conversation
> - Accumulate beliefs
> - Mutate dynamically
> - Be injected unconditionally

[cite_start]Violation is a **design error**. [cite: 630]

[Back to top](#navigation)

---

## 2. What Qualifies as Reference Memory

### 2.1 Valid Sources

- Official documentation
- RFCs / specifications
- Internal runbooks
- ADRs
- Vendor manuals
- Versioned API references

### 2.2 Explicit Non-Examples

- Chat transcripts
- Model-generated explanations
- User opinions
- Hypotheses
- One-off notes
- Unverified third-party content

[Back to top](#navigation)

---

## 3. Logical Separation from Other Memory Types

### 3.1 Conceptual Separation

- dynamic_memory → beliefs / learned facts
- reference_memory → sources / lookup material

They never share:
- admission policies
- confidence semantics
- mutation logic

### 3.2 Physical Storage

Reference Memory MAY share infrastructure, but MUST be:
- logically isolated
- metadata-filterable
- gated

[Back to top](#navigation)

---

## 4. Metadata Model (Required)

### 4.1 Mandatory Fields

[cite_start]Each chunk MUST include: [cite: 631]
- product
- version
- source
- scope
- confidence (always high)
- ingested_at
- chunk_id

### 4.2 Optional but Recommended Fields

- provider
- doc_section
- url
- checksum

### 4.3 Metadata Is Used for Filtering, Not Ranking

Metadata:
- selects candidates
- enforces correctness
- prevents version bleed

[cite_start]Vector similarity ranks **only within filtered sets**. [cite: 632]

[Back to top](#navigation)

---

## 5. Ingestion Workflow (Steward-Owned)

### 5.1 Ingestion Is an Explicit Operation

Ingestion is:
- manual or tool-driven
- deliberate
- version-scoped
- auditable

### 5.2 Steward Responsibilities During Ingestion

The Steward MUST:
- validate metadata
- chunk deterministically
- embed
- store in reference namespace
- record provenance

[cite_start]Router has **no role**. [cite: 633]

[Back to top](#navigation)

---

## 6. Retrieval Gating (Critical Section)

### 6.1 Required Gates

All must pass:
1. Mode ∈ {engineering, implementation, formal_spec}
2. Intent indicates lookup
3. Token budget allows
4. Product/version unambiguous

[cite_start]Fail any → **no retrieval**. [cite: 634]

### 6.2 Explicit Non-Gates

Not gated by:
- identity
- popularity
- recency alone

[Back to top](#navigation)

---

## 7. Retrieval Flow (Implementation-Grade)

### 7.1 High-Level Flow

~~~text
User Request
 → Steward classifies mode + intent
 → Router evaluates eligibility
 → Filtered retrieval
 → Minimal chunk selection
 → Injection
~~~

### 7.2 Filtering Order (Strict)

1. Product
2. Version
3. Scope
4. Mode
5. Vector similarity

[Back to top](#navigation)

---

## 8. Injection Semantics

### 8.1 Injection Position

[cite_start]Injected after static rules, before dynamic memory. [cite: 635]

### 8.2 Injection Format

[cite_start]Injected as **attributed excerpts**, never paraphrased. [cite: 636]
~~~text
REFERENCE (Terraform 1.6, official docs):
- ...
~~~

[Back to top](#navigation)

---

## 9. Version Correctness Guarantees

### 9.1 Single-Version Rule

[cite_start]Only one active version per product namespace. [cite: 637]
Ambiguity → abort and ask.

### 9.2 Interaction with Dynamic Memory

Dynamic facts must:
- record version
- degrade confidence if version changes

[Back to top](#navigation)

---

## 10. Failure Modes and Safe Behavior

### 10.1 Missing Reference Data

- no hallucination
- no silent fallback
- ask or proceed without reference

### 10.2 Conflicting References

- surface conflict
- never resolve silently

[Back to top](#navigation)

---

## 11. Telemetry Requirements

Router MUST log:
- retrieval attempts
- chunks selected
- versions
- token cost

[cite_start]Telemetry is observational only. [cite: 638]

[Back to top](#navigation)

---

## 12. Hard Invariants (Reference Memory)

- Never becomes belief
- Never overrides static rules
- Always gated
- Always attributable

[Back to top](#navigation)

---

## 13. Relationship to Other Documents

- Depends on Documents 1 & 2
- Completes canonical set

[Back to top](#navigation)

---

## 14. Closing Statement

[cite_start]Reference Memory restores **determinism** to probabilistic systems. [cite: 639]
Used correctly: force multiplier.
Used incorrectly: poison.

[cite_start]This document defines the line. [cite: 640]

[Back to top](#navigation)

---

## 15. Amendment: Namespace Clarification

[cite_start]The Single-Version Rule applies per **Product Namespace**, not globally. [cite: 641]
One version per namespace is allowed; multiple disjoint namespaces may coexist (e.g., Terraform Core + AWS Provider).
[cite_start]This preserves determinism while enabling real-world dependency graphs. [cite: 642]

---

**END OF DOCUMENT 03**
