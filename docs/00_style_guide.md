# DOCUMENTATION STYLE GUIDE & STANDARD
## Formatting, Tone, and Structural Canons for Memory Steward
### Foundational Engineering Specification (Document 00 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**[Next: Document 1 (Architecture)](01_overview.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. File Naming & Organization](#2-file-naming--organization)
- [3. Header & Metadata Standard](#3-header--metadata-standard)
- [4. Navigation & Interlinking](#4-navigation--interlinking)
- [5. Typography & Formatting](#5-typography--formatting)
- [6. Tone & Voice (RFC 2119)](#6-tone--voice-rfc-2119)
- [7. Section Standardization](#7-section-standardization)
- [8. Visual Representation Standard (C4 Model)](#8-visual-representation-standard-c4-model)
- [9. Summary](#9-summary)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** All Contributors
**Change policy:**
- Append-only
- No silent edits

[cite_start]This document defines the **canonical style guide** for the Memory Steward engineering specifications[cite: 146].

[Back to top](#navigation)

---

## 1. Purpose

This document defines the **canonical style guide** for the Memory Steward engineering specifications.
All documentation must adhere to these standards to maintain:
- **Readability:** Uniform visual hierarchy.
- **Navigability:** Consistent cross-linking and anchoring.
- [cite_start]**Authority:** High-grade engineering tone. [cite: 147]

[Back to top](#navigation)

---

## 2. File Naming & Organization

- **Naming Convention:** `dd_topic_slug.md`
  - `dd`: Two-digit zero-padded index (e.g., `01`, `02`, `10`).
  - [cite_start]`topic_slug`: Lowercase, underscore_separated (e.g., `operational_mode`). [cite: 148, 149]
- **Storage:** Root of the documentation directory.
- [cite_start]**Images:** Stored in `./assets/` and linked via relative paths (or rendered via Mermaid). [cite: 150]

[Back to top](#navigation)

---

## 3. Header & Metadata Standard

Every document MUST start with the following header block, exactly as formatted:

~~~markdown
# [DOCUMENT TITLE IN CAPS]
## [Descriptive Subtitle]
### Foundational Engineering Specification (Document X of Y)
*Namespace: (deployment-specific) • Owner: (optional)*

---
~~~

**Rules:**
- **H1:** System-wide concept (e.g., "CANONICAL MEMORY ARCHITECTURE").
- **H2:** Specific scope of this file.
- **H3:** Document sequence identifier.
- [cite_start]**Metadata:** Italicized, single line, separated by a bullet (`•`). [cite: 151, 152, 153]

[Back to top](#navigation)

---

## 4. Navigation & Interlinking

### Top Navigation Bar
Immediately following the header separator (`---`), a directional navigation bar MUST exist:

~~~markdown
## Navigation
**← [Prev: Document X (Name)](dd_filename.md) | [Next: Document Y (Name)](dd_filename.md) →**
~~~

- Use **Bold** for the entire line.
- Use `←` and `→` arrows.
- [cite_start]Use explicit filenames for links. [cite: 155, 156]

### Table of Contents (TOC)
A manual TOC list must follow the top nav.
- Use `- [Section Name](#anchor-slug)` syntax.
- [cite_start]Anchor slugs must be lowercase, hyphenated, with special characters removed. [cite: 157]

### Back Links
At the end of every major section (H2), insert:
[cite_start]`[Back to top](#navigation)` [cite: 158]

[Back to top](#navigation)

---

## 5. Typography & Formatting

### 5.1 Code Blocks
- **Delimiter:** Use `~~~` (three tildes) for all code blocks to avoid conflict with nested Markdown parsers.
- [cite_start]**Language:** Always specify the language (e.g., `~~~python`, `~~~sql`, `~~~text`, `~~~mermaid`). [cite: 159]
- **Context:** Use `text` for pseudo-code or output traces.

### 5.2 Tables
- Use standard GFM tables.
- **Alignment:** Left-align text, center checks/statuses.
- [cite_start]**Header:** Bold column names are optional but recommended. [cite: 160]

### 5.3 Admonitions & Invariants
Do not use proprietary "alert" blocks (e.g., `::: info`). Use standard Markdown emphasis:

- **Hard Invariants:**
  > **Hard Invariant:** The model MUST NOT write to static memory.
- **Critical Warnings:**
  > [cite_start]**Warning:** Violation of this rule causes immediate abort. [cite: 161, 162, 163]

[Back to top](#navigation)

---

## 6. Tone & Voice (RFC 2119)

- **Imperative:** Use "MUST", "MUST NOT", "SHOULD", "MAY".
- **Concise:** Avoid marketing fluff. No "We are excited to introduce...".
- [cite_start]**Definitive:** Avoid "Conceptually," "Basically," or "Kind of." [cite: 165, 166]
- **Active Voice:** "The Router injects memory" (not "Memory is injected by the Router").

**Bad:**
> "Ideally, you should try to keep the version strings consistent so things don't break."

**Good:**
> [cite_start]"The Router **MUST** reject any retrieval request with ambiguous version strings." [cite: 167, 168]

[Back to top](#navigation)

---

## 7. Section Standardization

### 7.1 Section 0 (Status)
Every document MUST begin with Section 0:

~~~markdown
## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL / DRAFT / DEPRECATED
**Audience:** [Target Roles]
**Change policy:**
- Append-only
- No silent edits
~~~

### 7.2 Closing Statement
Every document MUST end with a semantic closing summary, followed by a footer separator.

~~~markdown
## X. Closing Statement
[Summary of why this document matters.]

---

**END OF DOCUMENT X**
~~~
[cite_start][cite: 169]

[Back to top](#navigation)

---

## 8. Visual Representation Standard (C4 Model)

All architectural diagrams MUST use the **C4 Model** hierarchy and be implemented using **Mermaid.js** code blocks.

### 8.1 Hierarchy Mapping
- **Level 1 (System Context):** High-level interactions (User ↔ Steward ↔ LLM).
- **Level 2 (Container):** Deployable units (Router, Postgres, Qdrant, MCP Server).
- [cite_start]**Level 3 (Component):** Internal modules (Ingestion Logic, Hysteresis State). [cite: 171, 172, 173]

### 8.2 Syntax Standard
Use `C4Context`, `C4Container`, or standard flowchart syntax that mimics C4 structure.

**Example (Level 2 - Container):**
~~~mermaid
graph TD
    User((User))
    subgraph "Control Plane"
        Router[Router / MCP Client]
        Steward[Steward / MCP Server]
    end
    subgraph "Data Plane"
        LLM[LLM Backend]
    end

    User -->|Chat| Router
    Router -->|Gating Check| Steward
    Steward -->|Mode: Engineering| Router
    Router -->|Inference| LLM
~~~
[cite_start][cite: 174, 175, 176]

[Back to top](#navigation)

---

## 9. Summary

This style guide enforces the **"High-Grade"** aesthetic:
1.  **Strict Structure** (Headers, Nav, Sections).
2.  **Strict Logic** (RFC 2119, Invariants).
3.  **Strict Formatting** (Tildes, standardized tables).
4.  **Strict Visuals** (Mermaid, C4).
[cite_start]Adherence is mandatory for all contributions. [cite: 178, 179]

---

**END OF DOCUMENT 00**
