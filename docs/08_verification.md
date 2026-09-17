# VERIFICATION
## Executable Checks for the Current Repository
### Foundational Engineering Specification (Document 08 of 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

**← [Prev: Document 07 (Management)](07_glass_pane.md) | [Next: Document 09 (Runtime Contract)](09_runtime_contract.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Static Checks](#1-static-checks)
- [2. Router Regression Targets](#2-router-regression-targets)
- [3. Steward Regression Targets](#3-steward-regression-targets)
- [4. MCP Regression Targets](#4-mcp-regression-targets)
- [5. Kubernetes Verification](#5-kubernetes-verification)
- [6. Failure Behavior](#6-failure-behavior)
- [7. Definition of Done](#7-definition-of-done)
- [8. Closing Statement](#8-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED
**Audience:** Maintainers, QA, release engineers
**Change policy:** Living implementation-aligned document; no silent behavioral drift.

Verification follows the current code and manifests; examples in this document are not substitutes for component tests.

[Back to top](#navigation)

---

## 1. Static Checks

For each Python component:

~~~bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest
~~~

CI MUST check rather than auto-fix source files. Formatting/lint fixes belong in the change set, not in the CI workspace.

[Back to top](#navigation)

---

## 2. Router Regression Targets

At minimum verify:

- `/healthz` and `/v1/models` contracts;
- `/glap` intercept does not invoke Builder;
- static global rules are rendered into the Builder envelope;
- dynamic and reference Qdrant filters preserve memory-type isolation;
- `reference_filters` rejects unknown keys and passes exact filters through;
- AMP context retrieval does not call Builder;
- Builder history pruning is applied to the payload actually sent upstream;
- streaming responses remain valid SSE.

[Back to top](#navigation)

---

## 3. Steward Regression Targets

Verify:

- `/admit` extraction/persistence error boundaries;
- agent outcome idempotency and conflict behavior;
- artifact hash validation and `agent_reference` persistence;
- context-feedback persistence;
- Qdrant upserts use the correct memory type/project metadata.

[Back to top](#navigation)

---

## 4. MCP Regression Targets

Verify live registration and schema shape for content, config, diagnostics, Git, and AMP tools. Transport adapters must preserve Router/Steward ownership of the underlying operations.

[Back to top](#navigation)

---

## 5. Kubernetes Verification

~~~bash
task up
task ops:service:wait
task ops:service:status
task verify:health
task verify:amp
~~~

The wait/status surface covers Postgres, Qdrant, embeddings, Router, Steward, MCP, the reference-ingest worker, LIST, CodeGraph, Open WebUI, and Alloy. `verify:health` performs HTTP readiness checks from the Router pod using Python `requests` (already present in the Router package) and uses `pg_isready` for Postgres; it does not assume `curl` exists in the Router image.

[Back to top](#navigation)

---

## 6. Failure Behavior

Do not document a degraded-mode guarantee unless a test proves it. In particular, failures of Postgres/Qdrant can affect different request phases; verification should assert observed endpoint behavior rather than assume that chat always succeeds with “static only”.

[Back to top](#navigation)

---

## 7. Definition of Done

A behavior change is complete when:

- relevant tests pass;
- Ruff passes without modifying files;
- `git diff --check` is clean;
- task/manifests affected by the change are exercised against the target cluster when applicable;
- documentation matches the behavior represented by the merged code.

[Back to top](#navigation)

---

## 8. CI Contract

The repository CI runs component-specific tests and Ruff checks. Optional components that genuinely contain no tests may explicitly tolerate pytest exit code 5; core components must not hide that result.

The repository also calls the organization reusable repository-standards workflow pinned to a reviewed commit. That workflow checks mechanical repository policy, YAML, Bash syntax, and ShellCheck errors.

Important policy characteristics include:

- third-party GitHub Actions pinned to full commit SHAs;
- explicit top-level workflow permissions;
- checkout credentials not persisted when unnecessary;
- UTF-8 and final-newline hygiene;
- no trailing whitespace in tracked text/config files;
- local Markdown-link validation;
- one Markdown H1 per document;
- secret-pattern scanning;
- YAML lint and shell syntax/static analysis.

## 9. Component Verification Matrix

| Component | Primary checks | Critical regression targets |
| --- | --- | --- |
| memory-router | Ruff + pytest | history pruning, reference filters, structured context, MCP bridge, static/dynamic/reference separation |
| memory-steward | Ruff + pytest | fragment extraction parsing, persistence behavior, AMP idempotency/artifacts/feedback |
| memory-steward-mcp | Ruff + pytest | tool registration, durable reference-ingestion queue/batching, reference agent adapters, config/diagnostic contracts |
| memory-steward-list | Ruff + pytest when present | route contract and transcription service behavior |
| embeddings | Ruff + pytest | health/embed contract, request-size rejection, bounded FastEmbed invocation |
| steward_tui | pytest/ruff when integrated into CI or run manually | schema parsing, type coercion, tool discovery/invocation rendering |

## 10. Documentation Verification

Documentation changes MUST be verified mechanically as repository content, not reviewed only for prose quality.

Minimum checks:

~~~bash
git diff --check
~~~

and the organization repository policy used by CI. Reviewers SHOULD additionally verify that every named Task, route, table, environment variable, tool, and file exists in the current tree.

## 11. Kubernetes and Taskfile Verification

| Area | Check |
| --- | --- |
| Namespace/resources | Apply manifests to intended/disposable cluster and inspect `kubectl get` state |
| Service health | Use repository in-cluster health Task rather than assuming host curl availability |
| Application restart | Verify deployments return Available |
| Stateful restart | Use prompted Postgres/Qdrant restart tasks and verify data readiness |
| MCP | List live tools and call a read-only diagnostic operation |
| Reference lane | Ingest/search/get test data in a non-production namespace or controlled corpus |
| Reference URL worker | Queue a controlled URL, inspect progress, verify bounded completion/cancel/retry behavior |
| AMP | Run `task verify:amp` and inspect idempotency/artifact behavior |
| Images | Confirm manifests reference the intended published tags/digests; local `task build` alone does not alter GHCR references |

## 12. Negative Tests Required by Boundary Changes

Architecture-sensitive changes need negative tests. Examples:

- unknown `reference_filters` field is rejected;
- no filters add no hidden product/version narrowing;
- same AMP `outcome_id` with different payload returns 409;
- ordinary chat cannot write Reference Memory;
- missing Builder history budget does not reintroduce dropped messages;
- compatibility mode keys do not change Router behavior without a consumer;
- LIST does not require Postgres secrets;
- MCP destructive tools remain explicit;
- admission-control provisioned schema is not presented as active runtime.

## 13. Definition of Done: Detailed

A change is complete only when all applicable items are satisfied:

1. code compiles/imports in the supported environment;
2. relevant component tests pass;
3. Ruff passes without CI rewriting source;
4. organization repository standards pass;
5. manifests parse/lint;
6. shell scripts pass syntax/ShellCheck error checks;
7. docs describe current behavior at the same level of detail as the affected contract;
8. no stale names/routes/tasks remain in current-state documentation;
9. operational verification is recorded for topology/lifecycle changes;
10. destructive behavior is guarded;
11. secret handling remains explicit;
12. observability exists for newly introduced critical behavior;
13. proposal-only behavior is labeled as proposal;
14. `git diff --check` is clean.

## 14. Release/Deployment Smoke Sequence

~~~text
CI green
  -> deploy/apply manifests
  -> wait Postgres/Qdrant
  -> wait embeddings
  -> wait Router/Steward/MCP
  -> run health checks
  -> list MCP tools
  -> run AMP verification when changed
  -> perform representative Router request
  -> inspect telemetry/logs
  -> verify optional LIST/TUI only if in release scope
~~~

## 15. Evidence Expectations

Verification claims should state exactly what ran. Avoid statements such as “all tests pass” when only syntax checks were run. For patches generated outside the repository host, record base commit/tree identity and run `git apply --check` against an untouched copy of the exact base before handing off the patch.

---

## 8. Closing Statement

A change is complete only when executable checks validate the affected behavior and deployment contract. Documentation examples are guidance; tests and runtime checks are the proof.

[Back to top](#navigation)

---

**END OF DOCUMENT 08**


## Appendix A. Operator Task Verification Inventory

| Task | Expected purpose |
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
| ops:service:restart:mcp | Restart MCP |
| ops:service:restart:list | Restart LIST |
| ops:service:restart:embeddings | Restart embeddings |
| ops:service:restart:webui | Restart Open WebUI |
| ops:service:restart:alloy | Restart namespace Alloy collector |
| ops:storage:restart:postgres | Prompted Postgres restart |
| ops:storage:restart:qdrant | Prompted Qdrant restart |
| ops:mcp:tools | List live MCP tools |
| ops:mcp:tools:json | List live MCP tools as JSON |
| ops:mcp:call | Call arbitrary live MCP tool |
| ops:mcp:forward | Loopback-only MCP port-forward |
| ops:ref:list | Reference list shortcut |
| ops:ref:inspect | Reference inspect shortcut |
| ops:ref:ingest:url | Reference URL ingestion shortcut |
| ops:ref:ingest:text | Reference text ingestion shortcut |
| ops:ref:purge | Prompted reference purge shortcut |
| ops:ref:search | Reference search shortcut |
| ops:ref:get | Reference get shortcut |
| ops:config:show | Show runtime config |
| ops:diag:health | Diagnostics health shortcut |
