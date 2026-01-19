# Memory Steward

**Memory Steward** is a local-first memory admission and context virtualization service for AI systems.

It provides a strict, auditable layer for deciding **what is remembered**, **what is injected**, and **what is ignored**, independent of chat history, session boundaries, or model state.

Memory Steward is part of the **Homel** organization.

---

## NAVIGATION

- [Top](#memory-steward)
- [1. What Problem This Solves](#1-what-problem-this-solves)
- [2. Core Idea](#2-core-idea)
- [3. What Memory Steward Is](#3-what-memory-steward-is)
- [4. What Memory Steward Is NOT](#4-what-memory-steward-is-not)
- [5. Architectural Overview](#5-architectural-overview)
- [6. Design Principles](#6-design-principles)
- [7. Non-Negotiable Invariants](#7-non-negotiable-invariants)
- [8. Scope](#8-scope)
- [9. Documentation](#9-documentation)

---

## 1. What Problem This Solves

Large Language Models are:

- stateless
- constrained by finite context windows
- isolated by chat and session boundaries

As a result, long-running work degrades over time:
constraints are forgotten, decisions drift, and users must restate context manually.

Memory Steward addresses this by introducing a **context virtualization layer** above the LLM.

Every user message is treated as a query into a structured memory system, and relevant past context is dynamically re-injected — without relying on chat history.

[Back to Top](#memory-steward)

---

## 2. Core Idea

> **Memory is not accumulated. It is reconstructed.**

The LLM remains stateless.

Context is rebuilt on every turn from:
- canonical rules
- retrieved semantic fragments

[Back to Top](#memory-steward)

---

## 3. What Memory Steward Is

- A **memory admission controller**
- A **context reconstruction service**
- A **gatekeeper** between interaction and persistence
- A **local-first**, inspectable system

[Back to Top](#memory-steward)

---

## 4. What Memory Steward Is NOT

- Not a chat log
- Not a RAG framework
- Not an agent
- Not an execution engine
- Not a planner
- Not autonomous

Memory Steward does not decide *what to do*.  
It decides *what is worth remembering*.

[Back to Top](#memory-steward)

---

## 5. Architectural Overview

High-level flow:

~~~text
User Interaction
   ↓
Memory Admission (Steward)
   ↓
Atomic Memory Fragments
   ↓
Persistent Storage
   ↓
Relevance-Based Retrieval
   ↓
Prompt Reconstruction
   ↓
LLM Execution
~~~

[Back to Top](#memory-steward)

---

## 6. Design Principles

- **Stateless models**  
  The LLM is never assumed to remember anything.

- **Explicit layering**  
  Canonical rules and dynamic context have different semantics.

- **Admission over accumulation**  
  Nothing is stored unless explicitly admitted.

- **Auditability**  
  All memory entries are inspectable.

- **Local sovereignty**  
  All components can run locally.

[Back to Top](#memory-steward)

---

## 7. Non-Negotiable Invariants

- Static memory is never embedded
- Dynamic memory is never blindly injected
- Retrieval happens on every turn
- Chat/session boundaries are not trusted
- Relevance beats recency
- The Steward never generates answers

Violating these breaks the system.

[Back to Top](#memory-steward)

---

## 8. Scope

This repository implements the **Memory Steward** system only.

Execution, supervision, tooling, and convergence logic are intentionally **out of scope** and handled by separate projects within the Homel organization.

[Back to Top](#memory-steward)

---

## 9. Documentation

- `docs/architecture.md` — Canonical architecture specification
- `docs/invariants.md` — System invariants and hard constraints
- `docs/industry-landscape-memory.md` — Derived landscape analysis specific to Memory Steward

[Back to Top](#memory-steward)

---

**Memory Steward**  
by HomelDev  
https://homel.dev
