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

The wait/status surface covers Postgres, Qdrant, embeddings, Router, Steward, MCP, LIST, Open WebUI, and Vector. `verify:health` performs HTTP readiness checks from the Router pod using Python `requests` (already present in the Router package) and uses `pg_isready` for Postgres; it does not assume `curl` exists in the Router image.

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

## 8. Closing Statement

A change is complete only when executable checks validate the affected behavior and deployment contract. Documentation examples are guidance; tests and runtime checks are the proof.

[Back to top](#navigation)

---

**END OF DOCUMENT 08**
