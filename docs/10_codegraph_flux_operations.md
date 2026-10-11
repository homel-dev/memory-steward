# CodeGraph Flux Build Operations and End-to-End Verification

**Scope:** the implemented Flux `GitRepository` artifact → Memory Steward PostgreSQL controller → Argo Workflow → CodeGraph generation in MinIO. Serving and MCP query capability are not part of this path. No alerting is provisioned by this runbook.

## Data flow and durable evidence

1. Flux source-controller publishes a `GitRepository.status.artifact` with `url`, `revision`, and `digest`.
2. Flux notification delivery must route a `NewArtifact` event to `POST /events/flux` on `codegraph-controller.ms:8093`. A `Provider` and `Alert` may be managed outside this repository; **their existence and delivery must be checked**, not inferred from the controller Deployment.
3. The ingress records one row in `public.codegraph_builds` for each source identity and artifact digest. Duplicate events return the existing `build_id`.
4. The controller compares the event with the current Flux artifact, then either marks it `superseded` or creates an Argo Workflow from `WorkflowTemplate/codegraph-build` in namespace `ms`.
5. Argo runs the `flux-index` worker, which downloads and verifies the exact source artifact, indexes it, and writes a generation bundle and `.result.json` to MinIO.
6. The controller observes Argo, validates the worker result identity, and records `succeeded` or `failed` in PostgreSQL.

The durable state sequence is `received → submitted → running → succeeded`, with terminal `failed` and `superseded` alternatives. `running` may be skipped in the database if Argo completes between controller observations. `/healthz` reports HTTP process liveness only; it does not prove DB, Flux, Argo, or MinIO readiness.

## Read-only verification in the minikube context

The commands below do not submit events or start builds. They inspect whichever activity is already present.

### 1. Source event and delivery prerequisites

```bash
kubectl get gitrepositories.source.toolkit.fluxcd.io -A
kubectl get providers.notification.toolkit.fluxcd.io,alerts.notification.toolkit.fluxcd.io -A
kubectl -n ms get deployment/codegraph-controller service/codegraph-controller workflowtemplate/codegraph-build
kubectl -n ms logs deployment/codegraph-controller --since=2h --timestamps
```

Find the intended source's `status.artifact.revision` and `status.artifact.digest` with:

```bash
kubectl -n flux-system get gitrepository SOURCE_NAME -o jsonpath='{.status.artifact}'
```

Replace `SOURCE_NAME` with the actual `GitRepository` and its namespace if different. A healthy source artifact without a corresponding PostgreSQL row means the ingress/delivery path is unproven; inspect Flux `Alert`/`Provider` and controller logs. Do not interpret `/healthz=200` as evidence that a `NewArtifact` was delivered.

### 2. Durable build status and failure details

```bash
kubectl -n ms exec statefulset/postgres -- psql -U homel -d homel -P pager=off -c '
SELECT id, source_namespace, source_name, artifact_revision, artifact_digest,
       state, workflow_namespace, workflow_name, workflow_uid,
       generation_bucket, generation_key, error_detail,
       received_at, submitted_at, started_at, finished_at
FROM codegraph_builds ORDER BY received_at DESC LIMIT 20;
'
```

Match the exact source/digest, then retain its `id` (`build_id`) and `workflow_name` to correlate logs, Argo, and MinIO. No row means no accepted event has been durably recorded. `received` without workflow implies preflight/submission has not completed; `submitted` or `running` implies Argo should have an object. Terminal `failed` has `error_detail`; `superseded` means preflight saw a different current Flux revision/digest.

### 3. Argo Workflow and worker logs

```bash
kubectl -n ms get workflows.argoproj.io -l app=codegraph-build -o wide
kubectl -n ms get workflow WORKFLOW_NAME -o yaml
kubectl -n ms logs -l workflows.argoproj.io/workflow=WORKFLOW_NAME --all-containers=true --timestamps --prefix=true
```

Replace `WORKFLOW_NAME` using the PostgreSQL row. Inspect `status.phase`, `status.message`, the worker Pod/container exit status, and the CodeGraph stage lines. A `Succeeded` Workflow is not by itself proof that the controller accepted the generation result: the PostgreSQL row must be `succeeded` and contain the matching generation digest.

### 4. Published generation identity

