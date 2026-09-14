# Memory Router

Memory Router is the synchronous retrieval and inference orchestration service for Memory Steward.

It exposes the OpenAI-compatible chat endpoint, structured context retrieval for AMP clients, and read-only Reference Memory search/get endpoints. It reads canonical static state from Postgres, retrieves semantic context from Qdrant, assembles the canonical context envelope, calls the configured Builder endpoint, records telemetry, and submits completed chat turns to Memory Steward for asynchronous admission.

The Router does not perform durable-memory admission. Operational `mode`, when supplied, is caller metadata used for retrieval gating; the current Router does not classify mode itself.

Runtime configuration is supplied by Kubernetes environment/config resources. See the repository root `README.md`, `docs/09_runtime_contract.md`, and `Taskfile.yml` for deployment and operations.
