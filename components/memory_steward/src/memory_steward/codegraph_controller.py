from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, Header, HTTPException
from psycopg import sql

from memory_steward.codegraph_registry import (
    DEFAULT_NOTIFY_CHANNEL,
    CodeGraphRegistry,
    IndexSuccess,
    IndexWork,
    ServeWork,
    postgres_dsn_from_env,
)

log = logging.getLogger("memory-steward.codegraph-controller")


class KubernetesIndexJobLauncher:
    def __init__(
        self,
        *,
        namespace: str,
        worker_image: str,
        controller_url: str,
        worker_secret_name: str,
        codegraph_version: str,
        index_profile: str,
        job_ttl_seconds: int = 600,
    ):
        try:
            from kubernetes import client, config
        except ImportError as exc:  # pragma: no cover - dependency is present in runtime image
            raise RuntimeError("kubernetes Python package is not installed") from exc

        config.load_incluster_config()
        self._client = client
        self._api = client.BatchV1Api()
        self.namespace = namespace
        self.worker_image = worker_image
        self.controller_url = controller_url
        self.worker_secret_name = worker_secret_name
        self.codegraph_version = codegraph_version
        self.index_profile = index_profile
        self.job_ttl_seconds = job_ttl_seconds

    @staticmethod
    def _env(name: str, value: str | None):
        from kubernetes import client

        return client.V1EnvVar(name=name, value=value or "")

    def launch(self, work: IndexWork) -> None:
        client = self._client
        env = [
            self._env("CODEGRAPH_WORKER_MODE", "index"),
            self._env("CODEGRAPH_REGISTRY_ID", work.registry_id),
            self._env("CODEGRAPH_WORKER_GENERATION", str(work.worker_generation)),
            self._env("CODEGRAPH_SOURCE_BUCKET", work.source_bucket),
            self._env("CODEGRAPH_SOURCE_OBJECT_KEY", work.source_object_key),
            self._env("CODEGRAPH_SOURCE_VERSION_ID", work.source_version_id),
            self._env("CODEGRAPH_PROJECT_ID", work.project_id),
            self._env("CODEGRAPH_RUN_ID", work.run_id),
            self._env("CODEGRAPH_REALM", work.realm),
            self._env("CODEGRAPH_REPOSITORY", work.repository),
            self._env("CODEGRAPH_VERSION", self.codegraph_version),
            self._env("CODEGRAPH_INDEX_PROFILE", self.index_profile),
            self._env("CODEGRAPH_CONTROLLER_URL", self.controller_url),
            self._env("CODEGRAPH_WORK_ROOT", "/workspace"),
            self._env("CODEGRAPH_HOME", "/state/home"),
        ]
        if work.base is not None:
            env.extend(
                [
                    self._env("CODEGRAPH_BASE_ARTIFACT_BUCKET", work.base.artifact_bucket),
                    self._env("CODEGRAPH_BASE_ARTIFACT_KEY", work.base.artifact_key),
                    self._env("CODEGRAPH_BASE_ARTIFACT_DIGEST", work.base.artifact_digest),
                    self._env("CODEGRAPH_BASE_REVISION", work.base.revision),
                ]
            )

        container = client.V1Container(
            name="index",
            image=self.worker_image,
            image_pull_policy="Always",
            command=["python", "-m", "memory_steward.codegraph_worker"],
            env=env,
            env_from=[
                client.V1EnvFromSource(
                    secret_ref=client.V1SecretEnvSource(name=self.worker_secret_name, optional=True)
                )
            ],
            volume_mounts=[
                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                client.V1VolumeMount(name="state", mount_path="/state"),
            ],
        )
        pod_spec = client.V1PodSpec(
            restart_policy="Never",
            service_account_name="codegraph-worker",
            containers=[container],
            volumes=[
                client.V1Volume(name="workspace", empty_dir=client.V1EmptyDirVolumeSource()),
                client.V1Volume(name="state", empty_dir=client.V1EmptyDirVolumeSource()),
            ],
        )
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app": "codegraph-worker",
                    "codegraph.registry-id": work.registry_id,
                    "codegraph.worker-generation": str(work.worker_generation),
                }
            ),
            spec=pod_spec,
        )
        job = client.V1Job(
            metadata=client.V1ObjectMeta(name=work.worker_id, namespace=self.namespace),
            spec=client.V1JobSpec(
                backoff_limit=0,
                ttl_seconds_after_finished=self.job_ttl_seconds,
                template=template,
            ),
        )
        self._api.create_namespaced_job(namespace=self.namespace, body=job)