For a successful row, read `generation_bucket`, `generation_key`, `generation_digest`, and `result`. The bundle is at `s3://BUCKET/KEY`, and its worker result is at `s3://BUCKET/KEY.result.json`.

To inspect the object metadata without downloading or changing it, use the controller's configured MinIO client:

```bash
kubectl -n ms exec deployment/codegraph-controller -- python -c '
from memory_steward.codegraph_controller import _minio_client
import sys
item = _minio_client().stat_object(sys.argv[1], sys.argv[2])
print("size=", item.size, "etag=", item.etag, "metadata=", item.metadata)
' BUCKET KEY
```

The result's `source_ref`, `source_revision`, `source_digest`, `codegraph_version`, `index_profile`, and `generation_digest` must refer to the same build and source artifact. An S3 ETag is not a substitute for the generation's recorded SHA-256 digest.

## Metrics and OCO logs

`codegraph-controller:8093/metrics` exposes:

| Series | Interpretation |
| --- | --- |
| `memory_steward_codegraph_builds{state}` | Durable PostgreSQL row counts in each lifecycle state (all time) |
| `memory_steward_codegraph_events_total{outcome}` | Process-local Flux ingress accepted/duplicate/ignored/invalid/unauthorized counters |
| `memory_steward_codegraph_workflow_operations_total{operation,outcome}` | Process-local controller transitions, failures and observation errors |
| `memory_steward_codegraph_worker_duration_seconds` | Successful worker durations observed by the controller, including fetch/index/publish |
| `memory_steward_codegraph_last_received_timestamp_seconds` | Latest durable received time, `0` if none |
| `memory_steward_codegraph_last_succeeded_timestamp_seconds` | Latest durable successful completion time, `0` if none |
| `memory_steward_codegraph_oldest_active_age_seconds` | Age of the oldest uncompleted build, `0` if none |

The time/count gauges are queried from PostgreSQL during each `/metrics` scrape. If PostgreSQL is unavailable, the scrape fails and `up` should reflect that; `/healthz` may still return 200. Counters and histogram samples reset on controller process restart; they are not durable totals. No build UUID, revision, digest, query text, or S3 key is used as a metric label.

Namespace-local Alloy scrapes this endpoint and ships the metrics to the existing OCO VictoriaMetrics datasource (`victoriametrics`), while collecting controller and Argo worker Pod logs through Kubernetes log collection to OCO VictoriaLogs (`victorialogs`). The provisioned Grafana dashboard is **Memory Steward / CodeGraph Builds**, UID `ms-codegraph`. The controller's service log label is `controller` (the Deployment's container name); Argo worker logs can be found by their `codegraph_stage=` marker in namespace `ms`, regardless of the executor's container name.

Read the exported metrics directly from inside the controller Pod:

```bash
kubectl -n ms exec deployment/codegraph-controller -- python -c '
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:8093/metrics", timeout=10).read().decode())
'
```

In Grafana Explore, select VictoriaMetrics and query `up{service="codegraph-controller",project="memory-steward"}` plus `memory_steward_codegraph_builds`. Select VictoriaLogs and filter `namespace:="ms" service:="controller"` for controller activity or `namespace:="ms" "codegraph_stage="` for worker stage output. Dashboard availability or scrape success alone does **not** prove the full build path succeeded.

## End-to-end success criteria

For one **already occurring** `NewArtifact` event, all of these must agree:

1. The Flux source has the expected artifact `revision` and `digest`.
2. The controller logs `codegraph_event=accepted` with the corresponding `build_id`, and PostgreSQL has the matching row.
3. The row links to an Argo Workflow, which reaches phase `Succeeded`; the worker logs reach `codegraph_stage=result_published`.
4. The row reaches `succeeded` and the result identity matches the exact Flux source revision/digest and intended CodeGraph version/profile.
5. The MinIO generation bundle and `.result.json` exist at the recorded coordinates.
6. OCO can query the CodeGraph metric series and the controller/worker log lines, with the same build identity in logs and PostgreSQL.

If a step is absent, the first missing transition is the diagnostic boundary. Do not report an end-to-end PASS from unit tests, `/healthz`, an Argo `Succeeded` phase alone, or Grafana panels alone. This document does not inject a synthetic event, trigger a Flux reconciliation, or mutate production state.
