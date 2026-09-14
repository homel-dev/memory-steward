# DOCUMENTATION STYLE GUIDE AND STANDARD
## Formatting, Authority, Navigation, and Maintenance Rules
### Foundational Engineering Specification (Document 00 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**[Next: Document 01 (Architecture)](01_overview.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. Authority and Drift Policy](#2-authority-and-drift-policy)
- [3. File Naming and Organization](#3-file-naming-and-organization)
- [4. Header and Metadata Standard](#4-header-and-metadata-standard)
- [5. Navigation and Interlinking](#5-navigation-and-interlinking)
- [6. Typography and Formatting](#6-typography-and-formatting)
- [7. Tone and Normative Language](#7-tone-and-normative-language)
- [8. Section Standardization](#8-section-standardization)
- [9. Visual Representation Standard](#9-visual-representation-standard)
- [10. Closing Statement](#10-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** All contributors and maintainers
**Change policy:** Living implementation-aligned standard; no silent behavioral drift.

This document defines the documentation standard for Memory Steward engineering specifications and repository operational guides.

[Back to top](#navigation)

---

## 1. Purpose

Documentation MUST remain readable, navigable, technically precise, and synchronized with the current repository.

The standard exists to enforce:

- uniform visual hierarchy;
- deterministic cross-linking and anchors;
- explicit implementation status;
- engineering tone without marketing filler;
- maintainable Mermaid diagrams instead of opaque screenshots for architecture.

[Back to top](#navigation)

---

## 2. Authority and Drift Policy

The checked-in implementation and executable tests are the authority for current runtime behavior.

Documentation MUST describe behavior present in the current tree. A design that is not implemented MUST be labelled `PROPOSAL`, `PARTIAL`, `BACKGROUND`, `DEPRECATED`, or otherwise explicitly non-runtime. Documentation MUST NOT make an unimplemented behavior canonical merely by describing it.

Behavior-changing code changes MUST update every affected documentation contract in the same change set. Historical decisions belong in Git history, ADRs, or explicitly dated notes; stale current-state text MUST be edited rather than preserved behind an append-only rule.

Allowed status values:

- `IMPLEMENTED` — represented by current code/manifests and, where practical, executable tests;
- `PARTIAL` — only the explicitly identified subset exists;
- `PROPOSAL` — design intent only;
- `BACKGROUND` — rationale/comparison material, not a runtime contract;
- `DEPRECATED` — retained only for migration/history.

[Back to top](#navigation)

---

## 3. File Naming and Organization

Numbered engineering specifications under `docs/` MUST use `dd_topic_slug.md` with a two-digit index and lowercase underscore-separated slug.

Repository-root operational guides such as `README.md`, `DEPLOYMENT.md`, and `CONTRIBUTING.md` MAY use conventional root filenames but MUST follow the same formatting, tone, and authority rules where applicable.

Architecture images SHOULD be represented as Mermaid source. If binary assets are required, they MUST live under a documented assets directory and MUST NOT duplicate a maintainable Mermaid representation without reason.

[Back to top](#navigation)

---

## 4. Header and Metadata Standard

Numbered engineering specifications MUST begin with:

~~~markdown
# [DOCUMENT TITLE IN CAPS]
## [Descriptive Subtitle]
### Foundational Engineering Specification (Document XX of YY)
*Namespace: memory-steward • Owner: architecture-team*

---
~~~

Proposal/background documents MAY replace the third line with an explicit `Engineering Proposal` or `Background Architecture Note`, but status MUST remain unambiguous.

[Back to top](#navigation)

---

## 5. Navigation and Interlinking

Every numbered specification MUST contain a `## Navigation` section immediately after the header separator.

The navigation section MUST contain:

- directional previous/next links where applicable;
- a manual table of contents using repository-stable GitHub/GitLab-compatible anchor slugs;
- explicit filenames in links.

At the end of every major H2 section, insert:

~~~markdown
[Back to top](#navigation)
~~~

Links MUST be relative when the target is in this repository.

[Back to top](#navigation)

---

## 6. Typography and Formatting

### 6.1 Code Blocks

Repository documentation MUST use triple tildes and MUST specify a language identifier:

    ~~~bash
    command
    ~~~

Use `text` for pseudo-code and traces. Triple backtick fences are non-compliant in committed engineering specifications.

When an entire Markdown document is reprinted in chat/tickets and contains internal triple-tilde fences, an outer quadruple-tilde fence MAY be used to avoid delimiter collision. That exception does not apply to committed files.

### 6.2 Tables

Use standard GFM tables. Text SHOULD be left-aligned unless numeric/status alignment materially improves readability.

### 6.3 Invariants and Warnings

Use standard Markdown blockquotes:

~~~markdown
> **Hard Invariant:** The Builder MUST NOT decide durable-memory writes.
~~~

Do not use proprietary alert syntax.

### 6.4 Generated Artifacts

Do not commit generated citation markers, transcript annotations, or model-output metadata such as `[cite_start]` or `[cite: ...]`.

[Back to top](#navigation)

---

## 7. Tone and Normative Language

Use RFC 2119-style `MUST`, `MUST NOT`, `SHOULD`, and `MAY` for normative requirements.

Documentation MUST be concise, active-voice, and implementation-specific. Avoid conceptual filler such as “basically”, “kind of”, or aspirational language that is indistinguishable from current behavior.

Commands, endpoints, environment variables, table names, and workload names SHOULD be written exactly as implemented.

[Back to top](#navigation)

---

## 8. Section Standardization

Every numbered specification MUST begin its body with:

~~~markdown
## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED / PARTIAL / PROPOSAL / BACKGROUND / DEPRECATED
**Audience:** [target roles]
**Change policy:** [explicit maintenance rule]
~~~

Every numbered specification MUST end with a `Closing Statement`, a separator, and an `END OF DOCUMENT` marker.

[Back to top](#navigation)

---

## 9. Visual Representation Standard

Architecture and sequence diagrams MUST use Mermaid when a diagram materially improves understanding.

Diagrams MUST show current deployable units and real request paths. Proposed components or flows MUST be marked as proposed in both diagram labels and surrounding text.

Use C4 concepts for system/container/component boundaries even when standard Mermaid `graph` or `sequenceDiagram` syntax is more practical than a C4-specific renderer.

[Back to top](#navigation)

---

## 10. Closing Statement

The repository is trustworthy only when operators can distinguish implemented behavior from design intent and can navigate from code/manifests to documentation without encountering contradictory contracts.

[Back to top](#navigation)

---

**END OF DOCUMENT 00**
