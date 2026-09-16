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
- CodeGraph MinIO event discovery and PostgreSQL registry insertion.
- CodeGraph discovery queue control through PostgreSQL LISTEN/NOTIFY plus fallback scans.

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

The same image provides CodeGraph control-plane and worker process modes:

- `python -m memory_steward.codegraph_listener` — receives MinIO object-created webhooks on `/events/minio` and performs idempotent discovery inserts;
- `python -m memory_steward.codegraph_controller` — claims discovered rows and creates isolated Kubernetes index Jobs;
- `python -m memory_steward.codegraph_worker` with `CODEGRAPH_WORKER_MODE=index` — downloads the repository snapshot, verifies `.git`, resolves the exact Git SHA, performs full or safe incremental CodeGraph indexing, and persists the complete CodeGraph state back to MinIO.

The image pins the upstream CodeGraph engine version. Serve/reconcile worker modes remain future slices.
