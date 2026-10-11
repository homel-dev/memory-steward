# Memory Steward: Flux deployment and recovery runbook

**Rollout order for an existing cluster:** merge the `host-runtime` patch
**first**, and wait until `flux get kustomizations -n flux-system` shows the
`memory-steward` Kustomization using `prune: false` and the new stage objects
exist. Only then merge the Memory Steward patch. Doing this in reverse can
allow the old runtime Kustomization (`prune: true`) to delete StatefulSets when
their manifests move to `k8s/infra`. The new stages can report `path not found`
between the two merges; that is expected and does not stop existing pods.

The cluster's `host-runtime` repo creates four Flux Kustomizations. They use
the same `GitRepository/memory-steward` source and run **in order**:

| Flux Kustomization | Repository path | Completion condition |
|---|---|---|
| `memory-steward-infra` | `./k8s/infra` | Namespace, Secret, Postgres, Qdrant and backups PVC are ready |
| `memory-steward-restore` | `./k8s/restore` | Optional first-install recovery Job succeeds |
| `memory-steward-migrate` | `./k8s/migrate` | `migrate.sh up` and `init_qdrant.sh ensure` Jobs complete |
| `memory-steward` | `./k8s` | Applications, CodeGraph, telemetry and backup CronJob are ready |

No manual SQL is needed. On a fresh Postgres database, migrations create
`schema_migrations` and all application tables, including `codegraph_builds`.
On existing installations, already-recorded migrations are skipped. The tooling
image embeds `sql/migrations/`; CI promotes its digest to *all three*
Kustomization files (runtime, restore and migrate). Updated Job templates carry
the Flux `force` annotation so completed Jobs can be replaced and rerun safely.
The runtime Kustomization has `prune: false` during the ownership transition:
existing Postgres/Qdrant StatefulSets and PVCs must not be garbage-collected.

## Optional recovery from MinIO on a fresh install

Recovery is **opt-in**. If no `homel-backup-restore` Secret or `MINIO_BUCKET`
exists, the restore Job succeeds without touching the stores and the migration
stage initializes a clean deployment. A configured bucket without the manifest
also boots from scratch. Any other remote read, checksum or restore failure
blocks the subsequent migrations and workloads.

For automatic restore, provision Secret `ms/homel-backup-restore` using your
normal secret-management mechanism (not this Git repo), with keys:

- `MINIO_ENDPOINT` (`minio.namespace.svc.cluster.local:9000` or an HTTPS URL)
- `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`
- `MINIO_BUCKET`
- optional `MINIO_SECURE` (`true`/`false`) and `MINIO_MANIFEST_KEY`
  (defaults to `memory-steward/latest.json`)

Place a JSON manifest in that bucket, pointing to a **matching** pair of an
existing `pg_dump -Fc` artifact and a Qdrant collection snapshot:

```json
{
  "postgres": {
    "key": "memory-steward/2026-10-11/homel.dump",
    "sha256": "<64 lowercase hexadecimal characters>"
  },
  "qdrant": {
    "key": "memory-steward/2026-10-11/homel_memory.snapshot",
    "sha256": "<64 lowercase hexadecimal characters>"
  }
}
```

Create the manifest only after both objects have been uploaded; update the
manifest last. The existing nightly backup CronJob saves to the in-cluster
backups PVC; moving an appropriate backup pair to MinIO and publishing its
manifest is a separate backup-retention operation. Do not assume local PVC
backups are automatically in MinIO.

The restore Job checks that Postgres contains **no application tables** and
that the Qdrant collection is absent before restoring either store. It checks
both SHA-256 digests before beginning; it never overwrites a populated DB.
An interrupted restore leaves `/backups/restore-incomplete` on the backups PVC
and blocks future attempts until an operator investigates the partial state.
Do not remove this marker blindly. The runtime will not start until recovery
and migrations have succeeded.

## End-to-end verification

After both Git repos have been merged, check Flux ordering and revisions:

```sh
flux get sources git -n flux-system
flux get kustomizations -n flux-system
kubectl get jobs -n ms memory-bootstrap-restore memory-schema-migrate memory-qdrant-init
kubectl logs -n ms job/memory-bootstrap-restore
kubectl logs -n ms job/memory-schema-migrate
kubectl logs -n ms job/memory-qdrant-init
kubectl get pods -n ms
```

All four Kustomizations should report `Ready=True` with the same current
Memory Steward revision; each Job should be `Complete`. If a Job fails, inspect
its logs and `kubectl describe job -n ms <job>` before retrying. A failed
migration or restore prevents the runtime Kustomization from proceeding.

Check the original CodeGraph failures and the Flux event path:

```sh
kubectl logs -n ms deploy/codegraph-controller --since=30m
kubectl get events -n flux-system --sort-by=.lastTimestamp
kubectl port-forward -n ms svc/codegraph-controller 8093:8093
curl -fsS localhost:8093/metrics | grep -E '^memory_steward_codegraph_'
```

`/metrics` must return HTTP 200 after `codegraph_builds` is created. A Flux
`NewArtifact` webhook may omit revision/digest metadata; the controller now
resolves them from `GitRepository.status.artifact`. A corresponding event must
produce an `accepted` or `duplicate` CodeGraph log entry, not a 400 response.
Do not infer event delivery merely from pods being `Running`: inspect the
event/log counters and verify the matching Argo Workflow if a new build starts.
No alerting is enabled by this deployment.
