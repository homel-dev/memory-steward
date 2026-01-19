# docs/invariants.md

# Memory Steward — System Invariants

## NAVIGATION

- [Top](#memory-steward--system-invariants)
- [1. Model Invariants](#1-model-invariants)
- [2. Static Memory Invariants](#2-static-memory-invariants)
- [3. Dynamic Memory Invariants](#3-dynamic-memory-invariants)
- [4. Admission Invariants](#4-admission-invariants)
- [5. Retrieval Invariants](#5-retrieval-invariants)
- [6. Injection Invariants](#6-injection-invariants)
- [7. Steward Role Invariants](#7-steward-role-invariants)
- [8. Failure Invariants](#8-failure-invariants)
- [9. Scope Invariants](#9-scope-invariants)

---

## 1. Model Invariants

- The reasoning LLM is always stateless.
- The system never assumes prior model memory.
- All continuity is provided externally.

[Back to Top](#memory-steward--system-invariants)

---

## 2. Static Memory Invariants

- Static memory is authoritative.
- Static memory is never embedded.
- Static memory is always injected.
- Static memory is never modified by the Steward.
- Static memory is human-editable and auditable.

Static memory functions as a **constitution**, not recall.

[Back to Top](#memory-steward--system-invariants)

---

## 3. Dynamic Memory Invariants

- Dynamic memory is append-only.
- Dynamic memory entries are atomic.
- Entries are never auto-summarized.
- Entries are never compacted in-place.
- Deletion or compaction requires an explicit, external process.

[Back to Top](#memory-steward--system-invariants)

---

## 4. Admission Invariants

- Nothing is stored without explicit admission.
- Admission is a meta-level decision.
- The Steward never stores raw chats.
- The Steward never stores transcripts.

[Back to Top](#memory-steward--system-invariants)

---

## 5. Retrieval Invariants

- Retrieval happens on every user turn.
- Retrieval is relevance-based.
- Recency is subordinate to relevance.
- Chat and session identifiers are ignored.
- Retrieval may return zero fragments.

[Back to Top](#memory-steward--system-invariants)

---

## 6. Injection Invariants

- Static memory is always injected first.
- Dynamic memory is injected conditionally.
- Injection is bounded and size-aware.
- Dynamic memory may be dropped to preserve static rules.

[Back to Top](#memory-steward--system-invariants)

---

## 7. Steward Role Invariants

- The Steward never generates answers.
- The Steward never executes tools.
- The Steward never reasons about tasks.
- The Steward never rewrites memory.
- The Steward only admits or rejects fragments.

[Back to Top](#memory-steward--system-invariants)

---

## 8. Failure Invariants

- Over-retrieval must degrade gracefully.
- Retrieval failure must not corrupt memory.
- Admission failure must not block execution.
- Memory absence must not cause undefined behavior.

[Back to Top](#memory-steward--system-invariants)

---

## 9. Scope Invariants

- Memory Steward has no execution authority.
- Memory Steward has no planning authority.
- Memory Steward has no supervision authority.

Those responsibilities belong to other systems.

[Back to Top](#memory-steward--system-invariants)

---

END OF DOCUMENT
