from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkflowRef:
    namespace: str
    name: str
    uid: str | None


class ArgoWorkflowClient:
    GROUP = "argoproj.io"
    VERSION = "v1alpha1"
    PLURAL = "workflows"

    def __init__(self, *, namespace: str, workflow_template: str, api: Any | None = None):
        if api is None:
            try:
                from kubernetes import client, config
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("kubernetes Python package is not installed") from exc
            config.load_incluster_config()
            api = client.CustomObjectsApi()
        self._api = api
        self.namespace = namespace
        self.workflow_template = workflow_template

    @staticmethod
    def workflow_name(build_id: str) -> str:
        return f"cg-build-{build_id.replace('-', '')}"

    def submit(
        self,
        *,
        build_id: str,
        source_ref: str,
        source_url: str,
        source_revision: str,
        source_digest: str,
        generation_bucket: str,
        generation_key: str,
        worker_image: str,
        codegraph_version: str,
        index_profile: str,
    ) -> WorkflowRef:
        name = self.workflow_name(build_id)
        body = {
            "apiVersion": f"{self.GROUP}/{self.VERSION}",
            "kind": "Workflow",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "app": "codegraph-build",
                    "memory-steward.build-id": build_id,
                },
            },
            "spec": {
                "workflowTemplateRef": {"name": self.workflow_template},
                "arguments": {
                    "parameters": [
                        {"name": "build-id", "value": build_id},
                        {"name": "source-ref", "value": source_ref},
                        {"name": "source-url", "value": source_url},
                        {"name": "source-revision", "value": source_revision},
                        {"name": "source-digest", "value": source_digest},
                        {"name": "generation-bucket", "value": generation_bucket},
                        {"name": "generation-key", "value": generation_key},
                        {"name": "worker-image", "value": worker_image},
                        {"name": "codegraph-version", "value": codegraph_version},
                        {"name": "index-profile", "value": index_profile},
                    ]
                },
            },
        }
        try:
            obj = self._api.create_namespaced_custom_object(
                group=self.GROUP,
                version=self.VERSION,
                namespace=self.namespace,
                plural=self.PLURAL,
                body=body,
            )
        except Exception as exc:
            status = getattr(exc, "status", None)
            if status != 409:
                raise
            obj = self.get(name)

        metadata = obj.get("metadata", {}) if isinstance(obj, dict) else {}
        return WorkflowRef(
            namespace=self.namespace,
            name=name,
            uid=(str(metadata["uid"]) if metadata.get("uid") else None),
        )

    def get(self, name: str) -> dict[str, Any]:
        obj = self._api.get_namespaced_custom_object(
            group=self.GROUP,
            version=self.VERSION,
            namespace=self.namespace,
            plural=self.PLURAL,
            name=name,
        )
        if not isinstance(obj, dict):
            raise RuntimeError(f"Argo Workflow {self.namespace}/{name} returned invalid object")
        return obj
