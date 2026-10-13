"""Publish a serving Pod and Service for each immutable, completed Flux generation."""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

from kubernetes import client, config

log = logging.getLogger("memory-steward.codegraph-publisher")


def service_name(build_id: str) -> str:
    return "cg-serve-" + build_id.replace("-", "")


def alias_name(repository: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", repository.lower()).strip("-")[:32] or "repo"
    digest = hashlib.sha256(repository.encode()).hexdigest()[:12]
    return f"cg-latest-{slug}-{digest}"


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

    def ensure(self, build: Any) -> str | None:
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
        deployed = self.apps.read_namespaced_deployment(name, self.namespace)
        if not deployed.status or not deployed.status.ready_replicas:
            return None

        repository = str(build["repository"])
        alias = alias_name(repository)
        alias_service = {
            "apiVersion": "v1", "kind": "Service",
            "metadata": {"name": alias, "namespace": self.namespace,
                         "labels": {"app": "codegraph-latest"}},
            "spec": {"selector": labels,
                     "ports": [{"name": "http", "port": 8094, "targetPort": 8094}]},
        }
        try:
            existing = self.core.read_namespaced_service(alias, self.namespace)
        except client.exceptions.ApiException as exc:
            if exc.status != 404:
                raise
            self._create(self.core.create_namespaced_service, alias_service, self.namespace)
            log.info("codegraph_event=alias_created repository=%s build_id=%s",
                     repository, build["build_id"])
        else:
            if existing.spec.selector != labels:
                self.core.patch_namespaced_service(
                    alias, self.namespace, {"spec": {"selector": labels}}
                )
                log.info("codegraph_event=alias_switched repository=%s build_id=%s",
                         repository, build["build_id"])
        return f"http://{alias}.{self.namespace}.svc.cluster.local:8094"

    def prune(self, build: Any) -> None:
        # Keep the active generation Service for exact-revision compatibility.
        if not hasattr(self, "_pruned"):
            self._pruned: set[str] = set()
        for old_id in build["previous_build_ids"]:
            if old_id in self._pruned:
                continue
            old_name = service_name(old_id)
            try:
                self.core.delete_namespaced_service(old_name, self.namespace)
            except client.exceptions.ApiException as exc:
                if exc.status != 404:
                    raise
            try:
                self.apps.delete_namespaced_deployment(old_name, self.namespace)
            except client.exceptions.ApiException as exc:
                if exc.status != 404:
                    raise
            self._pruned.add(old_id)
