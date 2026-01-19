# docs/architecture.md

# Memory Steward — Canonical Architecture Specification

---

## DOCUMENT METADATA

- Project: Memory Steward
- Document Type: Canonical Architecture Specification
- Scope: Memory, Context Virtualization, Personalization
- Status: Canonical (Foundational, Non-Optional)
- Audience: Senior engineers, system architects, contributors
- Explicit Non-Goals:
  - UI
  - Execution
  - Tooling
  - Vendor-specific SDKs

---

## NAVIGATION

- [Top](#memory-steward--canonical-architecture-specification)
- [1. Purpose](#1-purpose)
- [2. Problem Statement](#2-problem-statement)
- [3. Core Idea](#3-core-idea)
- [4. Mental Model](#4-mental-model)
- [5. Memory Layers](#5-memory-layers)
  - [5.1 Static / Canonical Memory](#51-static--canonical-memory)
  - [5.2 Dynamic Context Memory](#52-dynamic-context-memory)
- [6. Infinite Context Mechanism](#6-infinite-context-mechanism)
- [7. Storage Model](#7-storage-model)
- [8. Role of the Memory Steward](#8-role-of-the-memory-steward)
- [9. Independence from Chats and Sessions](#9-independence-from-chats-and-sessions)
- [10. Topic Drift](#10-topic-drift)
- [11. Failure Modes](#11-failure-modes)
- [12. Summary](#12-summary)

---

## 1. Purpose

This document specifies **how Memory Steward achieves the illusion of an infinite context window** while preserving:

- correctness
- continuity across time
- personalization
- independence from chat/session boundaries
- independence from LLM providers

This is **not a memory feature**.

This is a **context virtualization system**.

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 2. Problem Statement

Modern LLM systems suffer from:

- finite context windows
- stateless execution
- loss of long-running constraints
- reliance on summarization
- chat-bound continuity

This leads to semantic drift and repeated correction.

Memory Steward explicitly rejects this model.

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 3. Core Idea

> Every user message is treated as a query into a personalized knowledge base, and all relevant past context is dynamically re-injected.

The LLM itself remembers nothing.

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 4. Mental Model

Memory Steward separates:

1. The LLM (stateless)
2. The prompt (reconstructed every turn)
3. The context (retrieved dynamically)

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 5. Memory Layers

### 5.1 Static / Canonical Memory

Static memory consists of explicit, authoritative rules.

Examples:
- Always respond in English
- Never invent facts
- Preserve raw Markdown when requested

Properties:
- Always injected
- Never embedded
- Never summarized
- Never removed automatically

[Back to Top](#memory-steward--canonical-architecture-specification)

---

### 5.2 Dynamic Context Memory

Dynamic memory consists of **atomic semantic fragments**:

- decisions
- constraints
- clarifications
- resolved ambiguities

Properties:
- Stored individually
- Embedded and indexed
- Retrieved dynamically
- Injected conditionally

This enables continuity without accumulation.

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 6. Infinite Context Mechanism

For each user message:

~~~text
User Message
   ↓
Embedding
   ↓
Vector Search
   ↓
Relevant Fragments
   ↓
Prompt Reconstruction
   ↓
LLM Execution
~~~

Nothing persists inside the model.

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 7. Storage Model

Dynamic memory entries are atomic records:

~~~text
MemoryEntry:
  - content
  - embedding
  - metadata:
      - scope
      - timestamp
      - confidence
~~~

Explicit exclusions:
- chat logs
- transcripts
- summaries

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 8. Role of the Memory Steward

The Steward LLM operates at the **meta level**.

It decides:
- what is worth storing
- how it is scoped
- whether it is durable

It does **not**:
- generate answers
- reason about tasks
- execute actions

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 9. Independence from Chats and Sessions

Chats are UI artifacts.

Memory retrieval:
- ignores chat IDs
- ignores session IDs
- relies only on relevance

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 10. Topic Drift

Topic switching requires no explicit detection.

Relevance naturally shifts as embeddings shift.

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 11. Failure Modes

- Over-retrieval → bounded injection
- Low-signal storage → steward filtering
- False relevance → metadata scoping

[Back to Top](#memory-steward--canonical-architecture-specification)

---

## 12. Summary

Memory Steward provides:

- retrieval-driven continuity
- explicit memory admission
- auditable state
- model-agnostic operation

This ensures no relevant context is ever truly lost.

[Back to Top](#memory-steward--canonical-architecture-specification)

---

END OF DOCUMENT
