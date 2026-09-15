# <img src="docs/img/logo2.jpeg" width="100" alt="Memory Steward logo"> Memory Steward

[![CI](https://github.com/homel-dev/memory-steward/actions/workflows/main.yml/badge.svg)](https://github.com/homel-dev/memory-steward/actions/workflows/main.yml)
[![Build images](https://github.com/homel-dev/memory-steward/actions/workflows/build_image.yml/badge.svg)](https://github.com/homel-dev/memory-steward/actions/workflows/build_image.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE-2.0.txt)

Memory Steward is a self-hosted memory control plane for LLM and agent workloads. It separates retrieval, admission, operator control, transcription, storage, and observability into explicit services with narrow contracts.

## Runtime architecture

| Component | Responsibility |
| --- | --- |
| `memory-router` | OpenAI-compatible chat ingress, project resolution, static/dynamic/reference retrieval, MMR, token budgeting, prompt-envelope rendering, Builder dispatch, async chat admission |
| `memory-steward` | Durable-memory admission from chat turns and structured agent outcomes; canonical `agent_reference` persistence; context feedback |
| `memory-steward-mcp` | Internal operator/agent control surface implemented with FastMCP |
| `steward-tui` | Textual Glass Pane client that discovers and invokes live MCP tool schemas |
| `memory-steward-list` | Optional local speech transcription service; translation endpoint is present but currently returns HTTP 501 |
| `embeddings` | Dense embedding service used by Router and Steward |
| Postgres | Canonical structured state, runtime configuration, telemetry, ingestion records, agent artifacts |
| Qdrant | Semantic retrieval index for dynamic and canonical reference memory |
| Open WebUI | Optional chat/operator frontend; `/glap` is bridged by Memory Router to the MCP server |
| Vector | Cluster log collection |
| OCO | Shared Grafana presentation plane; Memory Steward publishes datasource/dashboard ConfigMaps |

The code is the runtime authority. Documentation describes the behavior present in the current tree; proposals that are not implemented are explicitly marked as such.

## Request paths

### Chat

~~~text
Open WebUI / OpenAI client
  -> POST /v1/chat/completions (memory-router)
  -> static + dynamic + eligible reference retrieval
  -> MMR + token budget
  -> canonical context envelope
  -> Builder LLM
  -> response
  -> async POST /admit (memory-steward)
~~~

### Agent Memory Protocol

~~~text
Agent
  -> POST /v1/context/retrieve (memory-router)
     or memory.retrieve_context (MCP)
  -> structured governed context, no Builder call

Agent
  -> POST /v1/agent/outcomes (memory-steward)
     or memory.submit_agent_outcome (MCP)
  -> governed durable-memory extraction + canonical agent_reference artifacts
~~~

### Operator control

The MCP service is ClusterIP-only. Operators do not need to expose it publicly. The repository provides Task wrappers that execute the FastMCP client inside the MCP pod:

~~~bash
task ops:mcp:tools
task ops:mcp:call -- ref_list
task ops:ref:inspect -- product=kicad version=9.0 limit=10
task ops:ref:ingest:url -- url=https://example.invalid/docs product=kicad version=9.0 scope=pcb
task ops:mcp:forward
task tui
~~~

FastMCP discovers tool schemas from the live server, so this CLI path does not duplicate the MCP contract. Open WebUI and `/glap` remain available as an optional conversational operator surface.

`task tui` launches the packaged `steward-tui` image in Docker and creates a loopback-only `kubectl port-forward` to `memory-steward-mcp`. The host does not need Python, FastMCP, or Textual installed; the TUI runtime stays containerized.

## Operational mode: current behavior

There is currently **no mode classifier** in `memory-steward`.

`mode` is optional caller-supplied metadata. The Router uses it for:

- selecting `static_mode_conditioned` rows when a matching mode is supplied;
- reference-memory eligibility (`engineering`, `implementation`, `formal_spec`).

When `mode` is absent, only global static rules match, while the reference lane currently uses `engineering` as its fallback eligibility mode. `FORCE_MODE` and `HYSTERESIS_WINDOW` can be persisted by legacy MCP tools, but the current Router does not consume those keys; they therefore have no runtime effect.

## Reference memory: current behavior

Canonical reference memory is ingested explicitly through MCP content-plane tools (`ref_ingest_url`, `ref_ingest_text`) and stored/indexed with `memory_type=reference_memory`.

Router retrieval always filters on `memory_type=reference_memory`. Optional exact-match `reference_filters` may narrow by:

- `product`
- `version`
- `scope`
- `provider`
- `source`

No product/version narrowing is synthesized when the caller omits filters.

## Lifecycle

~~~bash
task up
task status:all
task ops:service:status
task ops:service:wait
task ops:service:restart
task down
~~~

`task build` is a separate developer helper that creates `homel/*:dev` images inside Minikube. The checked-in Kubernetes manifests still reference GHCR images, so `task build` does **not** change what `task up` deploys unless the manifests/image policy are explicitly overridden.

Stateful Postgres and Qdrant restarts are intentionally separate and prompted:

~~~bash
task ops:storage:restart:postgres
task ops:storage:restart:qdrant
~~~

## Validation

The repository CI runs component tests and Ruff checks. Before merging changes, run the equivalent component commands locally or in CI and verify the Kubernetes manifests/tasks against the target cluster.

## Documentation

- [`docs/00_style_guide.md`](docs/00_style_guide.md) — documentation rules and authority
- [`docs/01_overview.md`](docs/01_overview.md) — implemented architecture
- [`docs/02_operational_mode.md`](docs/02_operational_mode.md) — current mode semantics
- [`docs/03_reference.md`](docs/03_reference.md) — canonical reference memory
- [`docs/04_optimizations.md`](docs/04_optimizations.md) — implemented optimizations and explicit backlog
- [`docs/05_stability.md`](docs/05_stability.md) — live configuration and non-implemented stability features
- [`docs/06_telemetry.md`](docs/06_telemetry.md) — telemetry model
- [`docs/07_glass_pane.md`](docs/07_glass_pane.md) — MCP/operator surfaces
- [`docs/08_verification.md`](docs/08_verification.md) — verification expectations
- [`docs/09_runtime_contract.md`](docs/09_runtime_contract.md) — runtime topology/configuration
- [`docs/10_industry_landscape.md`](docs/10_industry_landscape.md) — background research
- [`docs/11_design_principles.md`](docs/11_design_principles.md) — design principles
- [`docs/12_extensions.md`](docs/12_extensions.md) — optional LIST and AMP extensions
- [`docs/13_admission_control.md`](docs/13_admission_control.md) — provisioned admission-control schema plus proposed runtime pipeline; current active boundary is explicit

## License

Apache-2.0. See [`LICENSE-2.0.txt`](LICENSE-2.0.txt).

## Detailed Runtime Reference

### API inventory

| Component | Method | Path | Purpose | Mutation |
| --- | --- | --- | --- | --- |
| memory-router | GET | /healthz | Liveness/availability check | No memory mutation |
| memory-router | GET | /v1/models | Expose effective Builder model | Reads runtime Builder model selection |
| memory-router | POST | /v1/chat/completions | OpenAI-compatible chat ingress | Retrieves context, calls Builder, dispatches ordinary-chat admission asynchronously |
| memory-router | POST | /v1/context/retrieve | Structured context retrieval for agents | No Builder call; returns governed context plus accounting |
| memory-router | POST | /v1/reference/search | Canonical Reference Memory search | Exact optional metadata filters; project context from request headers |
| memory-router | GET | /v1/reference/{chunk_id} | Fetch one reference chunk | 404 when absent |
| memory-steward | GET | /healthz | Steward liveness | No mutation |
| memory-steward | POST | /admit | Ordinary-chat durable-memory admission | LLM extraction followed by Postgres/Qdrant persistence |
| memory-steward | POST | /v1/agent/outcomes | Structured agent outcome submission | Idempotency, deterministic artifact persistence, optional durable-knowledge extraction |
| memory-steward | POST | /v1/context/feedback | Context usefulness feedback | Stores used/irrelevant/missing-context feedback and telemetry |
| memory-steward-list | GET | /healthz | LIST liveness | No database dependency |
| memory-steward-list | POST | /v1/audio/transcriptions | OpenAI-style transcription alias | Local Whisper transcription |
| memory-steward-list | POST | /v1/list/transcribe | Canonical LIST transcription route | Local Whisper transcription |
| memory-steward-list | POST | /v1/list/translate | Reserved translation route | Currently returns HTTP 501 |
| embeddings | GET | /healthz | Embedding service liveness | Reports model readiness |
| embeddings | POST | /embed | Dense embedding generation | Used by Router and Steward |

### Memory and evidence lanes

| Lane | Primary source | Selection | Primary authority |
| --- | --- | --- | --- |
| static_global | Human/operator | Always-active static rows | Human/operator |
| static_mode_conditioned | Human/operator | Exact supplied mode | Human/operator |
| dynamic_memory | Steward extraction | Project-scoped semantic retrieval | Steward |
| reference_memory | Explicit source ingestion | Semantic + exact metadata filters | External/operator source |
| agent_reference | Structured agent artifacts | Explicit artifact selectors | Deterministic agent output/provenance |
| telemetry | Runtime writers | Diagnostics only | System evidence, not prompt memory |

### MCP and TUI

The MCP server is the shared internal control surface. The repository also includes `components/steward_tui`, a Textual client that discovers the live tool schema and renders forms dynamically. Use loopback port-forward rather than exposing MCP publicly for routine administration.

~~~bash
task ops:mcp:forward
## separate terminal / environment with steward-tui installed
STEWARD_MCP_URL=http://127.0.0.1:8081/mcp steward-tui
~~~

### Important current limits

- No automatic mode classifier or active hysteresis engine.
- `FORCE_MODE` and `HYSTERESIS_WINDOW` are compatibility/diagnostic values without current policy consumers.
- Ordinary chat admission is asynchronous best-effort, not a durable queue.
- Migration 060 provisions audited-admission tables, but the deterministic gate/Auditor/quarantine runtime is not implemented.
- Agent artifacts are not automatically promoted to canonical Reference Memory.
- MCP static cache is process-local and is not the Router retrieval cache.

### Core operational tasks

| Task | Operational purpose |
| --- | --- |
| up | Deploy namespace/resources and wait for core services |
| down | Delete namespace ms |
| status:all | Show workload/resource state |
| nuke | Destructive cleanup path |
| build | Build local development images inside Minikube; does not rewrite GHCR manifests |
| k8s:deploy | Apply Kubernetes manifests |
| k8s:wait | Wait for configured workloads |
| k8s:restart | Restart application workloads |
| db:init | Initialize Postgres schema |
| db:init-qdrant | Initialize Qdrant collection |
| db:reset | Reset state with destructive confirmation |
| db:shell | Open Postgres shell |
| migrate:up | Apply canonical SQL migrations |
| migrate:status | Inspect migration status |
| backup | Create state backup |
| restore | Restore backup with safeguards |
| export:memory | Export memory data |
| export:fetch | Fetch exported data |
| verify:health | Run in-cluster health verification |
| verify:amp | Run Agent Memory Protocol checks |
| logs:router | Tail Router logs |
| logs:steward | Tail Steward logs |
| ops:service:status | Show complete service status |
| ops:service:wait | Wait for full service set |
| ops:service:health | Call health endpoints from an in-cluster context |
| ops:app:stop | Scale/stop application workloads |
| ops:app:start | Start application workloads |
| ops:service:restart | Restart application services |
| ops:service:restart:router | Restart Router |
| ops:service:restart:steward | Restart Steward |

For the complete operational reference, see [`DEPLOYMENT.md`](DEPLOYMENT.md), [`docs/07_glass_pane.md`](docs/07_glass_pane.md), and [`docs/09_runtime_contract.md`](docs/09_runtime_contract.md).
