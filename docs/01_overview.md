# CANONICAL MEMORY ARCHITECTURE
## Memory Steward System
### Foundational Engineering Specification (Document 01 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 00 (Style Guide)](00_style_guide.md) | [Next: Document 02 (Operational Modes)](02_operational_mode.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose of This Document](#1-purpose-of-this-document)
- [2. System Roles and Responsibility Boundaries](#2-system-roles-and-responsibility-boundaries)
- [3. Core Design Principles (Non-Negotiable)](#3-core-design-principles-non-negotiable)
- [4. Canonical Memory Taxonomy](#4-canonical-memory-taxonomy)
- [5. Memory Precedence and Injection Order](#5-memory-precedence-and-injection-order)
- [5.1 Prompt Construction as Enforcement Layer](#51-prompt-construction-as-enforcement-layer)
- [6. Gating Rules (High-Level)](#6-gating-rules-high-level)
- [7. Mutability Matrix (Summary)](#7-mutability-matrix-summary)
- [8. Hard Invariants (Must Never Be Violated)](#8-hard-invariants-must-never-be-violated)
- [9. Relationship to Other Documents](#9-relationship-to-other-documents)
- [10. Closing Statement](#10-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL / CANONICAL
**Audience:** System architects, control-plane implementers, future maintainers
**Change policy:**
- This document is **append-only**
- Existing sections may only be amended by explicit revision notes
- Silent or implicit changes are forbidden

This document defines the **canonical memory architecture** for the **Memory Steward** system. [cite_start]All other documents, implementations, and behaviors **must conform** to it. [cite: 586, 587]

[Back to top](#navigation)

---

## 1. Purpose of This Document

This document defines:
- What *kinds* of memory exist in the system
- Their lifetimes, mutability, and authority
- Who is allowed to read/write each memory type
- Gating and precedence rules between memory layers
- Hard invariants that must never be violated

This document **does not** define:
- Concrete modes
- Concrete routing logic
- Concrete products or technologies
- Implementation details

[cite_start]Those belong to Documents 2 and 3. [cite: 588]

[Back to top](#navigation)

---

## 2. System Roles and Responsibility Boundaries

### 2.1 Router (Memory Router)
**Role:** Prompt assembly and request orchestration

**Authority:**
- Reads memory
- Injects memory into prompts
- Enforces token budgets
- Writes telemetry only

**Forbidden:**
- Deciding memory classification
- Deciding what should be remembered long-term
- [cite_start]Mutating memory content [cite: 589]

### 2.2 Steward (Memory Steward)
**Role:** Memory governance and classification

**Authority:**
- Decides memory type
- Decides confidence levels
- Decides write eligibility
- Classifies operational mode
- Manages reference memory metadata

**Forbidden:**
- Prompt assembly
- Model-facing behavior shaping
- [cite_start]Overriding Router invariants [cite: 589]

### 2.3 Model (LLM Backend)
**Role:** Stateless inference engine

**Authority:** None

The model:
- Does not own memory
- Does not decide memory rules
- Does not decide modes
- Does not mutate system behavior

[cite_start]Models are replaceable components. [cite: 590]

[Back to top](#navigation)

---

## 3. Core Design Principles (Non-Negotiable)

### 3.1 Control Plane vs Data Plane
- Router + Steward form the **control plane**
- LLM inference is the **data plane**

[cite_start]All rules live in the control plane. [cite: 591]

### 3.2 Explicit Over Implicit
- No silent behavior changes
- No inferred contracts
- No hidden priorities

[cite_start]If a rule exists, it must be documented. [cite: 592]

### 3.3 Memory Is Not a Monolith
Different memories have:
- Different lifetimes
- Different trust levels
- Different mutation rules

[cite_start]They must never be conflated. [cite: 593]

[Back to top](#navigation)

---

## 4. Canonical Memory Taxonomy

### 4.1 Static Global Memory
*ID: `static_global`*

**Definition:**
[cite_start]Immutable, always-on rules and invariants. [cite: 594]

**Characteristics:**
- Injected into every prompt
- Highest precedence
- Extremely small
- Human-authored
- Rarely changed

**Examples:**
- Language constraints
- Interaction contracts
- Formatting rules
- Safety and non-negotiable behavior

**Mutability:**
[cite_start]Manual change only, explicit review required. [cite: 595]

### 4.2 Static Mode-Conditioned Memory
*ID: `static_mode_conditioned`*

**Definition:**
[cite_start]Static instruction blocks applied **only under specific operational modes**. [cite: 596]

**Key invariant:**
Selected by **mode**, not by topic.

### 4.3 Reference Memory
*ID: `reference_memory`*

**Definition:**
[cite_start]Authoritative, external, read-only knowledge corpora. [cite: 597]

**Critical invariant:**
Provides **sources**, not beliefs.

### 4.4 Dynamic Memory
*ID: `dynamic_memory`*

**Definition:**
[cite_start]Learned, conversation-derived facts, decisions, or preferences. [cite: 598]

**Written only by:** Steward

### 4.5 Telemetry
*ID: `telemetry`*

**Definition:**
Write-only operational observability data.

[cite_start]Telemetry is **not memory** in the cognitive sense. [cite: 599]

[Back to top](#navigation)

---

## 5. Memory Precedence and Injection Order

1. static_global
2. static_mode_conditioned
3. Session-local constraints
4. reference_memory
5. dynamic_memory
6. User message

[cite_start]Lower layers must never override higher layers. [cite: 600]

[Back to top](#navigation)

---

## 5.1 Prompt Construction as Enforcement Layer

Memory precedence is a conceptual rule set. Prompt construction is its mechanical enforcement.

The Router enforces canonical memory ordering by assembling prompts according to this document.
The Model never enforces memory hierarchy.
The Steward never assembles Builder prompts.

Prompt construction is therefore part of the control-plane contract, not an implementation accident.

[Back to top](#navigation)

### 5.1.1 Dual Prompt Species (Builder vs Steward)

The system defines two ontologically distinct prompt types:

1. Builder Prompt
2. Steward Prompt

They are not variants of the same template. They serve different planes and MUST remain isolated.

> **Hard Invariant:** Builder and Steward prompts MUST NOT share structural templates.
> **Hard Invariant:** A single model invocation MUST NOT serve both Builder and Steward roles simultaneously.

**Builder Prompt**
- Purpose: generate user-facing responses.
- Assembled by: Router.
- Consumed by: Builder LLM.
- MUST reflect canonical memory precedence.

**Steward Prompt**
- Purpose: classification, extraction, and memory governance.
- Assembled by: Router (for Steward).
- Consumed by: Steward LLM.
- MUST NOT include conversational behavior rules intended for Builder.

This separation preserves the Data Plane / Control Plane boundary defined in Section 3.

[Back to top](#navigation)

### 5.1.2 Canonical Builder Prompt Layer Order

The Builder prompt MUST respect the canonical injection order defined in Section 5.

The semantic order is:

1. `static_global`
2. `static_mode_conditioned` (if applicable)
3. Session-local constraints
4. `reference_memory` (gated)
5. `dynamic_memory` (gated)
6. User message

Lower layers MUST NOT override higher layers.

The Router MUST preserve this ordering independent of provider serialization format.

[Back to top](#navigation)

### 5.1.3 Canonical Steward Prompt Structure

The Steward prompt serves a different objective and therefore follows a distinct structure.

The semantic components are:

1. Steward system instructions (classification / extraction rules)
2. Relevant recent conversation turns (bounded)
3. Optional dynamic lookup context (gated)
4. Explicit task objective (e.g., classify mode, extract atomic facts)

The Steward prompt MUST NOT:
- Inject `static_global` interaction rules intended for conversational shaping.
- Inject reference memory unless explicitly required for validation logic.
- Contain Builder behavioral instructions.

The Steward exists to govern memory, not to generate conversation.

[Back to top](#navigation)

---

## 6. Gating Rules (High-Level)

Memory inclusion is gated by:
- Operational mode
- Confidence
- Recency
- Token budget
- Explicit user constraints

[cite_start]Not all available memory is injected. [cite: 601]

[Back to top](#navigation)

---

## 7. Mutability Matrix (Summary)

| Memory Type | Read | Write | Who Writes | Injected |
| :--- | :--- | :--- | :--- | :--- |
| static_global | Yes | Rare | Human | Always |
| static_mode_conditioned | Yes | Rare | Human | Mode |
| reference_memory | Yes | Yes* | Human/Tool | Gated |
| dynamic_memory | Yes | Yes | Steward | Gated |
| telemetry | Yes | Yes | System | Never |

[cite_start]\* Ingestion, not learning. [cite: 602, 603, 604, 605, 606, 607, 608, 609, 610, 611]

[Back to top](#navigation)

---

## 8. Hard Invariants (Must Never Be Violated)

- Model never decides memory rules
- Router never decides what is remembered
- Steward never assembles prompts
- Reference memory is never belief
- Static memory is never silently changed
- Existing contracts are immutable without approval
- Builder and Steward prompts are separate species and MUST NOT be merged.
- A single model invocation MUST NOT serve both Builder and Steward roles simultaneously.
- Prompt assembly MUST preserve canonical memory precedence order.
- Steward prompts MUST NOT contain conversational shaping rules intended for Builder.
- Builder prompts MUST NOT contain extraction/classification rules intended for Steward.

[cite_start]Violation is a **system design error**. [cite: 612]

[Back to top](#navigation)

---

## 9. Relationship to Other Documents

- Document 2: operational modes and routing logic
- Document 3: reference memory mechanics
- Document 6: telemetry and observability

[cite_start]If there is a conflict, **this document wins**. [cite: 613]

[Back to top](#navigation)

---

## 10. Closing Statement

This architecture prevents:
- Prompt chaos
- Memory poisoning
- Behavioral drift
- Configuration entropy

[cite_start]This is a **cognitive control plane**, not a chatbot. [cite: 614]

---

**END OF DOCUMENT 01**
