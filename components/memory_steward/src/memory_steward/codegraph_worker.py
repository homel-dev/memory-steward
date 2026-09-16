from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from memory_steward.codegraph_state import (
    STATE_ARTIFACT_SCHEMA_VERSION,
    CodeGraphStateError,
    CodeGraphStateManifest,
    create_state_bundle,
    extract_archive,
    git_revision,
    incremental_is_safe,
    prepare_canonical_workspace,
    restore_state_bundle,
    state_artifact_key,
)

log = logging.getLogger("memory-steward.codegraph-worker")


class UnindexableError(CodeGraphStateError):
    pass


@dataclass(frozen=True)
class IndexWorkerConfig:
    registry_id: str
    worker_generation: int
    source_bucket: str
    source_object_key: str
    source_version_id: str | None
    repository: str | None
    project_id: str | None
    run_id: str | None
    realm: str | None
    codegraph_version: str
    index_profile: str
    controller_url: str
    callback_token: str | None
    codegraph_binary: str
    index_timeout_seconds: int
    work_root: Path
    codegraph_home: Path
    base_artifact_bucket: str | None
    base_artifact_key: str | None
    base_artifact_digest: str | None

    @classmethod
    def from_env(cls) -> "IndexWorkerConfig":
        return cls(
            registry_id=os.environ["CODEGRAPH_REGISTRY_ID"],
            worker_generation=int(os.environ["CODEGRAPH_WORKER_GENERATION"]),
            source_bucket=os.environ["CODEGRAPH_SOURCE_BUCKET"],
            source_object_key=os.environ["CODEGRAPH_SOURCE_OBJECT_KEY"],
            source_version_id=os.environ.get("CODEGRAPH_SOURCE_VERSION_ID") or None,
            repository=os.environ.get("CODEGRAPH_REPOSITORY") or None,
            project_id=os.environ.get("CODEGRAPH_PROJECT_ID") or None,
            run_id=os.environ.get("CODEGRAPH_RUN_ID") or None,
            realm=os.environ.get("CODEGRAPH_REALM") or None,
            codegraph_version=os.environ.get("CODEGRAPH_VERSION", "0.20.1"),
            index_profile=os.environ.get("CODEGRAPH_INDEX_PROFILE", "graph-only"),
            controller_url=os.environ["CODEGRAPH_CONTROLLER_URL"].rstrip("/"),
            callback_token=os.environ.get("CODEGRAPH_WORKER_CALLBACK_TOKEN") or None,
            codegraph_binary=os.environ.get("CODEGRAPH_BINARY", "/usr/local/bin/codegraph-server"),
            index_timeout_seconds=int(os.environ.get("CODEGRAPH_INDEX_TIMEOUT_SECONDS", "1800")),
            work_root=Path(os.environ.get("CODEGRAPH_WORK_ROOT", "/workspace")),
            codegraph_home=Path(os.environ.get("CODEGRAPH_HOME", "/state/home")),
            base_artifact_bucket=os.environ.get("CODEGRAPH_BASE_ARTIFACT_BUCKET") or None,
            base_artifact_key=os.environ.get("CODEGRAPH_BASE_ARTIFACT_KEY") or None,
            base_artifact_digest=os.environ.get("CODEGRAPH_BASE_ARTIFACT_DIGEST") or None,
        )


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _minio_client():
    try:
        from minio import Minio
    except ImportError as exc:  # pragma: no cover - installed in runtime image
        raise RuntimeError("minio Python package is not installed") from exc

    raw_endpoint = os.environ["MINIO_ENDPOINT"]
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


def _download_object(
    client: Any,
    *,
    bucket: str,
    object_key: str,
    version_id: str | None,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    response = client.get_object(bucket, object_key, version_id=version_id)
    try:
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)
    finally:
        response.close()
        response.release_conn()


