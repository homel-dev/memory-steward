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

## 6. Documentation Completeness Requirement

Documentation must retain operational and architectural detail when implementation changes. Do not replace a detailed contract with a short summary merely to make the repository look cleaner. Update stale details in place, preserve still-valid rationale, and mark future behavior explicitly.

A documentation-sensitive PR should identify affected numbered documents in its description.

## 7. Patch and Base Verification

When producing a patch outside the repository host:

1. start from a fresh clone/pull or an explicitly supplied exact repository archive;
2. record the base commit/tree identity;
3. generate the patch using Git itself;
4. apply it to a second untouched copy of the same base with `git apply --check`;
5. run `git diff --check` and applicable lint/tests;
6. never claim verification that was not executed.

## 8. Boundary Review

Changes touching memory admission, reference retrieval, MCP mutation tools, or agent artifacts require an explicit authority review. State which component reads/writes which store and how the behavior fails.

## 9. CI Expectations

CI is check-only for source formatting. Do not depend on CI to auto-fix Ruff errors. Organization policy also verifies repository hygiene, Markdown structure, pinned actions, YAML, and shell scripts.
