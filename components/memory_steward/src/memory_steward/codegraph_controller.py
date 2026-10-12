from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from psycopg import sql

from memory_steward.argo_workflows import ArgoWorkflowClient
from memory_steward.codegraph_builds import BuildRecord, CodeGraphBuildStore, FluxArtifactEvent
from memory_steward.codegraph_metrics import EVENTS, WORKER_DURATION, WORKFLOW_OPERATIONS
from memory_steward.codegraph_metrics import refresh as refresh_metrics
from memory_steward.codegraph_metrics import render as render_metrics
from memory_steward.flux_source import FluxSourceClient, parse_flux_new_artifact

log = logging.getLogger("memory-steward.codegraph-controller")


class _SuppressSuccessfulHealthz(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (
            record.name == "uvicorn.access"
            and isinstance(args, tuple)
            and len(args) == 5
            and args[1] == "GET"
            and args[2] == "/healthz"
            and args[4] == 200
        )


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _minio_client():
    try:
        from minio import Minio
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("minio Python package is not installed") from exc

    raw_endpoint = os.environ.get("MINIO_ENDPOINT") or "minio.host-runtime.svc.cluster.local:9000"
    parsed = urlparse(raw_endpoint if "://" in raw_endpoint else f"//{raw_endpoint}")
    endpoint = parsed.netloc or parsed.path
    secure_default = parsed.scheme == "https"
    return Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        session_token=os.environ.get("MINIO_SESSION_TOKEN") or None,
        secure=_bool_env("MINIO_SECURE", secure_default),
        region=os.environ.get("MINIO_REGION") or None,
    )


