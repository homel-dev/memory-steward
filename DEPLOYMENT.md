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