def _upload_object(
    client: Any,
    *,
    bucket: str,
    object_key: str,
    source: Path,
    metadata: dict[str, str],
) -> None:
    client.fput_object(
        bucket,
        object_key,
        str(source),
        content_type="application/gzip",
        metadata=metadata,
    )


def _verify_codegraph_binary(config: IndexWorkerConfig) -> None:
    result = subprocess.run(
        [config.codegraph_binary, "--version"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"CodeGraph binary failed version check: {result.stderr.strip()}")
    reported = result.stdout.strip().split()
    actual_version = reported[-1] if reported else ""
    if actual_version != config.codegraph_version:
        raise RuntimeError(
            f"CodeGraph binary version mismatch: expected {config.codegraph_version}, got {result.stdout.strip()}"
        )


def _run_codegraph(config: IndexWorkerConfig, repository_root: Path) -> tuple[str, str]:
    command = [
        config.codegraph_binary,
        "--workspace",
        str(repository_root),
    ]
    if config.index_profile == "graph-only":
        command.append("--graph-only")
    elif config.index_profile != "full":
        raise RuntimeError(f"unsupported CodeGraph index profile: {config.index_profile}")
    command.extend(
        [
            "--run-tool",
            "codegraph_find_entry_points",
            "--tool-args",
            '{"compact":true,"limit":1}',
        ]
    )
    env = os.environ.copy()
    env["HOME"] = str(config.codegraph_home)
    result = subprocess.run(
        command,
        cwd=repository_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=config.index_timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(f"CodeGraph indexing failed: {result.stderr[-4000:].strip()}")
    return result.stdout, result.stderr


def _restore_incremental_base(
    *,
    client: Any,
    config: IndexWorkerConfig,
    repository_root: Path,
    target_revision: str,
    scratch: Path,
    canonical_workspace: Path,
) -> tuple[str, str | None]:
    if not config.base_artifact_bucket or not config.base_artifact_key:
        return "full", None

    bundle = scratch / "base-state.tar.gz"
    try:
        _download_object(
            client,
            bucket=config.base_artifact_bucket,
            object_key=config.base_artifact_key,
            version_id=None,
            destination=bundle,
        )
        manifest = restore_state_bundle(
            bundle_path=bundle,
            expected_digest=config.base_artifact_digest,
            codegraph_home=config.codegraph_home,
        )
        safe, reason = incremental_is_safe(
            repository_root=repository_root,
            target_revision=target_revision,
            base_manifest=manifest,
            repository=config.repository,
            codegraph_version=config.codegraph_version,
            index_profile=config.index_profile,
            canonical_workspace=canonical_workspace,
        )
        if safe:
            log.info("using incremental CodeGraph base revision=%s", manifest.revision)
            return "incremental", manifest.revision
        log.info("discarding incremental CodeGraph base reason=%s", reason)
    except Exception:
        log.exception("failed to restore/validate incremental CodeGraph base; falling back to full")

    state_dir = config.codegraph_home / ".codegraph"
    if state_dir.exists():
        shutil.rmtree(state_dir)
    return "full", None


def _report(config: IndexWorkerConfig, payload: dict[str, Any]) -> None:
    headers: dict[str, str] = {}
    if config.callback_token:
        headers["Authorization"] = f"Bearer {config.callback_token}"
    url = f"{config.controller_url}/v1/codegraph/index-result"
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            response.raise_for_status()
            return
        except Exception as exc:  # pragma: no cover - exercised through integration runtime
            last_error = exc
            log.warning("controller callback failed attempt=%s error=%s", attempt + 1, exc)
            time.sleep(min(2**attempt, 10))
    raise RuntimeError(f"failed to report CodeGraph worker result: {last_error}")


def run_index(config: IndexWorkerConfig) -> dict[str, Any]:
    started = time.monotonic()
    client = _minio_client()
    config.work_root.mkdir(parents=True, exist_ok=True)
    config.codegraph_home.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="codegraph-index-", dir=config.work_root) as tmp_dir:
        scratch = Path(tmp_dir)
        source_archive = scratch / Path(config.source_object_key).name
        extracted = scratch / "source"

        _download_object(
            client,
            bucket=config.source_bucket,
            object_key=config.source_object_key,
            version_id=config.source_version_id,
            destination=source_archive,
        )
        extract_archive(source_archive, extracted)
        canonical_workspace = config.work_root / "repo"
        try:
            repository_root = prepare_canonical_workspace(extracted, canonical_workspace)
        except CodeGraphStateError as exc:
            raise UnindexableError(str(exc)) from exc
        target_revision = git_revision(repository_root)

        _verify_codegraph_binary(config)
        index_mode, base_revision = _restore_incremental_base(
            client=client,
            config=config,
            repository_root=repository_root,
            target_revision=target_revision,
            scratch=scratch,
            canonical_workspace=canonical_workspace,
        )

        _stdout, stderr = _run_codegraph(config, repository_root)
        log.info("CodeGraph indexing complete revision=%s mode=%s", target_revision, index_mode)
        if stderr:
            log.debug("CodeGraph stderr tail: %s", stderr[-2000:])

        artifact_path = scratch / "codegraph-state.tar.gz"
        manifest = CodeGraphStateManifest(
            schema_version=STATE_ARTIFACT_SCHEMA_VERSION,
            repository=config.repository,
            revision=target_revision,
            codegraph_version=config.codegraph_version,
            index_profile=config.index_profile,
            workspace_path=str(canonical_workspace),
            source_bucket=config.source_bucket,
            source_object_key=config.source_object_key,
            base_revision=base_revision,
            index_mode=index_mode,
        )
        digest = create_state_bundle(
            codegraph_home=config.codegraph_home,
            manifest=manifest,
            output_path=artifact_path,
        )
        artifact_key = state_artifact_key(
            source_object_key=config.source_object_key,
            revision=target_revision,
            codegraph_version=config.codegraph_version,
            index_profile=config.index_profile,
        )
        metadata = {
            "git-sha": target_revision,
            "codegraph-version": config.codegraph_version,
            "index-profile": config.index_profile,
            "state-schema-version": str(STATE_ARTIFACT_SCHEMA_VERSION),
            "source-object": config.source_object_key,
        }
        if config.repository:
            metadata["repository"] = config.repository
        _upload_object(
            client,
            bucket=config.source_bucket,
            object_key=artifact_key,
            source=artifact_path,
            metadata=metadata,
        )

        return {
            "registry_id": config.registry_id,
            "worker_generation": config.worker_generation,
            "ok": True,
            "indexed_revision": target_revision,
            "codegraph_version": config.codegraph_version,
            "index_profile": config.index_profile,
            "index_mode": index_mode,
            "base_revision": base_revision,
            "state_artifact_bucket": config.source_bucket,
            "state_artifact_key": artifact_key,
            "state_artifact_digest": digest,
            "state_artifact_schema_version": STATE_ARTIFACT_SCHEMA_VERSION,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    mode = os.environ.get("CODEGRAPH_WORKER_MODE", "index")
    if mode != "index":
        raise SystemExit(f"unsupported CodeGraph worker mode in this slice: {mode}")

    config = IndexWorkerConfig.from_env()
    try:
        payload = run_index(config)
    except UnindexableError as exc:
        payload = {
            "registry_id": config.registry_id,
            "worker_generation": config.worker_generation,
            "ok": False,
            "failure_state": "unindexable",
            "error_detail": str(exc),
        }
    except Exception as exc:
        log.exception("CodeGraph index worker failed")
        payload = {
            "registry_id": config.registry_id,
            "worker_generation": config.worker_generation,
            "ok": False,
            "failure_state": "failed",
            "error_detail": str(exc),
        }

    _report(config, payload)
    print(json.dumps(payload, sort_keys=True))
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