class CodeGraphController:
    def __init__(
        self,
        store: CodeGraphBuildStore,
        *,
        flux: FluxSourceClient,
        argo: ArgoWorkflowClient,
        generation_bucket: str,
        worker_image: str,
        batch_size: int = 16,
        idle_poll_seconds: float = 5.0,
        codegraph_version: str = "0.20.1",
        index_profile: str = "graph-only",
        minio_client: Any | None = None,
    ):
        self.store = store
        self.flux = flux
        self.argo = argo
        self.generation_bucket = generation_bucket
        self.worker_image = worker_image
        self.batch_size = batch_size
        self.idle_poll_seconds = idle_poll_seconds
        self.codegraph_version = codegraph_version
        self.index_profile = index_profile
        self._minio = minio_client

    @staticmethod
    def _event_from_build(build: BuildRecord) -> FluxArtifactEvent:
        return FluxArtifactEvent(
            source_api_version=build.source_api_version,
            source_kind=build.source_kind,
            source_namespace=build.source_namespace,
            source_name=build.source_name,
            source_uid=build.source_uid,
            artifact_revision=build.artifact_revision,
            artifact_digest=build.artifact_digest,
            payload={},
        )

    @staticmethod
    def _source_ref(build: BuildRecord) -> str:
        return f"{build.source_api_version}:{build.source_namespace}/{build.source_kind}/{build.source_name}"

    @staticmethod
    def _generation_key(build_id: str) -> str:
        return f"codegraph/builds/{build_id}/generation-v1.tar.gz"

    @staticmethod
    def _result_key(generation_key: str) -> str:
        return f"{generation_key}.result.json"

    def _read_result(self, build: BuildRecord) -> dict[str, Any]:
        if not build.generation_bucket or not build.generation_key:
            raise RuntimeError("completed Workflow has no generation object coordinates")
        if self._minio is None:
            self._minio = _minio_client()
        response = self._minio.get_object(
            build.generation_bucket,
            self._result_key(build.generation_key),
        )
        try:
            payload = json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()
        if not isinstance(payload, dict):
            raise RuntimeError("CodeGraph worker result is not a JSON object")

        required = {
            "build_id",
            "source_ref",
            "source_revision",
            "source_digest",
            "codegraph_version",
            "index_profile",
            "index_mode",
            "generation_bucket",
            "generation_key",
            "generation_digest",
            "generation_schema_version",
        }
        missing = sorted(required - set(payload))
        if missing:
            raise RuntimeError(f"CodeGraph worker result missing fields: {', '.join(missing)}")
        if str(payload["build_id"]) != build.build_id:
            raise RuntimeError("CodeGraph worker result build_id mismatch")
        if str(payload["source_ref"]) != self._source_ref(build):
            raise RuntimeError("CodeGraph worker result source_ref mismatch")
        if str(payload["source_revision"]) != build.artifact_revision:
            raise RuntimeError("CodeGraph worker result revision mismatch")
        if str(payload["source_digest"]) != build.artifact_digest:
            raise RuntimeError("CodeGraph worker result digest mismatch")
        if str(payload["generation_bucket"]) != build.generation_bucket:
            raise RuntimeError("CodeGraph worker result bucket mismatch")
        if str(payload["generation_key"]) != build.generation_key:
            raise RuntimeError("CodeGraph worker result key mismatch")
        if str(payload["codegraph_version"]) != self.codegraph_version:
            raise RuntimeError("CodeGraph worker result version mismatch")
        if str(payload["index_profile"]) != self.index_profile:
            raise RuntimeError("CodeGraph worker result profile mismatch")
        if str(payload["index_mode"]) != "full":
            raise RuntimeError("initial Flux CodeGraph build must be full")
        return payload

    def _submit_pending(self) -> int:
        handled = 0
        for build in self.store.pending(limit=self.batch_size):
            try:
                current = self.flux.get_artifact(self._event_from_build(build))
                if current.digest != build.artifact_digest or current.revision != build.artifact_revision:
                    detail = (
                        "Flux artifact was superseded before CodeGraph build: "
                        f"event={build.artifact_revision}/{build.artifact_digest} "
                        f"current={current.revision}/{current.digest}"
                    )
                    if self.store.mark_superseded(build.build_id, detail):
                        WORKFLOW_OPERATIONS.labels(operation="submit", outcome="superseded").inc()
                        log.info(
                            "codegraph_event=superseded build_id=%s source=%s/%s revision=%s",
                            build.build_id, build.source_namespace, build.source_name, build.artifact_revision,
                        )
                    handled += 1
                    continue

                generation_key = self._generation_key(build.build_id)
                workflow = self.argo.submit(
                    build_id=build.build_id,
                    source_ref=self._source_ref(build),
                    source_url=current.url,
                    source_revision=current.revision,
                    source_digest=current.digest,
                    generation_bucket=self.generation_bucket,
                    generation_key=generation_key,
                    worker_image=self.worker_image,
                    codegraph_version=self.codegraph_version,
                    index_profile=self.index_profile,
                )
                submitted = self.store.mark_submitted(
                    build_id=build.build_id,
                    artifact_url=current.url,
                    workflow_namespace=workflow.namespace,
                    workflow_name=workflow.name,
                    workflow_uid=workflow.uid,
                    generation_bucket=self.generation_bucket,
                    generation_key=generation_key,
                )
                log.info(
                    "submitted CodeGraph Workflow build_id=%s source=%s/%s revision=%s digest=%s workflow=%s/%s",
                    build.build_id,
                    build.source_namespace,
                    build.source_name,
                    build.artifact_revision,
                    build.artifact_digest,
                    workflow.namespace,
                    workflow.name,
                )
                if submitted:
                    WORKFLOW_OPERATIONS.labels(operation="submit", outcome="succeeded").inc()
                handled += 1
            except Exception:
                # Leave the row in received state. The deterministic Workflow name
                # makes a retry converge if creation succeeded before the DB update.
                log.exception("failed to reconcile received CodeGraph build build_id=%s", build.build_id)
                WORKFLOW_OPERATIONS.labels(operation="submit", outcome="error").inc()
        return handled

    def _observe_active(self) -> int:
        handled = 0
        for build in self.store.active(limit=self.batch_size):
            if not build.workflow_name:
                if self.store.complete_failure(build_id=build.build_id, detail="active build has no workflow name"):
                    WORKFLOW_OPERATIONS.labels(operation="observe", outcome="failed").inc()
                    log.error("codegraph_event=failed build_id=%s reason=missing_workflow_name", build.build_id)
                handled += 1
                continue
            try:
                workflow = self.argo.get(build.workflow_name)
                status = workflow.get("status") if isinstance(workflow, dict) else None
                phase = str(status.get("phase") or "") if isinstance(status, dict) else ""
                if phase == "Running":
                    if self.store.mark_running(build.build_id):
                        WORKFLOW_OPERATIONS.labels(operation="observe", outcome="running").inc()
                        log.info("codegraph_event=running build_id=%s workflow=%s", build.build_id, build.workflow_name)
                    handled += 1
                    continue
                if phase == "Succeeded":
                    result = self._read_result(build)
                    completed = self.store.complete_success(build_id=build.build_id, result=result)
                    if completed:
                        WORKFLOW_OPERATIONS.labels(operation="observe", outcome="succeeded").inc()
                        if isinstance(result.get("duration_ms"), (int, float)):
                            WORKER_DURATION.observe(max(float(result["duration_ms"]) / 1000.0, 0.0))
                    log.info(
                        "codegraph_event=succeeded build_id=%s workflow=%s generation=s3://%s/%s duration_ms=%s",
                        build.build_id,
                        build.workflow_name,
                        build.generation_bucket,
                        build.generation_key,
                        result.get("duration_ms"),
                    )
                    handled += 1
                    continue
                if phase in {"Failed", "Error"}:
                    message = str(status.get("message") or f"Argo Workflow phase={phase}") if isinstance(status, dict) else phase
                    if self.store.complete_failure(build_id=build.build_id, detail=message):
                        WORKFLOW_OPERATIONS.labels(operation="observe", outcome="failed").inc()
                        log.error(
                            "codegraph_event=failed build_id=%s workflow=%s phase=%s detail=%s",
                            build.build_id, build.workflow_name, phase, message[:1000],
                        )
                    handled += 1
            except Exception:
                log.exception("failed to observe CodeGraph Workflow build_id=%s", build.build_id)
                WORKFLOW_OPERATIONS.labels(operation="observe", outcome="error").inc()
        return handled

    def drain_once(self) -> int:
        return self._submit_pending() + self._observe_active()

    def run_forever(self) -> None:
        self.drain_once()
        while True:
            try:
                with self.store.notification_connection() as conn:
                    conn.execute(sql.SQL("LISTEN {}").format(sql.Identifier(self.store.notify_channel)))
                    log.info("listening for CodeGraph build work channel=%s", self.store.notify_channel)
                    while True:
                        for _notify in conn.notifies(timeout=self.idle_poll_seconds, stop_after=1):
                            break
                        self.drain_once()
            except Exception:
                log.exception("CodeGraph controller listener failed; reconnecting")
                time.sleep(min(self.idle_poll_seconds, 5.0))


