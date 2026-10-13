"""Publish a serving Pod and Service for each immutable, completed Flux generation."""
from __future__ import annotations

import logging
from typing import Any

from kubernetes import client, config

log = logging.getLogger("memory-steward.codegraph-publisher")


def service_name(build_id: str) -> str:
    return "cg-serve-" + build_id.replace("-", "")


class CodeGraphPublisher:
    def __init__(self, *, namespace: str, image: str):
        config.load_incluster_config()
        self.apps = client.AppsV1Api()
        self.core = client.CoreV1Api()
        self.namespace = namespace
        self.image = image

    @staticmethod
    def _create(create: Any, body: dict[str, Any], namespace: str) -> None:
        try:
            create(namespace=namespace, body=body)
        except client.exceptions.ApiException as exc:
            if exc.status != 409:
                raise

    def ensure(self, build: Any) -> None:
        name = service_name(build["build_id"])
        if not build["generation_bucket"] or not build["generation_key"]:
            raise RuntimeError(f"CodeGraph build {build['build_id']} has no generation")
        result = build["result"]
        if not isinstance(result, dict):
            raise RuntimeError(f"CodeGraph build {build['build_id']} has no published result")
        labels = {"app": "codegraph-serve", "codegraph-build-id": build["build_id"]}
        service = {
            "apiVersion": "v1", "kind": "Service",
            "metadata": {"name": name, "namespace": self.namespace, "labels": labels},
            "spec": {"selector": labels, "ports": [{"name": "http", "port": 8094, "targetPort": 8094}]},
        }
        env = [{"name": env_name, "value": str(result[field])} for env_name, field in (
            ("CODEGRAPH_GENERATION_DIGEST", "generation_digest"),
            ("CODEGRAPH_SOURCE_REF", "source_ref"),
            ("CODEGRAPH_SOURCE_REVISION", "source_revision"),
            ("CODEGRAPH_SOURCE_DIGEST", "source_digest"),
            ("CODEGRAPH_VERSION", "codegraph_version"),
            ("CODEGRAPH_INDEX_PROFILE", "index_profile"),
        )]
        env += [
            {"name": "CODEGRAPH_GENERATION_BUCKET", "value": build["generation_bucket"]},
            {"name": "CODEGRAPH_GENERATION_KEY", "value": build["generation_key"]},
        ]
        deployment = {
            "apiVersion": "apps/v1", "kind": "Deployment",
            "metadata": {"name": name, "namespace": self.namespace, "labels": labels},
            "spec": {
                "replicas": 1, "selector": {"matchLabels": labels},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "containers": [{
                            "name": "serve", "image": self.image, "imagePullPolicy": "Always",
                            "command": ["python", "-m", "memory_steward.codegraph_generation_serve"],
                            "ports": [{"containerPort": 8094}],
                            "envFrom": [
                                {"configMapRef": {"name": "homel-runtime-contract"}},
                                {"secretRef": {"name": "homel-codegraph", "optional": True}},
                            ],
                            "env": env,
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/workspace"},
                                {"name": "state", "mountPath": "/state"},
                            ],
                            "readinessProbe": {"httpGet": {"path": "/healthz", "port": 8094},
                                               "periodSeconds": 5},
                        }],
                        "volumes": [{"name": "workspace", "emptyDir": {}}, {"name": "state", "emptyDir": {}}],
                    },
                },
            },
        }
        self._create(self.core.create_namespaced_service, service, self.namespace)
        self._create(self.apps.create_namespaced_deployment, deployment, self.namespace)
        log.info("codegraph_event=serving_ensured build_id=%s service=%s", build["build_id"], name)