class KubernetesServePodLauncher:
    def __init__(
        self,
        *,
        namespace: str,
        worker_image: str,
        controller_url: str,
        worker_secret_name: str,
    ):
        try:
            from kubernetes import client, config
        except ImportError as exc:  # pragma: no cover - dependency is present in runtime image
            raise RuntimeError("kubernetes Python package is not installed") from exc

        config.load_incluster_config()
        self._client = client
        self._api = client.CoreV1Api()
        self.namespace = namespace
        self.worker_image = worker_image
        self.controller_url = controller_url
        self.worker_secret_name = worker_secret_name

    @staticmethod
    def _env(name: str, value: str | None):
        from kubernetes import client

        return client.V1EnvVar(name=name, value=value or "")

    def launch(self, work: ServeWork) -> None:
        client = self._client
        labels = {
            "app": "codegraph-serve",
            "codegraph.worker-id": work.worker_id,
            "codegraph.registry-id": work.registry_id,
        }
        env = [
            self._env("CODEGRAPH_REGISTRY_ID", work.registry_id),
            self._env("CODEGRAPH_WORKER_GENERATION", str(work.worker_generation)),
            self._env("CODEGRAPH_WORKER_ENDPOINT", work.worker_endpoint),
            self._env("CODEGRAPH_SOURCE_BUCKET", work.source_bucket),
            self._env("CODEGRAPH_SOURCE_OBJECT_KEY", work.source_object_key),
            self._env("CODEGRAPH_SOURCE_VERSION_ID", work.source_version_id),
            self._env("CODEGRAPH_PROJECT_ID", work.project_id),
            self._env("CODEGRAPH_RUN_ID", work.run_id),
            self._env("CODEGRAPH_REALM", work.realm),
            self._env("CODEGRAPH_REPOSITORY", work.repository),
            self._env("CODEGRAPH_INDEXED_REVISION", work.indexed_revision),
            self._env("CODEGRAPH_VERSION", work.codegraph_version),
            self._env("CODEGRAPH_INDEX_PROFILE", work.index_profile),
            self._env("CODEGRAPH_STATE_ARTIFACT_BUCKET", work.state_artifact_bucket),
            self._env("CODEGRAPH_STATE_ARTIFACT_KEY", work.state_artifact_key),
            self._env("CODEGRAPH_STATE_ARTIFACT_DIGEST", work.state_artifact_digest),
            self._env("CODEGRAPH_CONTROLLER_URL", self.controller_url),
            self._env("CODEGRAPH_WORK_ROOT", "/workspace"),
            self._env("CODEGRAPH_HOME", "/state/home"),
            self._env("CODEGRAPH_SERVE_PORT", "8094"),
        ]
        container = client.V1Container(
            name="serve",
            image=self.worker_image,
            image_pull_policy="Always",
            command=["python", "-m", "memory_steward.codegraph_serve"],
            env=env,
            env_from=[
                client.V1EnvFromSource(
                    secret_ref=client.V1SecretEnvSource(name=self.worker_secret_name, optional=True)
                )
            ],
            ports=[client.V1ContainerPort(container_port=8094)],
            volume_mounts=[
                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                client.V1VolumeMount(name="state", mount_path="/state"),
            ],
            readiness_probe=client.V1Probe(
                http_get=client.V1HTTPGetAction(path="/healthz", port=8094),
                initial_delay_seconds=2,
                period_seconds=5,
            ),
        )
        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(name=work.worker_id, labels=labels),
            spec=client.V1PodSpec(
                restart_policy="Never",
                service_account_name="codegraph-worker",
                containers=[container],
                volumes=[
                    client.V1Volume(name="workspace", empty_dir=client.V1EmptyDirVolumeSource()),
                    client.V1Volume(name="state", empty_dir=client.V1EmptyDirVolumeSource()),
                ],
            ),
        )
        service = client.V1Service(
            metadata=client.V1ObjectMeta(name=work.worker_id, labels=labels),
            spec=client.V1ServiceSpec(
                selector={"codegraph.worker-id": work.worker_id},
                ports=[client.V1ServicePort(port=8094, target_port=8094)],
            ),
        )
        self._api.create_namespaced_service(namespace=self.namespace, body=service)
        try:
            self._api.create_namespaced_pod(namespace=self.namespace, body=pod)
        except Exception:
            self._api.delete_namespaced_service(name=work.worker_id, namespace=self.namespace)
            raise