def create_app(
    controller: CodeGraphController,
    store: CodeGraphBuildStore,
    *,
    webhook_token: str | None = None,
) -> FastAPI:
    app = FastAPI(title="memory-steward-codegraph-controller", version="0.2")

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        refresh_metrics(store.telemetry_snapshot())
        payload, content_type = render_metrics()
        return Response(content=payload, media_type=content_type)

    @app.post("/events/flux")
    def flux_event(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        if webhook_token and authorization != f"Bearer {webhook_token}":
            EVENTS.labels(outcome="unauthorized").inc()
            raise HTTPException(status_code=401, detail="invalid Flux webhook token")
        try:
            event = parse_flux_new_artifact(
                payload, artifact_lookup=controller.flux.get_artifact_for_source
            )
        except ValueError as exc:
            EVENTS.labels(outcome="invalid").inc()
            log.warning("codegraph_event=invalid_flux_event reason=%s", str(exc))
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            EVENTS.labels(outcome="lookup_failed").inc()
            log.exception("codegraph_event=flux_artifact_lookup_failed")
            raise HTTPException(status_code=503, detail="Flux source artifact unavailable") from exc
        if event is None:
            EVENTS.labels(outcome="ignored").inc()
            log.info("codegraph_event=ignored_flux_event reason=%s", str(payload.get("reason", "missing"))[:80])
            return {"accepted": False, "ignored": True}

        result = store.record_event(event)
        outcome = "accepted" if result.inserted else "duplicate"
        EVENTS.labels(outcome=outcome).inc()
        log.info(
            "codegraph_event=%s build_id=%s source=%s/%s revision=%s digest=%s",
            outcome, result.build_id, event.source_namespace, event.source_name,
            event.artifact_revision, event.artifact_digest,
        )
        return {
            "accepted": result.inserted,
            "duplicate": not result.inserted,
            "build_id": result.build_id,
        }

    return app


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    namespace = os.environ.get("POD_NAMESPACE", "ms")
    generation_bucket = os.environ.get("CODEGRAPH_GENERATION_BUCKET", "codegraph")
    store = CodeGraphBuildStore.from_env()
    controller = CodeGraphController(
        store,
        flux=FluxSourceClient(),
        argo=ArgoWorkflowClient(
            namespace=namespace,
            workflow_template=os.environ.get("CODEGRAPH_WORKFLOW_TEMPLATE", "codegraph-build"),
        ),
        generation_bucket=generation_bucket,
        worker_image=os.environ["CODEGRAPH_WORKER_IMAGE"],
        batch_size=int(os.environ.get("CODEGRAPH_CONTROLLER_BATCH_SIZE", "16")),
        idle_poll_seconds=float(os.environ.get("CODEGRAPH_CONTROLLER_POLL_SECONDS", "5")),
        codegraph_version=os.environ.get("CODEGRAPH_VERSION", "0.20.1"),
        index_profile=os.environ.get("CODEGRAPH_INDEX_PROFILE", "graph-only"),
    )
    log.info("codegraph_event=controller_start namespace=%s workflow_template=%s", namespace, controller.argo.workflow_template)
    thread = threading.Thread(target=controller.run_forever, name="codegraph-controller-loop", daemon=True)
    thread.start()

    app = create_app(
        controller,
        store,
        webhook_token=os.environ.get("CODEGRAPH_FLUX_WEBHOOK_TOKEN") or None,
    )
    logging.getLogger("uvicorn.access").addFilter(_SuppressSuccessfulHealthz())
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("CODEGRAPH_CONTROLLER_PORT", "8093")),
    )


if __name__ == "__main__":
    main()
