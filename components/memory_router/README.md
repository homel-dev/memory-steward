# Memory Router

Memory Router is the synchronous retrieval and inference orchestration service for Memory Steward.

It exposes the OpenAI-compatible chat endpoint, structured context retrieval for AMP clients, and read-only Reference Memory search/get endpoints. It reads canonical static state from Postgres, retrieves semantic context from Qdrant, assembles the canonical context envelope, calls the configured Builder endpoint, records telemetry, and submits completed chat turns to Memory Steward for asynchronous admission.

The Router does not perform durable-memory admission. Operational `mode`, when supplied, is caller metadata used for retrieval gating; the current Router does not classify mode itself.

Runtime configuration is supplied by Kubernetes environment/config resources. See the repository root `README.md`, `docs/09_runtime_contract.md`, and `Taskfile.yml` for deployment and operations.

## Responsibilities

- OpenAI-compatible chat ingress.
- Structured agent context retrieval.
- Static/dynamic/reference/exact-artifact context assembly.
- MMR and token budgeting.
- Builder dispatch and streaming proxy behavior.
- `/glap` MCP bridge.
- Router request/retrieval telemetry.
- Asynchronous ordinary-chat admission dispatch to Steward.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /healthz | Liveness/availability check |
| GET | /v1/models | Expose effective Builder model |
| POST | /v1/chat/completions | OpenAI-compatible chat ingress |
| POST | /v1/context/retrieve | Structured context retrieval for agents |
| POST | /v1/reference/search | Canonical Reference Memory search |
| GET | /v1/reference/{chunk_id} | Fetch one reference chunk |

## Key configuration

| Variable | Default/value | Purpose |
| --- | --- | --- |
| POSTGRES_SERVICE_HOST / POSTGRES_SERVICE_PORT | required via Kubernetes service discovery | Postgres address |
| POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB | required | Database credentials/database |
| POSTGRES_SSLMODE | disable | Postgres TLS mode |
| POSTGRES_APPLICATION_NAME | memory-router | Postgres application_name |
| QDRANT_SERVICE_HOST / QDRANT_SERVICE_PORT | required | Qdrant address |
| EMBEDDINGS_SERVICE_HOST / EMBEDDINGS_SERVICE_PORT | required | Embeddings address |
| QDRANT_COLLECTION | required | Qdrant collection |
| BUILDER_BASE_URL | service-derived when unset | Builder OpenAI-compatible base URL |
| BUILDER_API_KEY | local-token | Builder API key |
| BUILDER_MODEL | required | Builder model |
| MEMORY_STEWARD_SERVICE_HOST / MEMORY_STEWARD_SERVICE_PORT | required | Steward address |
| MAX_CONTEXT_TOKENS | 8192 code default; 128000 manifest value | Retrieval context budget |
| MAX_TOTAL_TOKENS | 16384 code default; 262144 manifest value | Prompt-input planning ceiling |
| DENSE_PREFETCH | 25 | Dense candidate prefetch |
| TOP_K | 8 | Final candidate cap |
| MMR_LAMBDA | 0.5 | MMR relevance/diversity balance |
| DEBUG_PROMPTS | false-like default | Full prompt debug logging; disabled in deployment |
| REFERENCE_RETRIEVAL_ENABLED | true-like default | Global reference lane toggle |
| RUNTIME_CONFIG_TTL_SECONDS | 5 | runtime_config cache TTL |
| MCP_URL | required by MCP bridge deployment | MCP endpoint for /glap |

## Important invariants

- Uses pruned history in the final Builder payload.
- Does not decide durable learned-memory admission.
- Reference queries always include `memory_type=reference_memory` and only explicit whitelisted metadata filters.
- No automatic mode classifier exists.
- Structured `/v1/context/retrieve` does not invoke Builder.

## Tests

Router tests cover unit, integration, history budget, reference API, and MCP bridge behavior. Run Ruff and pytest from this component directory.