class CodeGraphController:
    def __init__(
        self,
        registry: CodeGraphRegistry,
        *,
        launcher: Any | None = None,
        serve_launcher: Any | None = None,
        namespace: str = "ms",
        batch_size: int = 16,
        idle_poll_seconds: float = 5.0,
        codegraph_version: str = "0.20.1",
        index_profile: str = "graph-only",
    ):
        self.registry = registry
        self.launcher = launcher
        self.serve_launcher = serve_launcher
        self.namespace = namespace
        self.batch_size = batch_size
        self.idle_poll_seconds = idle_poll_seconds
        self.codegraph_version = codegraph_version
        self.index_profile = index_profile

    def drain_once(self) -> int:
        discovered = self.registry.claim_discovered(limit=self.batch_size)
        for work in discovered:
            log.info(
                "codegraph work queued registry_id=%s bucket=%s key=%s run_id=%s realm=%s",
                work.registry_id,
                work.source_bucket,
                work.source_object_key,
                work.run_id,
                work.realm,
            )

        if self.launcher is None:
            return len(discovered)

        reserved = self.registry.reserve_queued_index_work(
            limit=self.batch_size,
            codegraph_version=self.codegraph_version,
            index_profile=self.index_profile,
        )
        for work in reserved:
            try:
                self.launcher.launch(work)
                log.info(
                    "codegraph index worker launched registry_id=%s generation=%s worker=%s base_revision=%s",
                    work.registry_id,
                    work.worker_generation,
                    work.worker_id,
                    work.base.revision if work.base else None,
                )
            except Exception as exc:
                log.exception("failed to launch CodeGraph index worker registry_id=%s", work.registry_id)
                self.registry.mark_index_launch_failed(work, str(exc))
        return len(discovered) + len(reserved)

    def drain_serve_once(self) -> int:
        if self.serve_launcher is None:
            return 0

        serving = self.registry.reserve_activating_serve_work(
            limit=self.batch_size,
            namespace=self.namespace,
        )
        for work in serving:
            try:
                self.serve_launcher.launch(work)
                log.info(
                    "codegraph serve worker launched registry_id=%s generation=%s worker=%s endpoint=%s",
                    work.registry_id,
                    work.worker_generation,
                    work.worker_id,
                    work.worker_endpoint,
                )
            except Exception as exc:
                log.exception("failed to launch CodeGraph serve worker registry_id=%s", work.registry_id)
                self.registry.mark_serve_launch_failed(work, str(exc))
        return len(serving)

    def run_serve_forever(self) -> None:
        while True:
            try:
                self.drain_serve_once()
            except Exception:
                log.exception("codegraph serve controller scan failed")
            time.sleep(self.idle_poll_seconds)

    def run_forever(self) -> None:
        self.drain_once()
        while True:
            try:
                with self.registry.notification_connection() as conn:
                    conn.execute(
                        sql.SQL("LISTEN {}").format(sql.Identifier(self.registry.notify_channel))
                    )
                    log.info("listening for codegraph registry work channel=%s", self.registry.notify_channel)
                    while True:
                        for _notify in conn.notifies(
                            timeout=self.idle_poll_seconds,
                            stop_after=1,
                        ):
                            break
                        self.drain_once()
            except Exception:
                log.exception("codegraph controller listener failed; reconnecting")
                time.sleep(min(self.idle_poll_seconds, 5.0))


