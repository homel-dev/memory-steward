# Memory Steward MCP

Memory Steward MCP is the internal operator and agent tool surface for Memory Steward.

It exposes FastMCP tools for Reference Memory ingestion/inspection, static-memory management, diagnostics, runtime configuration, Git ingestion, and AMP adapters. Agent-facing tools delegate retrieval to Memory Router and admission/feedback to Memory Steward rather than implementing a second policy engine.

The Kubernetes service is ClusterIP-only. Operators can use the repository Task targets (`task ops:mcp:tools`, `task ops:mcp:call`, and `task ops:reference:*`) or a loopback-only port-forward instead of exposing MCP publicly.

## Purpose

FastMCP internal control and adapter surface. It exposes content, stability/configuration, diagnostics, Git/repository, and agent-memory planes.

## Tool inventory

| Plane | Tool | Class | Purpose |
| --- | --- | --- | --- |
| content | ref_ingest_url | Mutating | Queue durable background ingestion of a reference URL |
| content | ref_ingest_text | Mutating | Ingest operator-provided reference text |
| content | ref_ingest_status | Read-only | Inspect one durable URL-ingestion job and progress |
| content | ref_ingest_jobs | Read-only | List recent durable URL-ingestion jobs |
| content | ref_ingest_cancel | Mutating | Cancel a queued job or request cancellation at the next batch boundary |
| content | ref_ingest_retry | Mutating | Explicitly requeue a failed/cancelled job |
| content | ref_list | Read-only | List reference ingestion namespaces/events |
| content | ref_inspect | Read-only | Inspect stored reference chunks by metadata |
| content | ref_purge | Destructive | Delete reference data for an explicit selection |
| content | static_list | Read-only | List static memory rows |
| content | static_create | Mutating | Create static memory |
| content | static_update | Mutating | Update a static-memory row |
| content | static_toggle | Mutating | Enable or disable static memory |
| content | static_delete | Destructive | Delete a static-memory row |
| content | cache_control | Process-local | Control the MCP process-local static-memory cache only |
| stability | config_set_budget | Mutating | Persist MAX_CONTEXT_TOKENS consumed by Router |
| stability | config_force_mode | Compatibility | Persist FORCE_MODE; current Router/Steward do not consume it |
| stability | config_set_hysteresis | Compatibility | Persist HYSTERESIS_WINDOW; no current hysteresis engine consumes it |
| stability | config_show | Read-only | Show runtime_config values and current-consumer annotations |
| diagnostics | diag_health | Read-only | Aggregate service health information |
| diagnostics | diag_explain | Read-only | Inspect telemetry for a request |
| diagnostics | diag_explain_last | Read-only | Inspect most recent request telemetry |
| diagnostics | diag_metrics | Read-only | Summarize operational telemetry |
| diagnostics | diag_qdrant_stats | Read-only | Inspect Qdrant collection statistics |
| diagnostics | dyn_inspect | Read-only | Inspect dynamic-memory rows |
| diagnostics | dyn_simulate_retrieval | Read-only | Simulate dynamic retrieval for troubleshooting |
| diagnostics | diag_logs | Read-only | Read shared collected logs |
| git | repo_add | Mutating | Register repository metadata/connection |
| git | repo_list | Read-only | List registered repositories |
| git | repo_remove | Mutating | Remove repository registration |
| git | repo_test | Read-only/network | Test repository access |
| git | git_list_repos | Read-only | List Git repositories available through the Git plane |
| git | git_ingest_repo | Mutating | Ingest repository content into reference memory |
| git | git_ingest_file | Mutating | Ingest one repository file into reference memory |
| git | git_write_file | Mutating external | Write a repository file when explicitly invoked and authorized |
| agent | memory.retrieve_context | Read-only | Adapter to Router /v1/context/retrieve |
| agent | memory.reference.search | Read-only | Adapter to Router reference search |
| agent | memory.reference.get | Read-only | Adapter to Router reference get |
| agent | memory.submit_agent_outcome | Mutating | Adapter to Steward structured outcome admission |
| agent | memory.submit_context_feedback | Mutating | Adapter to Steward context feedback |

## Network posture

Keep the service internal. For local clients use `task ops:mcp:forward` and `http://127.0.0.1:8081/mcp`.

## Cache note

`cache_control` affects only the MCP process-local static cache; Router does not use that cache.

## Compatibility config note

`config_force_mode` and `config_set_hysteresis` persist compatibility values that have no current Router/Steward policy consumer.

## Reference ingestion execution

`ref_ingest_url` does not fetch or embed the document in the MCP request. It writes a durable `reference_ingestion_jobs` row and returns the job id. The `reference-ingest-worker` Deployment claims jobs with `FOR UPDATE SKIP LOCKED`, fences updates by worker id plus attempt count, fetches with a 64 MiB decompressed-content ceiling, and embeds/upserts in bounded batches. Qdrant writes use `wait=true`; completion and the immutable `reference_ingestion` provenance row are committed together in Postgres.

`ref_ingest_text` and Git ingestion are synchronous but share the same bounded batch implementation.
