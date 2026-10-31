# MEMORY STEWARD BACKUP VIA ARGO
## PostgreSQL and Qdrant backup, then MinIO export
### Engineering Proposal
*Namespace: ms • Owner: memory-steward*

---

## Navigation
- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. Execution](#1-execution)
- [2. Configuration](#2-configuration)
- [3. Limits](#3-limits)
- [4. Closing Statement](#4-closing-statement)

## 0. Status, Scope, and Authority
**Status:** PARTIAL
**Audience:** Operators
**Change policy:** Update alongside workflow changes.

The CronWorkflow replaces the prior Kubernetes CronJob; it does not change `scripts/backup.sh`.

[Back to top](#navigation)

## 1. Execution
At 03:00 UTC, Argo runs the existing PostgreSQL/Qdrant backup on the `backups` PVC, then exports `/backups` to a per-Workflow prefix in MinIO. The export runs only after successful backup. The `_BACKUP_COMPLETE` marker is written after `rclone check` succeeds.

[Back to top](#navigation)

## 2. Configuration
Create Kubernetes Secret `memory-steward-backup-minio` in namespace `ms` with keys `access-key`, `secret-key`, and `bucket`. The bucket must already exist. The account needs object read/write/list permissions in that bucket. The existing `memory-tooling` ServiceAccount is used.

[Back to top](#navigation)

## 3. Limits
The workflow exports all currently retained files in `/backups`, not an application-consistent snapshot of the entire PVC. Concurrent manual writes are not controlled. Host Runtime's independent 03:15 MinIO-to-S3 CronWorkflow is not gated on this export. Therefore off-host completion is **not** guaranteed by this change. The existing `backup.sh` retains its current local retention and database credential behavior. Restore and AWS provisioning are not implemented here.

[Back to top](#navigation)

## 4. Closing Statement
The Memory Steward-owned workflow performs the agreed PVC-to-MinIO export. End-to-end disaster recovery remains separate work.

[Back to top](#navigation)

---
**END OF DOCUMENT**