def create_app(
    controller: CodeGraphController,
    *,
    callback_token: str | None = None,
    proxy_token: str | None = None,
) -> FastAPI:
    app = FastAPI(title="memory-steward-codegraph-controller", version="0.1")

    def probe_serve_endpoint(endpoint: str) -> None:
        health = requests.get(f"{endpoint.rstrip('/')}/healthz", timeout=5)
        health.raise_for_status()
        headers: dict[str, str] = {}
        if proxy_token:
            headers["Authorization"] = f"Bearer {proxy_token}"
        tools = requests.get(
            f"{endpoint.rstrip('/')}/v1/tools",
            headers=headers,
            timeout=10,
        )
        tools.raise_for_status()
        payload = tools.json()
        if not isinstance(payload.get("tools"), list) or not payload["tools"]:
            raise RuntimeError("CodeGraph serve worker returned no tools")

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/v1/codegraph/index-result")
    def index_result(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if callback_token and authorization != f"Bearer {callback_token}":
            raise HTTPException(status_code=401, detail="invalid worker callback token")

        try:
            registry_id = str(payload["registry_id"])
            generation = int(payload["worker_generation"])
            ok = bool(payload["ok"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="invalid CodeGraph worker result") from exc

        if ok:
            required = (
                "indexed_revision",
                "codegraph_version",
                "index_profile",
                "index_mode",
                "state_artifact_bucket",
                "state_artifact_key",
                "state_artifact_digest",
                "state_artifact_schema_version",
            )
            if any(payload.get(name) in (None, "") for name in required):
                raise HTTPException(status_code=400, detail="incomplete successful CodeGraph worker result")
            updated = controller.registry.complete_index_success(
                IndexSuccess(
                    registry_id=registry_id,
                    worker_generation=generation,
                    indexed_revision=str(payload["indexed_revision"]),
                    codegraph_version=str(payload["codegraph_version"]),
                    index_profile=str(payload["index_profile"]),
                    index_mode=str(payload["index_mode"]),
                    base_revision=(str(payload["base_revision"]) if payload.get("base_revision") else None),
                    state_artifact_bucket=str(payload["state_artifact_bucket"]),
                    state_artifact_key=str(payload["state_artifact_key"]),
                    state_artifact_digest=str(payload["state_artifact_digest"]),
                    state_artifact_schema_version=int(payload["state_artifact_schema_version"]),
                    duration_ms=(int(payload["duration_ms"]) if payload.get("duration_ms") is not None else None),
                )
            )
        else:
            updated = controller.registry.complete_index_failure(
                registry_id=registry_id,
                worker_generation=generation,
                failure_state=str(payload.get("failure_state") or "failed"),
                error_detail=str(payload.get("error_detail") or "CodeGraph index worker failed"),
            )

        if not updated:
            raise HTTPException(status_code=409, detail="stale CodeGraph worker result")
        return {"updated": True}

    @app.post("/v1/codegraph/serve-result")
    def serve_result(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if callback_token and authorization != f"Bearer {callback_token}":
            raise HTTPException(status_code=401, detail="invalid worker callback token")
        try:
            registry_id = str(payload["registry_id"])
            generation = int(payload["worker_generation"])
            endpoint = str(payload["worker_endpoint"])
            ok = bool(payload["ok"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="invalid CodeGraph serve result") from exc

        expected_worker_id = f"cg-serve-{registry_id.replace('-', '')[:12]}-g{generation}"
        expected_endpoint = f"http://{expected_worker_id}.{controller.namespace}.svc.cluster.local:8094"
        if endpoint != expected_endpoint:
            raise HTTPException(status_code=409, detail="unexpected CodeGraph serve worker endpoint")

        if ok:
            indexed_revision = str(payload.get("indexed_revision") or "")
            if len(indexed_revision) != 40:
                raise HTTPException(status_code=400, detail="missing indexed revision")
            try:
                probe_serve_endpoint(endpoint)
            except Exception as exc:
                raise HTTPException(status_code=503, detail=f"CodeGraph serve probe failed: {exc}") from exc
            updated = controller.registry.complete_serve_success(
                registry_id=registry_id,
                worker_generation=generation,
                indexed_revision=indexed_revision,
                worker_endpoint=endpoint,
            )
        else:
            updated = controller.registry.complete_serve_failure(
                registry_id=registry_id,
                worker_generation=generation,
                worker_endpoint=endpoint,
                error_detail=str(payload.get("error_detail") or "CodeGraph serve worker failed"),
            )
        if not updated:
            raise HTTPException(status_code=409, detail="stale CodeGraph serve worker result")
        return {"updated": True}

    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    notify_channel = os.environ.get("CODEGRAPH_NOTIFY_CHANNEL", DEFAULT_NOTIFY_CHANNEL)
    registry = CodeGraphRegistry(
        postgres_dsn_from_env("memory-steward-codegraph-controller"),
        notify_channel=notify_channel,
    )
    codegraph_version = os.environ.get("CODEGRAPH_VERSION", "0.20.1")
    index_profile = os.environ.get("CODEGRAPH_INDEX_PROFILE", "graph-only")
    namespace = os.environ.get("POD_NAMESPACE", "ms")
    launcher = KubernetesIndexJobLauncher(
        namespace=namespace,
        worker_image=os.environ.get(
            "CODEGRAPH_WORKER_IMAGE",
            "ghcr.io/homel-dev/memory-steward/memory-steward:latest",
        ),
        controller_url=os.environ.get(
            "CODEGRAPH_CONTROLLER_URL",
            "http://codegraph-controller:8093",
        ),
        worker_secret_name=os.environ.get("CODEGRAPH_WORKER_SECRET_NAME", "homel-codegraph"),
        codegraph_version=codegraph_version,
        index_profile=index_profile,
        job_ttl_seconds=int(os.environ.get("CODEGRAPH_WORKER_JOB_TTL_SECONDS", "600")),
    )
    serve_launcher = KubernetesServePodLauncher(
        namespace=namespace,
        worker_image=os.environ.get(
            "CODEGRAPH_WORKER_IMAGE",
            "ghcr.io/homel-dev/memory-steward/memory-steward:latest",
        ),
        controller_url=os.environ.get(
            "CODEGRAPH_CONTROLLER_URL",
            "http://codegraph-controller:8093",
        ),
        worker_secret_name=os.environ.get("CODEGRAPH_WORKER_SECRET_NAME", "homel-codegraph"),
    )
    controller = CodeGraphController(
        registry,
        launcher=launcher,
        serve_launcher=serve_launcher,
        namespace=namespace,
        batch_size=int(os.environ.get("CODEGRAPH_CONTROLLER_BATCH_SIZE", "16")),
        idle_poll_seconds=float(os.environ.get("CODEGRAPH_CONTROLLER_POLL_SECONDS", "5")),
        codegraph_version=codegraph_version,
        index_profile=index_profile,
    )
    thread = threading.Thread(target=controller.run_forever, name="codegraph-controller-loop", daemon=True)
    thread.start()
    serve_thread = threading.Thread(
        target=controller.run_serve_forever,
        name="codegraph-serve-controller-loop",
        daemon=True,
    )
    serve_thread.start()

    app = create_app(
        controller,
        callback_token=os.environ.get("CODEGRAPH_WORKER_CALLBACK_TOKEN") or None,
        proxy_token=os.environ.get("CODEGRAPH_WORKER_PROXY_TOKEN") or None,
    )
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("CODEGRAPH_CONTROLLER_PORT", "8093")),
    )


if __name__ == "__main__":
    main()
