# Memory Steward

Memory Steward is the durable-memory admission service and hosts the initial CodeGraph discovery/control-plane processes.

It receives completed chat turns and structured agent outcomes, uses the configured Steward LLM to extract durable knowledge candidates, persists accepted dynamic-memory fragments to Postgres, and indexes their dense/lexical representations in Qdrant. It also persists reusable AMP agent-reference artifacts and retrieval feedback.

The service does not answer user chat requests and does not currently classify operational mode. See the repository root `README.md`, `docs/01_overview.md`, `docs/12_extensions.md`, and `docs/13_admission_control.md` for the implemented authority boundaries and known admission-control gaps.

## Responsibilities

- Ordinary-chat durable-memory extraction and persistence.
- Structured agent-outcome idempotency.
- Deterministic `agent_reference` artifact persistence.
- Optional durable-knowledge extraction from agent outcomes.
- Context feedback persistence.
- Steward admission/outcome/feedback telemetry.
- Flux `GitRepository` `NewArtifact` ingestion into durable PostgreSQL CodeGraph build state.
- CodeGraph build reconciliation through PostgreSQL LISTEN/NOTIFY plus fallback scans and Argo Workflows.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /healthz | Steward liveness |
| POST | /admit | Ordinary-chat durable-memory admission |
| POST | /v1/agent/outcomes | Structured agent outcome submission |
| POST | /v1/context/feedback | Context usefulness feedback |

## Persistence

Writes Postgres structured state and Qdrant semantic memory. Uses embeddings for durable fragments. The extraction LLM is configured independently from the Builder.

## Current admission boundary

The active path is extraction -> persistence. Migration 060's deterministic gate/Auditor/quarantine schema is not an active runtime pipeline.

## Agent outcomes

`(project_id, outcome_id)` is idempotent against a canonical request hash. Exact replay returns the stored completed result; payload conflict returns HTTP 409.

## CodeGraph control-plane entry points

The same image provides the CodeGraph control-plane and worker process:

- `python -m memory_steward.codegraph_controller` — exposes `/events/flux`, persists `NewArtifact` events, reconciles the current Flux artifact, submits/observes Argo Workflows, and records the durable result;
- `python -m memory_steward.codegraph_worker` with `CODEGRAPH_WORKER_MODE=flux-index` — downloads the exact Flux artifact, verifies its digest, performs a full CodeGraph index without requiring `.git`, and publishes a self-contained generation bundle to MinIO.

The controller also exposes `GET /metrics` with durable PostgreSQL build-state gauges and ingress/Workflow counters; both controller and worker emit CodeGraph lifecycle log lines with `build_id`. The image pins the upstream CodeGraph engine version; serving remains a later lifecycle step after a successful generation build.

Operator verification, log and metric queries, and the end-to-end evidence checklist are in [`docs/10_codegraph_flux_operations.md`](../../docs/10_codegraph_flux_operations.md).
