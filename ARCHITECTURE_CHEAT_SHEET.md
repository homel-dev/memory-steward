# ARCHITECTURE CHEAT SHEET

## Current Runtime

~~~text
Chat/OpenAI client -> memory-router -> Builder LLM
                         |  |  \
                         |  |   -> Postgres (static + exact artifacts + telemetry)
                         |  -> Qdrant (dynamic/reference retrieval)
                         -> embeddings
                         -> async memory-steward admission

Agent -> memory-router / memory-steward directly
      -> or memory-steward-mcp adapters

Operator -> /glap through Router
         -> or FastMCP CLI inside cluster / localhost port-forward
~~~

## Authority

- Router: retrieval, context assembly, Builder dispatch.
- Steward: durable dynamic-memory admission, agent outcomes/artifacts, feedback.
- MCP: internal schema-driven control/agent surface.
- Postgres: canonical structured state and telemetry.
- Qdrant: semantic index for dynamic/reference memory.
- OCO: Grafana presentation plane; not canonical storage.

## Current Mode Semantics

No Steward mode classifier exists. `mode` is caller-supplied optional Router metadata. Reference retrieval is allowed for `engineering`, `implementation`, and `formal_spec`; absent mode currently falls back to `engineering` for reference eligibility.

## Operator Commands

~~~bash
task ops:service:status
task ops:service:wait
task ops:mcp:tools
task ops:mcp:call -- ref_list
task ops:ref:inspect -- product=kicad version=9.0
~~~

## Core Endpoints

~~~text
memory-router:
  GET  /healthz
  GET  /v1/models
  POST /v1/chat/completions
  POST /v1/context/retrieve
  POST /v1/reference/search
  GET  /v1/reference/{chunk_id}

memory-steward:
  GET  /healthz
  POST /admit
  POST /v1/agent/outcomes
  POST /v1/context/feedback

memory-steward-list:
  GET  /healthz
  POST /v1/list/transcribe
  POST /v1/audio/transcriptions
  POST /v1/list/translate  # currently 501 / not implemented
~~~

## Hard Boundaries

- Do not expose MCP publicly for routine administration.
- Do not present proposal-only mode/auditor behavior as implemented.
- Do not promote agent artifacts to canonical Reference Memory implicitly.
- Do not let documentation outrun code/tests.

## Request Sequences

### Chat

~~~text
client -> Router -> static/dynamic/reference retrieval -> context budget -> Builder -> client
                 \-> telemetry
                 \-> async Steward admission -> Postgres + Qdrant
~~~

### Agent

~~~text
agent -> Router /v1/context/retrieve -> structured lanes + accounting
agent -> Steward /v1/agent/outcomes -> idempotency + agent_reference + optional durable knowledge
agent -> Steward /v1/context/feedback -> feedback + telemetry
~~~

## Memory Matrix

| Lane | Write authority | Read path | Notes |
| --- | --- | --- | --- |
| Static | Operator/MCP | Router | Global or exact-mode |
| Dynamic | Steward | Router | Project-scoped semantic |
| Reference | Explicit ingestion | Router | Source lane; exact metadata filters |
| Agent artifact | Steward deterministic outcome path | Router structured context | Exact selectors |
| Telemetry | Runtime | Diagnostics | Never cognitive memory by default |

## Critical Limits

- No mode classifier/hysteresis runtime.
- No durable admission queue.
- No active audited admission state machine.
- MCP stays internal/loopback for routine use.
- `task build` does not rewrite GHCR deployment images.

## High-Value Operator Commands

~~~bash
task ops:service:status
task ops:service:health
task ops:mcp:tools:json
task ops:diag:health
task ops:ref:list
task ops:config:show
task logs:router
task logs:steward
~~~
