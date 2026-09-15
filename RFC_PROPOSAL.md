# RFC: SEPARATED MEMORY CONTROL PLANE
## Deterministic Boundaries Around Probabilistic Inference

## Status

**Status:** PROPOSAL / BACKGROUND
**Repository implementation authority:** current code + executable tests
**License:** Apache-2.0

This RFC is design rationale. It MUST NOT be used to infer a runtime capability that is absent from the repository.

## 1. Motivation

Memory-augmented systems become difficult to reason about when inference, retrieval, durable writes, reference ingestion, and diagnostics all share implicit authority. This RFC proposes separating those responsibilities behind explicit contracts.

## 2. Reference Architecture

The current Memory Steward repository demonstrates the following separation:

- `memory-router`: synchronous retrieval/context assembly and Builder dispatch;
- `memory-steward`: durable learned-memory admission, agent outcomes, feedback;
- `memory-steward-mcp`: internal operator/agent control surface;
- Postgres: canonical structured state and telemetry;
- Qdrant: semantic retrieval indexes;
- optional LIST speech-input service;
- Open WebUI as an optional presentation client.

## 3. Important Qualification

The Router is logically not the durable learned-memory writer, but it does have Postgres write access for telemetry. Therefore the implementation is **not** accurately described as using a database credential that is physically read-only.

Likewise, explicit operator content/config writes may be performed by the MCP service. The useful invariant is authority by operation, not a false claim that exactly one process owns every mutation in every store.

## 4. Ordinary Chat Admission

The reference implementation dispatches chat admission asynchronously after Builder inference. Structured agent outcomes use an explicit synchronous API instead of being represented as synthetic chat turns.

## 5. Memory Types

Canonical Reference Memory is explicit curated ingestion. Dynamic memory is Steward-admitted learned context. `agent_reference` is structured reusable agent/tool output. These types remain distinct.

## 6. Operational Mode

A mode classifier/hysteresis mechanism is not currently implemented. The Router accepts optional caller-supplied `mode` metadata. Any standardized classifier design remains future work until represented by code/tests.

## 7. Security Considerations

Separation reduces accidental authority coupling but is not itself a complete security boundary. Operators should keep MCP internal, restrict Kubernetes/network access, protect Postgres/Qdrant credentials, validate destructive actions, and treat URL-ingestion capability as privileged operator functionality.

## 8. Compatibility Rule

Claims in this RFC become implementation guarantees only when they are represented by the repository's code, tests, manifests, and current operational documentation.

## 9. Current Implementation Mapping

The separated control-plane proposal maps to current runtime as follows:

- Router owns retrieval, prompt/context assembly, and Builder dispatch.
- Steward owns durable dynamic-memory admission and structured agent outcomes.
- MCP exposes explicit operator and agent adapters.
- Postgres stores canonical structured state and telemetry.
- Qdrant stores semantic dynamic/reference vectors.
- Agent artifacts use a deterministic Postgres lane.
- Reference ingestion is explicit and source-oriented.

## 10. Deliberately Unimplemented Portions

The repository does not currently implement automatic mode classification, mode hysteresis, a durable admission queue, or the proposed deterministic audited admission state machine. These remain future design areas and are intentionally not smuggled into the current contract.

## 11. Acceptance Criteria for Architectural Evolution

A future RFC implementation should preserve explicit authority, bounded context, observable decisions, replay/idempotency where needed, and detailed current-state documentation. New intelligence in the control plane should be introduced as a named component or state transition, not hidden inside prompt text.
