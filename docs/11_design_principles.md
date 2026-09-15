# DESIGN PRINCIPLES
## Separation, Bounded Context, and Asynchronous Admission
### Foundational Engineering Specification (Document 11 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 10 (Landscape)](10_industry_landscape.md) | [Next: Document 12 (Extensions)](12_extensions.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Separation of Responsibilities](#1-separation-of-responsibilities)
- [2. Retrieval over Raw History Growth](#2-retrieval-over-raw-history-growth)
- [3. Asynchronous Ordinary-Chat Admission](#3-asynchronous-ordinary-chat-admission)
- [4. Structured Agent Outcomes](#4-structured-agent-outcomes)
- [5. Failure Isolation](#5-failure-isolation)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers and architects
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

[Back to top](#navigation)

---

## 1. Separation of Responsibilities

The Router retrieves and assembles Builder context. The Steward performs durable-memory admission. MCP exposes explicit control/agent operations. LIST is an optional input service. Diagnostics are not treated as learned memory.

[Back to top](#navigation)

---

## 2. Retrieval over Raw History Growth

The Router uses selected static/dynamic/reference context and bounded chat history rather than treating all prior conversation as durable memory.

[Back to top](#navigation)

---

## 3. Asynchronous Ordinary-Chat Admission

Chat response delivery does not wait for ordinary admission completion. The Router dispatches admission asynchronously after the Builder response. Consequently, newly stated facts may not be available to retrieval immediately.

[Back to top](#navigation)

---

## 4. Structured Agent Outcomes

Agents submit structured outcomes/artifacts rather than synthetic chat transcripts. Durable knowledge extraction remains governed by Steward logic; validated reusable artifacts can be persisted separately as `agent_reference`.

[Back to top](#navigation)

---

## 5. Failure Isolation

Best-effort side paths (telemetry, async admission) should not replace a successful primary response merely because their own operation fails. This rule applies only where the code explicitly implements that isolation.

[Back to top](#navigation)

---

## 6. Principle: Authority Must Be Observable

A component boundary is useful only if operators can tell which component made a decision. Request IDs, context request IDs, outcome IDs, explicit tools, and distinct storage tables make authority inspectable.

The system should avoid "smart" hidden behavior that cannot be distinguished from data or configuration. A future classifier or auditor therefore requires explicit telemetry and documented failure behavior.

## 7. Principle: Deterministic Evidence Is Not Learned Memory

An agent-generated JSON artifact can be useful precisely because its bytes/schema/provenance are stable. Re-embedding or summarizing it into learned memory may destroy properties required for engineering workflows. The separate `agent_reference` lane preserves that distinction.

## 8. Principle: Reference Sources Are Not Beliefs

External documentation should remain identifiable as source material. Reference ingestion, metadata filters, and the `memory_type=reference_memory` discriminator allow the Router to retrieve sources without pretending the system "learned" them as user facts.

## 9. Principle: Bounded Context Beats Implicit Growth

Every lane competes for finite model input. The Router therefore uses explicit context and history budgets. Increasing model context size does not remove the need for ordering, gating, and observability; it only changes the available ceiling.

## 10. Principle: Async Work Must Admit Its Durability Tradeoff

Async ordinary-chat admission protects latency, but without a durable queue it is best-effort. The design should state that tradeoff plainly rather than claiming eventual consistency that the runtime cannot guarantee.

## 11. Principle: Operator Mutations Are Explicit

MCP provides powerful mutation tools. Their existence is not permission for automatic invocation. Destructive or externally mutating operations should require explicit operator intent and deployment authorization.

## 12. Principle: Provisioned Schema Is Not Runtime Behavior

Migrations can safely prepare future tables ahead of implementation. Documentation must still distinguish "the table exists" from "the runtime executes this state machine." This is the central rule behind the PARTIAL/PROPOSAL status of audited admission control.

## 13. Anti-Patterns

| Anti-pattern | Why it is rejected |
| --- | --- |
| One giant prompt containing all memory | Weak precedence, token growth, hard-to-debug behavior |
| Model decides what becomes Reference Memory | Conflates learned belief with authority/source material |
| Router directly writes learned facts | Collapses read/assemble and admission authority |
| Steward answers users | Collapses governance and data-plane inference |
| Hidden product inference from mode | Mixes posture with corpus selection |
| Arbitrary reference metadata filters | Expands query surface without versioned contract |
| Treating MCP-local cache as Router cache | Creates false performance/consistency assumptions |
| Silent retries/queues claimed but absent | Misstates durability guarantees |
| Telemetry payloads used as context | Pollutes cognitive inputs with diagnostics |
| Documentation shortened until operational detail is lost | Makes code archaeology necessary for normal maintenance |

## 14. Design Review Questions

Before accepting a new feature, reviewers should be able to answer:

- What lane does the data belong to?
- Who writes it?
- Who reads it?
- How is it selected?
- How is it budgeted?
- How is it deleted or invalidated?
- What telemetry proves the behavior?
- What happens when its dependency fails?
- Does it block the hot path?
- Is the behavior current, partial, proposal, or background?

---

## 6. Closing Statement

These principles summarize behavior already visible in the implementation. They guide changes but do not override executable contracts in code, tests, manifests, or API schemas.

[Back to top](#navigation)

---

**END OF DOCUMENT 11**
