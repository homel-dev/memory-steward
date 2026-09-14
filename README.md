# Memory Steward

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
~~~

FastMCP discovers tool schemas from the live server, so this CLI path does not duplicate the MCP contract. Open WebUI and `/glap` remain available as an optional conversational operator surface.

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
