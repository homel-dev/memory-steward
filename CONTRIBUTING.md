# CONTRIBUTING TO MEMORY STEWARD
## Engineering Guidelines and Invariants
### Foundational Engineering Specification (Root Document)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: RFC Proposal](RFC_PROPOSAL.md) | [Next: README](README.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. The Golden Rule](#1-the-golden-rule)
- [2. Documentation Standards](#2-documentation-standards)
- [3. Engineering Invariants](#3-engineering-invariants)
- [4. Definition of Done](#4-definition-of-done)
- [5. Visuals](#5-visuals)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** All Contributors and Maintainers
**Change policy:**
- Append-only
- No silent edits

Thank you for your interest in Memory Steward. This is a **High-Grade Engineering** project, which means we prioritize correctness, documentation, and determinism over new features. Before opening a PR, you **MUST** review the following.

[Back to top](#navigation)

---

## 1. The Golden Rule

**Documentation comes first.** Code without updated specification (Docs 01–12) will be rejected. If you change how the system behaves, you must update the corresponding `docs/` file.

[Back to top](#navigation)

---

## 2. Documentation Standards

All documentation changes must adhere to **[Document 00: Style Guide](docs/00_style_guide.md)**.
- Use `~~~` for code blocks.
- Use Mermaid.js for diagrams (C4 Model).
- Maintain the "Hard Invariants" sections.

[Back to top](#navigation)

---

## 3. Engineering Invariants

Do not violate the core architectural invariants defined in **[Document 01](docs/01_overview.md)** and **[Document 08](docs/08_verification.md)**:

> **Hard Invariant:** **No Implicit Writes:** The Model never decides what to remember. Only the Steward does.
> **Hard Invariant:** **No Data Plane Pollution:** Telemetry is never injected into the prompt.
> **Hard Invariant:** **Stateless Inference:** The Router must assume the Model remembers nothing between turns.

[Back to top](#navigation)

---

## 4. Definition of Done

Your PR is not ready until it passes the checks in **[Document 08: Verification](docs/08_verification.md)**.
1. Does it pass the "Statelessness" test?
2. Did you verify the `dynamic_memory` table is append-only?
3. Did you add telemetry for the new feature?

[Back to top](#navigation)

---

## 5. Visuals

If you change architecture, you **MUST** update the Mermaid C4 diagrams in **[Document 09](docs/09_runtime_contract.md)** or **[Document 00](docs/00_style_guide.md)**. Do not upload PNGs/JPGs.

[Back to top](#navigation)

---

## 6. Closing Statement

By adhering to these contributing guidelines, maintainers guarantee that the Memory Steward control plane remains deterministic and secure against behavioral drift.

---

**END OF DOCUMENT CONTRIBUTING**
