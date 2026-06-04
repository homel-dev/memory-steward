# AUDITED ADMISSION CONTROL & CONTEXT TRANSPARENCY

## Deterministic Gates, Steward–Auditor Asymmetry, Failure Memory, and Context Diff

### Foundational Engineering Specification (Candidate Document 13)

*Namespace: memory-steward • Owner: architecture-team*

-----

## Navigation

**← [Prev: Document 12 (Extensions)](12_extensions.md) | [Related: Document 01 (Architecture)](01_overview.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. The Admission Pipeline (Overview)](#2-the-admission-pipeline-overview)
- [3. Deterministic Gates (Pre-LLM Filter)](#3-deterministic-gates-pre-llm-filter)
- [4. Steward–Auditor Informational Asymmetry](#4-stewardauditor-informational-asymmetry)
- [5. Deterministic Decision Policy (LLM as Observation)](#5-deterministic-decision-policy-llm-as-observation)
- [6. Failure Memory](#6-failure-memory)
- [7. Context Diff (Assembly Transparency)](#7-context-diff-assembly-transparency)
- [8. Telemetry Requirements](#8-telemetry-requirements)
- [9. Hard Invariants](#9-hard-invariants)
- [10. Relationship to Other Documents](#10-relationship-to-other-documents)
- [11. Closing Statement](#11-closing-statement)

-----

## 0. Status, Scope, and Authority

**Status:** DRAFT (additive; requires architecture-team ratification before CANONICAL)
**Audience:** Control-plane architects, Steward implementers, operators
**Depends on:**

- Document 01 — Canonical Memory Architecture
- Document 02 — Operational Modes & Routing Semantics
- Document 06 — Telemetry & Observability
- Document 07 — Glass Pane (MCP Management)

**Change policy:**

- Append-only
- No silent edits
- This document is **additive**: it MUST NOT weaken any invariant in Documents 00–12

This document is DRAFT, not CANONICAL. It touches admission semantics (Steward authority) and therefore MUST be ratified by the architecture-team before any rule here is treated as binding. Until then it is a specification proposal, not enforcement.

[Back to top](#navigation)

-----

## 1. Purpose

This document specifies four retained capabilities that harden memory admission and make context assembly transparent:

1. **Deterministic Gates** — cheap, LLM-free admission filtering that runs first.
1. **Steward–Auditor Asymmetry** — a skeptical second pass that is *more informed but less generative* than the Steward.
1. **Failure Memory** — a first-class record of what was tried and rejected, and why.
1. **Context Diff** — a structured account of what changed in assembled context, and why.

These capabilities are additive. They do not introduce new memory write authorities, do not move the Steward off the write path, and do not inject diagnostics into prompts.

[Back to top](#navigation)

-----

## 2. The Admission Pipeline (Overview)

```text
Conversation / Event
        ↓
   Steward (proposer)           ← sees LOCAL evidence only
        ↓
   Candidate
        ↓
   Deterministic Gates          ← LLM-free; cheap reject/hold
        ↓ (only survivors)
   Auditor (skeptic)            ← sees BROADER historical evidence
        ↓
   Deterministic Decision Policy
        ↓
 Admit | Hold | Reject | Quarantine
```

> **Hard Invariant:** No LLM in this pipeline writes memory directly. Both Steward and Auditor emit structured candidates/verdicts; the final write decision is made by deterministic policy (Section 5).

> **Hard Invariant:** The Steward remains the sole authority that performs memory writes, as defined in Document 01. The Auditor MUST NOT write memory and MUST NOT mutate candidates.

[Back to top](#navigation)

-----

## 3. Deterministic Gates (Pre-LLM Filter)

### 3.1 Principle

The cheapest correct rejection MUST happen before any model runs. Most low-quality candidates can be eliminated by deterministic checks, eliminating most of the need for an LLM review pass.

### 3.2 Required Gates (Strict Order)

A candidate MUST pass all of the following before the Auditor is invoked:

1. **Schema validity** — candidate conforms to the canonical candidate shape (Section 4.3).
1. **Scope validity** — `scope` is a known bounded value (`user`, `project`, `global`).
1. **Minimum evidence** — `evidence_count >= MIN_EVIDENCE` (default **2**).
1. **Non-duplication** — candidate is not a byte-equal or normalized-equal duplicate of an already-admitted fact.
1. **Not-recently-rejected** — candidate does not match an entry in Failure Memory (Section 6) within `REJECT_COOLDOWN`.

Fail any gate → deterministic outcome (`reject` or `hold`), **no LLM invoked**.

### 3.3 Example

```text
candidate:  "user prefers D2"
evidence_count: 1
MIN_EVIDENCE:   2
→ reject (deterministic, no Auditor call)
```

> **Hard Invariant:** Gate failures MUST be recorded with a bounded drop-reason code (aligned to Document 06 drop accounting). No silent drops.

[Back to top](#navigation)

-----

## 4. Steward–Auditor Informational Asymmetry

### 4.1 Core Idea

The Steward and the Auditor perform **different cognitive tasks** and MUST receive **different inputs**.

- **Steward asks:** “What does this mean?” (extraction, classification, scoping)
- **Auditor asks:** “Are you sure?” (sufficiency of support, overreach, contradiction)

The asymmetry is deliberate: the Auditor is *more informed and more skeptical*, not smarter or more creative.

### 4.2 Input Asymmetry

|Input                                    |Steward|Auditor|
|:----------------------------------------|:-----:|:-----:|
|Current message                          |Yes    |Yes    |
|Recent conversation window               |Yes    |Yes    |
|Active constraints / project profile     |Yes    |Yes    |
|Admission history                        |No     |Yes    |
|Rejection history                        |No     |Yes    |
|Contradiction history                    |No     |Yes    |
|Failure Memory (prior tried-and-rejected)|No     |Yes    |

The Auditor sees institutional history the Steward never sees. This makes the Auditor a memory of the system’s own past decisions, not a second reasoner over the same evidence.

### 4.3 Candidate Shape (Steward Output)

```json
{
  "candidate_type": "constraint | preference | project_fact | decision | observation",
  "claim": "string",
  "scope": "user | project | global",
  "evidence": ["string"],
  "evidence_count": 0,
  "confidence": 0.0,
  "ttl": "string | null",
  "supersedes": []
}
```

### 4.4 Verdict Shape (Auditor Output)

The Auditor emits a small, structured verdict. It MUST NOT emit prose, rewritten claims, or new candidates.

```json
{
  "verdict": "admit | retry | hold | reject",
  "confidence": 0.0,
  "flags": ["insufficient_evidence", "possible_overgeneralization", "contradicts_prior"]
}
```

### 4.5 Retry and Quarantine Discipline

> **Hard Invariant:** The Auditor MUST NOT trigger an immediate in-loop Steward retry. Immediate retries risk a hallucination → repair → repair loop.

- A `retry` verdict returns only bounded `retry_reason` flags to the Steward for **one** additional attempt.
- After `MAX_ATTEMPTS` (default **3**) without admission, the candidate is **quarantined**, not deleted.
- Quarantined candidates are retained for later Observer review; they often represent ambiguous, contradictory, or novel signals.

[Back to top](#navigation)

-----

## 5. Deterministic Decision Policy (LLM as Observation)

### 5.1 Principle

The LLM provides **observations**. The **policy decides**. The verdict is computed deterministically from a score, not asserted by a model.

### 5.2 Scoring Model (Reference; Implementation MUST Be Explicit)

```text
evidence_count          0 .. 30
temporal_consistency    0 .. 20
cross_session_support   0 .. 20
user_explicitness       0 .. 30
contradictions        -30 .. 0
---------------------------------
score = sum (clamped 0 .. 100)
```

### 5.3 Thresholds (Config-Driven)

```text
score >= 70   → admit
40 .. 69      → hold (queue for review)
score < 40    → reject
```

The Auditor’s `confidence` and `flags` MAY adjust inputs to the score but MUST NOT bypass the threshold policy.

> **Hard Invariant:** The admit/hold/reject boundary is deterministic and reproducible from stored inputs. Two identical input sets MUST yield identical decisions.

[Back to top](#navigation)

-----

## 6. Failure Memory

### 6.1 Definition

**Failure Memory** is an append-only record of candidates and approaches that were *tried and rejected*, and the reason. It is the inverse of conventional memory, which stores only what worked.

### 6.2 Why It Matters

Coding agents and operators repeatedly re-propose approaches that were already rejected. Storing rejections cheaply prevents re-litigation and is high-value context for downstream consumers.

### 6.3 Record Shape

```json
{
  "attempted": "string (claim or approach)",
  "outcome": "rejected | quarantined | superseded",
  "reason": "string (bounded, non-sensitive)",
  "scope": "user | project | global",
  "recorded_at": "RFC3339"
}
```

### 6.4 Rules

- Failure Memory is **logically isolated** from dynamic memory (separate namespace).
- It is **append-only**; entries are never silently edited.
- It is consulted by the deterministic gates (Section 3.2, gate 5) and visible to the Auditor (Section 4.2).
- It MUST NOT store raw chat text, secrets, or identity beyond the bounded `reason`.

[Back to top](#navigation)

-----

## 7. Context Diff (Assembly Transparency)

### 7.1 Definition

On every context assembly, the Router MAY emit a structured diff describing how the assembled context changed relative to the prior assembly for the same session/consumer.

### 7.2 Diff Shape

```json
{
  "added":   [{"ref": "string", "why": "string"}],
  "removed": [{"ref": "string", "why": "string"}],
  "changed": [{"ref": "string", "why": "string"}]
}
```

### 7.3 Rules

- The Context Diff is a **Diagnostics Plane** artifact. It is **pull-only** and MUST NOT be injected into the Builder prompt (preserves Document 06 telemetry invariant).
- It plugs into the existing Glass Pane `explain_decision` surface (Document 07) and answers: “Why am I seeing this context now?”
- `why` fields MUST use bounded reason codes, not raw content.

[Back to top](#navigation)

-----

## 8. Telemetry Requirements

All four capabilities reuse the canonical telemetry schema (Document 06). No parallel telemetry schema is permitted.

The pipeline MUST record, per candidate:

- Gate outcomes and drop-reason codes.
- Auditor verdict, confidence, and flags.
- Computed score and resulting decision.
- Quarantine events and attempt counts.

> **Hard Invariant:** Telemetry remains write-only by default and pull-only on exposure. No admission telemetry is injected into chat context.

[Back to top](#navigation)

-----

## 9. Hard Invariants

- The Steward remains the sole memory writer; the Auditor never writes and never mutates candidates.
- Deterministic gates run before any LLM; the cheapest correct rejection happens first.
- The final admit/hold/reject decision is deterministic policy over a score, not an LLM assertion.
- No immediate in-loop retries; quarantine after `MAX_ATTEMPTS`.
- Failure Memory is append-only and logically isolated from dynamic memory.
- Context Diff is pull-only Diagnostics Plane data and is never injected into prompts.
- This document is additive and MUST NOT weaken any invariant in Documents 00–12.

[Back to top](#navigation)

-----

## 10. Relationship to Other Documents

- **Extends Document 01:** adds an admission pipeline downstream of the Steward without changing write authority or precedence.
- **Aligns with Document 02:** gates are consistent with mode/intent gating; mode is not re-decided here.
- **Reuses Document 06:** all counters, drop reasons, and exposure rules follow the existing telemetry canon.
- **Surfaces via Document 07:** Context Diff and verdict traces are exposed through the Glass Pane, not new dashboards.

[Back to top](#navigation)

-----

## 11. Closing Statement

These four capabilities convert admission from a single-model judgment into a governed, auditable pipeline: deterministic filtering first, a skeptical and better-informed reviewer second, a deterministic policy as the final arbiter, and a transparent record of both rejections and context changes. They add rigor without granting any new authority — which is the only kind of addition this architecture permits.

-----

**END OF DOCUMENT 13 (DRAFT)**
