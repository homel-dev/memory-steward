
# END-TO-END VERIFICATION & VALIDATION
## The Definition of Done and Correctness Tests
### Foundational Engineering Specification (Document 08 of 12)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Document 07 (Management)](07_glass_pane.md) | [Next: Document 09 (Runtime Contract)](09_runtime_contract.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Purpose](#1-purpose)
- [2. System Components (Verification Targets)](#2-system-components-verification-targets)
- [3. Core Invariants (Must Hold)](#3-core-invariants-must-hold)
- [4. Step-by-Step Verification Plan](#4-step-by-step-verification-plan)
- [5. Definition of Done](#5-definition-of-done)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** FOUNDATIONAL
**Audience:** QA, core maintainers, release engineers
**Change policy:**
- Append-only
- No silent edits

[Back to top](#navigation)

---

## 1. Purpose

This document defines **what must be true** for the Memory Steward system to be considered correct.
It serves as the primary regression guard.

[Back to top](#navigation)

---

## 2. System Components (Verification Targets)

### 2.1 Router (Ingress)
- **Role:** Authoritative ingress, embedder, and orchestrator.
- **Verification:**
  ~~~bash
  kubectl logs deploy/memory-router | grep "retrieved"
  ~~~

### 2.2 Steward (Admission)
- **Role:** Async decision maker for persistence.
- **Verification:**
  ~~~bash
  kubectl logs deploy/memory-steward | grep "fragment_inserted"
  ~~~

### 2.3 Postgres (Truth)
- **Role:** Append-only canonical store.
- **Verification:**
  ~~~sql
  SELECT count(*) FROM dynamic_memory; -- Must only increase
  ~~~

[Back to top](#navigation)

---

## 3. Core Invariants (Must Hold)

### 3.1 Statelessness
**Test:** Delete the Builder LLM pod during a conversation.
**Expectation:** Conversation continues without state loss (state is in Postgres/Vector).

### 3.2 Async Admission
**Test:** Scale Steward to 0 replicas.
**Expectation:** Chat (`/v1/chat/completions`) continues to function; only memory formation is paused.

### 3.3 Relevance Beats Recency
**Test:** Inject an old rule ("Always speak French") and a newer irrelevant fact.
**Expectation:** System adheres to the old rule.

[Back to top](#navigation)

---

## 4. Step-by-Step Verification Plan

### 4.1 Phase 1: Basic Plumbing
**Action:** Send a raw curl request to the Router.
~~~bash
curl http://router/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{ "messages": [{"role":"user","content":"hello"}] }'
~~~
**Success:** 200 OK with valid JSON response.

### 4.2 Phase 2: Static Memory
**Action:** Insert a static rule.
~~~sql
INSERT INTO static_memory (project_id, key, content, priority)
VALUES ('default', 'lang', 'Always respond in Spanish', 100);
~~~
**Test:** Ask "Hello".
**Success:** Response is in Spanish.

### 4.3 Phase 3: Dynamic Memory Admission
**Action:** User states a fact.
"My project code is 994."
**Wait:** 2 seconds (Async lag).
**Check:**
~~~sql
SELECT content FROM dynamic_memory WHERE content LIKE '%994%';
~~~
**Success:** Row exists.

### 4.4 Phase 4: Retrieval Validation
**Action:** Restart Router (clear caches). Ask "What is my project code?"
**Success:** Router logs show retrieval of the specific fragment; Answer is "994".

### 4.5 Phase 5: Failure Modes

| Failure | Expected Behavior |
| :--- | :--- |
| **Steward Down** | Chat works, no new memory. |
| **Qdrant Down** | Chat works, degraded context (Static only). |
| **Postgres Down** | Explicit 500 Error (Fail Secure). |

[Back to top](#navigation)

---

## 5. Definition of Done

The system is deployed and correct ONLY when:
1. All Phase 1-5 tests pass.
2. No "UPDATE" statements appear in Steward logs (Append-only).
3. Telemetry is visible in the Diagnostics Plane.

[Back to top](#navigation)

---

## 6. Closing Statement

Verification proves that the **Control Plane** is enforcing invariants, regardless of the underlying LLM's behavior.

---

**END OF DOCUMENT 08**
