# OPERATIONAL MODES & ROUTING SEMANTICS
## Mode Classification, Decision Authority, and Routing Logic
### Foundational Engineering Specification (Document 02 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 01 (Architecture)](01_overview.md) | [Next: Document 03 (Reference)](03_reference.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. What a “Mode” Is (and Is Not)](#1-what-a-mode-is-and-is-not)
- [2. Minimal Mode Set (Deliberately Small)](#2-minimal-mode-set-deliberately-small)
- [3. Authority: Who Decides the Mode](#3-authority-who-decides-the-mode)
- [4. Mode Decision Signals](#4-mode-decision-signals)
- [5. Mode Transitions](#5-mode-transitions)
- [6. Routing Effects of Mode](#6-routing-effects-of-mode)
- [7. Prompt Assembly Contract (Mode-Aware)](#7-prompt-assembly-contract-mode-aware)
- [8. Failure Modes and Safe Defaults](#8-failure-modes-and-safe-defaults)
- [9. Implementation Guidance (Non-Code)](#9-implementation-guidance-non-code)
- [10. Hard Invariants (Mode System)](#10-hard-invariants-mode-system)
- [11. Relationship to Other Documents](#11-relationship-to-other-documents)
- [12. Closing Statement](#12-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL / CANONICAL
**Audience:** Control-plane architects, Router/Steward implementers
**Depends on:** Document 1 (Canonical Memory Architecture)
**Change policy:**
- Append-only
- No silent edits
- Mode additions require explicit justification

[cite_start]This document defines **operational modes**, **who decides them**, and **how they affect routing, memory gating, and prompt assembly**. [cite: 282, 283]

[Back to top](#navigation)

---

## 1. What a “Mode” Is (and Is Not)

### 1.1 Definition
[cite_start]An **operational mode** is a classification of the user’s **cognitive / problem-solving posture**, not subject matter. [cite: 284]
A mode answers:
> “How should the system behave right now?”

It does **not** answer:
- What product is being discussed
- What technology is involved
- What data should be retrieved

### 1.2 Explicit Non-Goals
Modes are **not**:
- Topics (e.g., Terraform, AWS, Chemistry)
- Tags for retrieval ranking
- User personas

[cite_start]Modes influence **rules**, not **facts**. [cite: 285]

[Back to top](#navigation)

---

## 2. Minimal Mode Set (Deliberately Small)

[cite_start]The system must start with a **minimal, stable set**. [cite: 286]

### 2.1 Canonical Initial Modes
The recommended initial set:
1. engineering
2. implementation
3. brainstorming
4. formal_spec
5. casual

[cite_start]No additional modes may be introduced without evidence they cannot be expressed via these. [cite: 287]

### 2.2 Mode Semantics (High-Level)
| Mode | Primary Traits |
| :--- | :--- |
| engineering | rigor, correctness, constraints, tradeoffs |
| implementation | code, diffs, APIs, production-grade patterns |
| brainstorming | hypothesis allowed, alternatives, exploration |
| formal_spec | definitions, invariants, precise language |
| casual | lightweight, no heavy contracts |
[cite_start][cite: 288, 289, 290, 291, 292]

[Back to top](#navigation)

---

## 3. Authority: Who Decides the Mode

### 3.1 Steward Is the Sole Authority
[cite_start]Only **Memory Steward** may decide or change the active mode. [cite: 293]
The Router:
- consumes the mode
- never infers the mode

The Model:
- has no awareness of mode logic
- cannot request or change modes

### 3.2 Mode Decision Is Classification, Not Retrieval
Mode decision is:
- deterministic
- stateless (per request, with context)
- based on signals

[cite_start]It does **not** use vector similarity. [cite: 294]

[Back to top](#navigation)

---

## 4. Mode Decision Signals

The Steward may use the following **signals**, weighted but deterministic:

### 4.1 Linguistic Signals
- verbs: implement, wire, refactor, design
- nouns: contract, invariant, architecture
- prohibitions: no silent changes, production-grade

### 4.2 Artifact Signals
- presence of code blocks
- diffs or file trees
- schemas or configs
- explicit system references

### 4.3 Intent Signals
- exploratory vs executional language
- request for options vs correctness
- explicit constraints

### 4.4 Explicit User Override
[cite_start]If the user explicitly states a mode, it **wins**. [cite: 295]

[Back to top](#navigation)

---

## 5. Mode Transitions

### 5.1 Modes Are Not Sticky by Default
[cite_start]Each request may re-evaluate mode. [cite: 296]
Modes persist only if:
- reinforced by subsequent signals
- explicitly locked by user instruction

### 5.2 Transition Rules
Allowed transitions (examples):
- brainstorming → engineering
- engineering → implementation
- implementation → engineering

Forbidden transitions:
- casual → implementation without reclassification
- brainstorming → implementation without confirmation

### 5.3 Stabilization (Hysteresis)

Transitions are subject to temporal coherence and dampening to prevent "mode jitter."
> [cite_start]**See [Document 5 (Stability)](05_stability.md) for the specific hysteresis model, decay functions, and state variables.** [cite: 297]

[Back to top](#navigation)

---

## 6. Routing Effects of Mode

[cite_start]Modes affect **routing and gating**, not content. [cite: 298]

### 6.1 Memory Injection by Mode
| Memory Type | engineering | implementation | brainstorming | formal_spec | casual |
| :--- | :--- | :--- | :--- | :--- | :--- |
| static_global | Yes | Yes | Yes | Yes | Yes |
| static_mode_conditioned | Yes | Yes | Yes* | Yes | No |
| reference_memory | Gated | Gated | Rare | Gated | No |
| dynamic_memory | Gated | Gated | Gated | Gated | Minimal |

[cite_start]\* brainstorming uses lighter rule sets. [cite: 299, 300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314]

### 6.2 Instruction Strictness
- engineering / implementation:
  - no guessing
  - production-grade patterns
  - interface stability
- brainstorming:
  - hypotheses allowed
  - alternatives encouraged
- casual:
  - no heavy constraints

[Back to top](#navigation)

---

## 7. Prompt Assembly Contract (Mode-Aware)

Router must:
1. always inject static_global
2. inject static_mode_conditioned only if mode allows
3. gate reference memory by mode + intent
4. enforce token budgets
5. preserve layer precedence

Router must never:
- change rule text
- reorder precedence
- omit required layers

[Back to top](#navigation)

---

## 8. Failure Modes and Safe Defaults

### 8.1 Ambiguous Signals
If mode cannot be determined confidently:
- default to **engineering**
- [cite_start]never default to implementation [cite: 315]

### 8.2 Conflicting Signals
Resolve by priority:
1. explicit user instruction
2. artifact presence
3. linguistic intent
4. previous mode

[Back to top](#navigation)

---

## 9. Implementation Guidance (Non-Code)

### 9.1 Steward Output Contract (Conceptual)
~~text
mode: engineering
confidence: high
signals_used:
  - code_blocks
  - engineering_verbs
lock: false
~~

[cite_start]Schema is implementation-defined but must be explicit. [cite: 316]

### 9.2 Router Consumption
Router treats mode as:
- read-only
- authoritative
- required for gating

[cite_start]Router must emit telemetry for mode decisions. [cite: 317]

[Back to top](#navigation)

---

## 10. Hard Invariants (Mode System)

- Modes are orthogonal to topics
- Modes never select facts
- Modes never write memory
- Router never infers modes
- Model never sees mode logic

[cite_start]Violation is a **control-plane breach**. [cite: 318]

[Back to top](#navigation)

---

## 11. Relationship to Other Documents

- Builds on **[Document 1 (Architecture)](01_overview.md)**
- Enables **[Document 3 (Reference)](03_reference.md)**
- Stabilized by **[Document 5 (Stability)](05_stability.md)**

[Back to top](#navigation)

---

## 12. Closing Statement

[cite_start]Modes control **how the system thinks**, not what it knows. [cite: 319]
[cite_start]A small, explicit mode set is a **stability mechanism**, not a limitation. [cite: 320]

---

**END OF DOCUMENT 02**
