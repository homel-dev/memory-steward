"""Durable RR workspace snapshot source through Kubernetes Events.

Events are notifications only. The immutable snapshot lives in MinIO; its
SHA-256 is verified by the existing Argo CodeGraph worker before indexing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

from kubernetes import client, config, watch

from memory_steward.codegraph_builds import CodeGraphBuildStore, FluxArtifactEvent

log = logging.getLogger("memory-steward.codegraph-workspace")

WORKSPACE_SOURCE_KIND = "RRWorkspace"
WORKSPACE_EVENT_REASON = "CodeGraphWorkspaceSnapshot"
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_KEY = re.compile(r"^rr/workspaces/[A-Za-z0-9._/-]+\.tar\.gz$")


def workspace_source_name(project_id: str, repository: str) -> str:
    identity = json.dumps([project_id, repository], separators=(",", ":"))
    return "rr-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def parse_workspace_snapshot(message: str, namespace: str, bucket: str) -> FluxArtifactEvent:
    try:
        payload = json.loads(message)
    except (TypeError, ValueError) as exc:
        raise ValueError("workspace event message must contain JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("workspace event must contain a JSON object")
    project = payload.get("project_id")
    repository = payload.get("repository")
    revision = payload.get("revision")
    digest = payload.get("snapshot_digest")
    object_bucket = payload.get("bucket")
    key = payload.get("key")
    if not isinstance(project, str) or not project or len(project) > 256:
        raise ValueError("project_id is missing or invalid")
    if not isinstance(repository, str) or not repository or len(repository) > 512 or any(ord(c) < 32 for c in repository):
        raise ValueError("repository is missing or invalid")
    if not isinstance(revision, str) or not _SHA1.fullmatch(revision):
        raise ValueError("revision must be a lowercase 40-character Git SHA")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise ValueError("snapshot_digest must be sha256:<64 lowercase hex characters>")
    if object_bucket != bucket or not isinstance(key, str) or not _KEY.fullmatch(key) or ".." in key.split("/"):
        raise ValueError("workspace source must be an authorized MinIO bucket and rr/workspaces/ key")
    run_id = payload.get("run_id")
    if run_id is not None and (not isinstance(run_id, str) or not run_id or len(run_id) > 256):
        raise ValueError("run_id is invalid")
    return FluxArtifactEvent(
        source_api_version="rr.homel.dev/v1",
        source_kind=WORKSPACE_SOURCE_KIND,
        source_namespace=namespace,
        source_name=workspace_source_name(project, repository),
        source_uid=None,
        artifact_revision=revision,
        artifact_digest=digest,
        payload={
            "project_id": project, "repository": repository,
            "run_id": run_id, "realm": "workspace",
            "artifact_url": f"s3://{bucket}/{key}",
            "snapshot_digest": digest,
        },
    )


class WorkspaceEventWatcher:
    """Namespace-bound Kubernetes Event consumer; PostgreSQL owns deduplication."""

    def __init__(self, store: CodeGraphBuildStore, *, namespace: str, source_bucket: str):
        config.load_incluster_config()
        self.events = client.CoreV1Api()
        self.store = store
        self.namespace = namespace
        self.source_bucket = source_bucket

    def run_forever(self) -> None:
        # List/watch starts from a resource version to cover the list/watch gap.
        # Already-created objects are safe because the database insert is idempotent.
        while True:
            try:
                initial = self.events.list_namespaced_event(
                    self.namespace, field_selector=f"reason={WORKSPACE_EVENT_REASON}"
                )
                for event in initial.items:
                    self._consume(event)
                stream = watch.Watch()
                for update in stream.stream(
                    self.events.list_namespaced_event,
                    namespace=self.namespace,
                    field_selector=f"reason={WORKSPACE_EVENT_REASON}",
                    resource_version=initial.metadata.resource_version,
                    timeout_seconds=60,
                ):
                    if update.get("type") in {"ADDED", "MODIFIED"}:
                        self._consume(update["object"])
            except Exception:
                log.exception("RR workspace Kubernetes Event watch failed; restarting")
                import time
                time.sleep(5)

    def _consume(self, event: Any) -> None:
        if event.reason != WORKSPACE_EVENT_REASON or event.type != "Normal":
            return
        try:
            record = parse_workspace_snapshot(
                event.message, self.namespace, self.source_bucket
            )
            result = self.store.record_event(record)
            log.info(
                "codegraph_event=workspace_%s build_id=%s project=%s source=%s digest=%s",
                "accepted" if result.inserted else "duplicate",
                result.build_id, record.payload["project_id"], record.source_name,
                record.artifact_digest,
            )
        except ValueError as exc:
            log.warning("codegraph_event=invalid_workspace_snapshot reason=%s", exc)


def workspace_status(store: CodeGraphBuildStore, *, project_id: str, repository: str, snapshot_digest: str) -> dict[str, Any]:
    if not project_id or not repository or not _SHA256.fullmatch(snapshot_digest):
        raise ValueError("project_id, repository and valid snapshot_digest are required")
    name = workspace_source_name(project_id, repository)
    with store._connect() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT id::text, state, artifact_revision, worker_endpoint, error_detail
               FROM codegraph_builds
               WHERE source_namespace = %s AND source_kind = 'RRWorkspace'
                 AND source_name = %s AND artifact_digest = %s""",
            (os.environ.get("CODEGRAPH_WORKSPACE_EVENT_NAMESPACE", "rr"), name, snapshot_digest),
        )
        row = cur.fetchone()
    if row is None:
        return {"state": "missing", "ready": False}
    build_id, state, revision, endpoint, error = row
    return {
        "build_id": str(build_id), "state": "ready" if state == "succeeded" and endpoint else state,
        "ready": state == "succeeded" and bool(endpoint),
        "revision": revision,
        "worker_endpoint": endpoint if state == "succeeded" else None,
        "error": error if state == "failed" else None,
    }
