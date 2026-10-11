from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from memory_steward.codegraph_builds import FluxArtifactEvent

REVISION_METADATA_KEY = "source.toolkit.fluxcd.io/revision"
DIGEST_METADATA_KEY = "source.toolkit.fluxcd.io/digest"


@dataclass(frozen=True)
class FluxArtifactStatus:
    url: str
    revision: str
    digest: str


def parse_flux_new_artifact(
    payload: dict[str, Any],
    *,
    artifact_lookup: Callable[[str, str], FluxArtifactStatus] | None = None,
) -> FluxArtifactEvent | None:
    if payload.get("reason") != "NewArtifact":
        return None

    involved = payload.get("involvedObject")
    metadata = payload.get("metadata") or {}
    if not isinstance(involved, dict) or not isinstance(metadata, dict):
        raise ValueError("Flux event must contain involvedObject and valid metadata")

    api_version = involved.get("apiVersion")
    kind = involved.get("kind")
    namespace = involved.get("namespace")
    name = involved.get("name")
    uid = involved.get("uid")
    revision = metadata.get(REVISION_METADATA_KEY)
    digest = metadata.get(DIGEST_METADATA_KEY)

    if api_version != "source.toolkit.fluxcd.io/v1" or kind != "GitRepository":
        return None
    if not isinstance(namespace, str) or not namespace:
        raise ValueError("Flux GitRepository event is missing namespace")
    if not isinstance(name, str) or not name:
        raise ValueError("Flux GitRepository event is missing name")
    if uid is not None and not isinstance(uid, str):
        raise ValueError("Flux GitRepository event has invalid uid")
    # Flux notification-controller generic Provider payloads may omit source
    # artifact metadata. Read the authoritative GitRepository status instead.
    if (not revision or not digest) and artifact_lookup is not None:
        current = artifact_lookup(namespace, name)
        revision = revision or current.revision
        digest = digest or current.digest
    if not isinstance(revision, str) or not revision:
        raise ValueError("Flux NewArtifact event is missing revision metadata")
    if not isinstance(digest, str) or not digest:
        raise ValueError("Flux NewArtifact event is missing digest metadata")

    return FluxArtifactEvent(
        source_api_version=api_version,
        source_kind=kind,
        source_namespace=namespace,
        source_name=name,
        source_uid=uid,
        artifact_revision=revision,
        artifact_digest=digest,
        payload=payload,
    )


class FluxSourceClient:
    def __init__(self, api: Any | None = None):
        if api is None:
            try:
                from kubernetes import client, config
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("kubernetes Python package is not installed") from exc
            config.load_incluster_config()
            api = client.CustomObjectsApi()
        self._api = api

    def get_artifact(self, event: FluxArtifactEvent) -> FluxArtifactStatus:
        return self.get_artifact_for_source(event.source_namespace, event.source_name)

    def get_artifact_for_source(self, namespace: str, name: str) -> FluxArtifactStatus:
        obj = self._api.get_namespaced_custom_object(
            group="source.toolkit.fluxcd.io",
            version="v1",
            namespace=namespace,
            plural="gitrepositories",
            name=name,
        )
        status = obj.get("status") if isinstance(obj, dict) else None
        artifact = status.get("artifact") if isinstance(status, dict) else None
        if not isinstance(artifact, dict):
            raise RuntimeError("GitRepository has no status.artifact")

        url = artifact.get("url")
        revision = artifact.get("revision")
        digest = artifact.get("digest")
        if not isinstance(url, str) or not url:
            raise RuntimeError("GitRepository status.artifact.url is missing")
        if not isinstance(revision, str) or not revision:
            raise RuntimeError("GitRepository status.artifact.revision is missing")
        if not isinstance(digest, str) or not digest:
            raise RuntimeError("GitRepository status.artifact.digest is missing")
        return FluxArtifactStatus(url=url, revision=revision, digest=digest)
