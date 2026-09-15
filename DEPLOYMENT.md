# DEPLOYMENT
## Minikube / Kubernetes Entry Points

### 0. Current Runtime Defaults

- Kubernetes namespace: `ms`
- Installer Minikube profile: `minikube`
- Repository Taskfile namespace: `ms`

### 1. Prerequisites

- `git`
- `kubectl`
- `minikube`
- `go-task` / `task` when using Taskfile operations
- `docker` when using `task tui`

### 2. Bootstrap

The repository installer is `install/install.sh`.

~~~bash
curl -fsSL https://sh.homel.dev/install-ms.sh | bash
~~~

The redirect/bootstrap mechanism is deployment infrastructure outside the repository runtime; the checked-in installer remains the source for what the local bootstrap actually performs.

### 3. Preferred Repository Workflow

~~~bash
task up             # deploy, wait, initialize, verify
task ops:service:status
task ops:service:wait
~~~

`task build` creates local `homel/*:dev` images in Minikube, but the checked-in manifests still reference GHCR images. It is therefore a developer image-build helper, not an implicit input to `task up`. To consume those local images, override the manifest image references/pull policy explicitly.

### 4. Workload Lifecycle

Restart stateless application services and the log collector:

~~~bash
task ops:service:restart
~~~

Restart stateful stores only explicitly:

~~~bash
task ops:storage:restart:postgres
task ops:storage:restart:qdrant
~~~

Tear down the namespace:

~~~bash
task down
~~~

`task down` deletes namespace `ms`; treat it as destructive because namespaced PVCs are removed with the namespace.

### 5. MCP Operator Access

Do not add a public MCP ingress for routine operator work.

~~~bash
task ops:mcp:tools
task ops:mcp:call -- ref_list
~~~

For the full-screen schema-driven operator client:

~~~bash
task tui
~~~

The task runs `steward-tui` in Docker and creates a loopback-only `kubectl port-forward` to the internal MCP Service. No host Python/FastMCP/Textual environment is required.

For a local MCP-capable application:

~~~bash
task ops:mcp:forward
## http://127.0.0.1:8081/mcp
~~~

### 6. Direct Kubernetes Inspection

~~~bash
kubectl get pods,svc -n ms
kubectl get deploy,statefulset,daemonset -n ms
~~~

### 7. Images

Current manifests include both fixed and floating tags. Do not assume every workload is digest/tag pinned. If reproducible production deployment is required, pin and verify all images in one explicit change set.

## 8. Full Lifecycle Task Reference

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
| ops:service:restart:mcp | Restart MCP |
| ops:service:restart:list | Restart LIST |
| ops:service:restart:embeddings | Restart embeddings |
| ops:service:restart:webui | Restart Open WebUI |
| ops:service:restart:vector | Restart Vector |
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

## 9. Suggested Bring-Up Verification

~~~bash
task up
task ops:service:wait
task ops:service:status
task ops:service:health
task ops:mcp:tools:json
task ops:diag:health
~~~

When Reference Memory is in scope, add a controlled list/search/get test. When AMP is in scope, run `task verify:amp`.

## 10. Troubleshooting Order

1. namespace/resources;
2. Postgres/Qdrant persistence/readiness;
3. embeddings;
4. Steward and Router;
5. MCP;
6. optional LIST/Open WebUI/Vector;
7. request-level telemetry and logs;
8. only then consider destructive reset/restore.

## 11. Current Image Caveat

The repository contains a local Minikube build helper, while checked-in manifests reference GHCR images. Treat local builds and deployed image selection as separate operations.
