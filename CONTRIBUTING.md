# CONTRIBUTING TO MEMORY STEWARD

## Engineering Contract

### 1. Authority

The current code and executable tests define current behavior. Documentation MUST be updated in the same change set so it accurately describes that behavior.

A design document may propose future behavior only when it is explicitly marked `PROPOSAL`, `DRAFT`, or `NOT IMPLEMENTED`.

### 2. Required Checks

Run the checks for each changed Python component:

~~~bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest
~~~

At repository level:

~~~bash
git diff --check
task --list
~~~

For Kubernetes/Taskfile changes, exercise the relevant tasks against a disposable or intended cluster and include the exact verification in the PR description.

### 3. Architecture Boundaries

- Router owns retrieval/context assembly and Builder dispatch.
- Steward owns durable dynamic-memory admission and structured agent outcome persistence.
- AMP MCP handlers delegate to Router/Steward APIs rather than duplicating policy.
- Canonical Reference Memory is explicitly ingested and remains distinct from learned dynamic memory and `agent_reference`.
- Telemetry is diagnostics data and is not automatically injected into Builder context.

### 4. Documentation

Follow [`docs/00_style_guide.md`](docs/00_style_guide.md).

Do not commit:

- stale endpoint/environment-variable examples;
- generated citation markers;
- claims about unimplemented classifiers, hysteresis, queues, or background jobs;
- commands using a namespace/resource name that differs from manifests.

### 5. Pull Requests

A PR is ready when:

- behavior is covered by tests where practical;
- lint/tests pass without CI rewriting files;
- docs match code;
- destructive operations remain explicit and guarded;
- `git diff --check` is clean.
