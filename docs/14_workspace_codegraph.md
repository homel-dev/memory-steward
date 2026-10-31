# RR WORKSPACE CODEGRAPH SOURCE
## Kubernetes Event notification, immutable source archive and full CodeGraph generation
### Engineering Extension (Document 14)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Source contract](#1-source-contract)
- [2. Lifecycle](#2-lifecycle)
- [3. Access and operations](#3-access-and-operations)
- [4. Limitations](#4-limitations)
- [5. Closing Statement](#5-closing-statement)

## 0. Status, Scope, and Authority

**Status:** IMPLEMENTED in this patch; deployment and Kubernetes runtime not verified.
**Audience:** Memory Steward and RR integrators.
**Change policy:** The event carries an immutable artifact reference; the controller owns the build decision.

[Back to top](#navigation)

## 1. Source contract

RR uploads a gzip TAR of the exact Git workspace to MinIO bucket `codegraph` under `rr/workspaces/`. RR computes the SHA-256 digest of the archive bytes, in lowercase hex. The archive MUST capture modified and untracked project files as well as tracked files. The `revision` field is a full lowercase Git commit SHA. Neither repository URL nor Git SHA alone identifies the complete workspace snapshot.

RR creates a Kubernetes `v1/Event` in namespace `rr` with `reason: CodeGraphWorkspaceSnapshot`, `type: Normal`, and a JSON `message`:

~~~json
{
  "project_id": "rr-project",
  "run_id": "example-run",
  "repository": "local-gitlab/project",
  "revision": "0000000000000000000000000000000000000000",
  "snapshot_digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "bucket": "codegraph",
  "key": "rr/workspaces/example.tar.gz"
}
~~~

The event never carries repository content. The allowed bucket is configured by `CODEGRAPH_WORKSPACE_SOURCE_BUCKET` (default `codegraph`). The workspace controller watches `CODEGRAPH_WORKSPACE_EVENT_NAMESPACE` (default `rr`). The `rr/workspaces/` key prefix is fixed.

[Back to top](#navigation)

## 2. Lifecycle

1. Kubernetes Event watcher validates the source reference and records the build in PostgreSQL (`codegraph_builds`). Deduplication identity is project + repository + snapshot SHA-256. An existing build is reused across RR runs.
2. The existing controller submits the existing Argo `codegraph-build` Workflow using the workspace MinIO source, `index_profile=full` and the existing `memory_steward.codegraph_worker`.
3. The Worker downloads the private MinIO archive using its configured credentials and verifies the complete archive digest before extraction or index computation.
4. The controller observes Argo completion and publishes an immutable `cg-serve-<build-id>` backend. Workspace builds never change the Flux `repository:latest` alias.
5. Ready status requires a successful Workflow, validated generation result and a Ready serving Deployment. Until then, status is not `ready`.
6. The existing `POST /v1/codegraph/capability-sessions` accepts an optional `snapshot_digest`; with this value it resolves a matching published workspace build, binds it to the requested run and issues the existing session credential. Other callers retain their existing behavior.

No extra scheduler or indexing implementation is introduced; the existing Argo and CodeGraph runtime owns execution.

[Back to top](#navigation)

## 3. Access and operations

Use the internal controller Service for status:

~~~text
GET http://codegraph-controller.ms.svc.cluster.local:8093/v1/codegraph/workspace-builds?project_id=rr-project&repository=local-gitlab%2Fproject&snapshot_digest=sha256%3A...
~~~

Responses have `state`, `ready`, and when known `build_id`, `revision`, `worker_endpoint`, `error`. `missing` means the event has not been recorded. `received/submitted/running` means a build exists but is not ready; `failed` is terminal. `succeeded` without `worker_endpoint` is still serving preparation, not READY. The caller polls this endpoint and MUST NOT issue a CodeGraph capability until `ready=true`.

Read-only operator checks:

~~~bash
kubectl -n rr get events --field-selector reason=CodeGraphWorkspaceSnapshot
kubectl -n ms logs deployment/codegraph-controller --since=30m
kubectl -n ms get workflows.argoproj.io -l app=codegraph-build
~~~

The controller Service status endpoint is cluster-internal, not automatically exposed via the llm-runtime Gateway. RR needs connectivity to that service. RR also requires permission to create Kubernetes Events in `rr` and to publish the archive in MinIO; these are RR-side prerequisites, not granted by this patch.

[Back to top](#navigation)

## 4. Limitations

The new source requires the CI-built Memory Steward image and applied SQL migration. The event source is a Kubernetes Event, whose retention is finite; RR polls status after emission. An event that never reaches the watcher leaves status `missing` until the next explicit submission. Duplicate event submissions are idempotent. The `snapshot_digest` identifies archive bytes, not Git HEAD alone. The consumer requires a lowercase Git SHA and a `sha256:` archive digest. Serving cleanup for workspace builds is not automatic in this patch; Flux serving garbage collection remains unchanged.

The existing CodeGraph MCP exposure remains restricted to read-only `AGENT_CODEGRAPH_TOOLS`. Full indexing (`index_profile=full`) does not expose administrative or mutation tools to agents.

[Back to top](#navigation)

## 5. Closing Statement

This extension adds RR workspace indexing as a distinct input while retaining the Flux path and its `graph-only` profile. The exact workspace snapshot, not a similarly named upstream repository, is the indexed source.

[Back to top](#navigation)

---
END OF DOCUMENT
