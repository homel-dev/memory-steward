# Memory Steward — Storage Model Specification

## DOCUMENT METADATA

- Project: Memory Steward
- Document Type: Canonical Storage Specification
- Status: Canonical (Non-Optional)
- Audience: Engineers, system architects, maintainers
- Non-Goals:
  - Database tuning
  - Vendor-specific optimizations
  - Backup / retention policy

---

## NAVIGATION

- [Top](#memory-steward--storage-model-specification)
- [1. Purpose of This Document](#1-purpose-of-this-document)
- [2. Storage Philosophy](#2-storage-philosophy)
- [3. Static Memory Storage](#3-static-memory-storage)
- [4. Dynamic Memory Storage](#4-dynamic-memory-storage)
- [5. Atomicity and Granularity](#5-atomicity-and-granularity)
- [6. Metadata Semantics](#6-metadata-semantics)
- [7. Explicit Exclusions](#7-explicit-exclusions)
- [8. Auditability Guarantees](#8-auditability-guarantees)
- [9. Lifecycle Boundaries](#9-lifecycle-boundaries)
- [10. Summary](#10-summary)

---

## 1. Purpose of This Document

This document defines **what Memory Steward stores**, **why it stores it**, and **what it explicitly refuses to store**.

It exists to prevent:
- accidental scope creep
- chat-log persistence
- silent summarization
- irreversible memory mutation

This document is **descriptive and restrictive**, not instructional.

[Back to Top](#memory-steward--storage-model-specification)

---

## 2. Storage Philosophy

Memory Steward follows three foundational storage principles:

1. **Atomicity over aggregation**
2. **Retrieval over compression**
3. **Auditability over convenience**

Memory is stored to be:
- individually inspectable
- independently retrievable
- semantically stable over time

[Back to Top](#memory-steward--storage-model-specification)

---

## 3. Static Memory Storage

### Definition

Static memory consists of **authoritative, user-defined rules**.

Examples:
- formatting constraints
- language requirements
- safety rules
- project-wide invariants

### Storage Characteristics

- Stored as plain text or structured configuration
- Version-controlled
- Human-editable
- Not embedded
- Not vectorized

### Lifecycle

- Created and modified **only by humans**
- Never modified by the Steward
- Always injected at prompt assembly time

Static memory functions as **constitutional law**, not recall.

[Back to Top](#memory-steward--storage-model-specification)

---

## 4. Dynamic Memory Storage

### Definition

Dynamic memory consists of **atomic semantic fragments** admitted by the Memory Steward.

These fragments represent:
- decisions
- constraints
- clarifications
- resolved ambiguities

They are **not summaries** and **not transcripts**.

### Storage Characteristics

- One fragment per record
- Embedded into a vector store
- Indexed for semantic retrieval
- Stored append-only

Each fragment is self-contained and meaningful in isolation.

[Back to Top](#memory-steward--storage-model-specification)

---

## 5. Atomicity and Granularity

Dynamic memory entries must satisfy:

- No internal references to “above”, “earlier”, or “previous”
- No reliance on conversational ordering
- No multi-decision bundling

Example (valid):

~~~text
The system must always respond in English.
~~~

Example (invalid):

~~~text
As discussed earlier, we decided to keep the same format.
~~~

Atomicity is mandatory.

[Back to Top](#memory-steward--storage-model-specification)

---

## 6. Metadata Semantics

Dynamic memory entries may include metadata such as:

- project or scope identifier
- creation timestamp
- confidence classification
- optional tags

Metadata is used **only** for:
- retrieval filtering
- relevance weighting
- audit inspection

Metadata must never be used to infer ordering guarantees.

[Back to Top](#memory-steward--storage-model-specification)

---

## 7. Explicit Exclusions

Memory Steward explicitly does **not** store:

- raw chat logs
- full conversation transcripts
- rolling summaries
- condensed histories
- tool outputs
- execution traces

Those belong to other systems.

[Back to Top](#memory-steward--storage-model-specification)

---

## 8. Auditability Guarantees

Every stored memory entry must be:

- human-readable
- traceable to an admission event
- removable only via explicit action

Memory Steward favors:
- explainability
- debuggability
- forensic clarity

[Back to Top](#memory-steward--storage-model-specification)

---

## 9. Lifecycle Boundaries

Memory Steward is responsible for:
- admission
- storage
- retrieval

Memory Steward is **not responsible** for:
- compaction
- summarization
- garbage collection
- retention policy

Those require explicit external processes.

[Back to Top](#memory-steward--storage-model-specification)

---

## 10. Summary

The storage model of Memory Steward is:

- minimal
- explicit
- append-only
- auditable
- semantically stable

This ensures long-term correctness and resistance to drift.

[Back to Top](#memory-steward--storage-model-specification)

---

END OF DOCUMENT
