from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import uvicorn
from fastapi import FastAPI, Header, HTTPException

from memory_steward.codegraph_state import (
    CodeGraphStateError,
    CodeGraphStateManifest,
    extract_archive,
    git_revision,
    prepare_canonical_workspace,
    restore_state_bundle,
)

log = logging.getLogger("memory-steward.codegraph-serve")


# Agent-facing read/query surface for CodeGraph v0.20.1. The worker adapter
# is a second enforcement point behind Memory Steward capability routing.
AGENT_CODEGRAPH_TOOLS = frozenset(
    {
        "codegraph_symbol_search",
        "codegraph_get_symbol_info",
        "codegraph_get_detailed_symbol",
        "codegraph_get_ai_context",
        "codegraph_get_edit_context",
        "codegraph_get_curated_context",
        "codegraph_search_by_pattern",
        "codegraph_search_by_error",
        "codegraph_get_callers",
        "codegraph_get_callees",
        "codegraph_get_call_graph",
        "codegraph_get_dependency_graph",
        "codegraph_analyze_impact",
        "codegraph_analyze_complexity",
        "codegraph_traverse_graph",
        "codegraph_find_circular_deps",
        "codegraph_find_entry_points",
        "codegraph_find_hot_paths",
        "codegraph_find_by_imports",
        "codegraph_find_by_signature",
        "codegraph_find_implementors",
        "codegraph_find_dead_imports",
        "codegraph_get_module_summary",
        "codegraph_find_related_tests",
        "codegraph_pr_context",
    }
)


@dataclass(frozen=True)
class ServeWorkerConfig:
    registry_id: str
    worker_generation: int
    worker_endpoint: str
    source_bucket: str
    source_object_key: str
    source_version_id: str | None
    repository: str | None
    project_id: str | None
    run_id: str | None
    realm: str | None
    indexed_revision: str
    codegraph_version: str
    index_profile: str
    state_artifact_bucket: str
    state_artifact_key: str
    state_artifact_digest: str
    controller_url: str
    callback_token: str | None
    proxy_token: str | None
    codegraph_binary: str
    work_root: Path
    codegraph_home: Path
    port: int

    @classmethod
    def from_env(cls) -> "ServeWorkerConfig":
        return cls(
            registry_id=os.environ["CODEGRAPH_REGISTRY_ID"],
            worker_generation=int(os.environ["CODEGRAPH_WORKER_GENERATION"]),
            worker_endpoint=os.environ["CODEGRAPH_WORKER_ENDPOINT"],
            source_bucket=os.environ["CODEGRAPH_SOURCE_BUCKET"],
            source_object_key=os.environ["CODEGRAPH_SOURCE_OBJECT_KEY"],
            source_version_id=os.environ.get("CODEGRAPH_SOURCE_VERSION_ID") or None,
            repository=os.environ.get("CODEGRAPH_REPOSITORY") or None,
            project_id=os.environ.get("CODEGRAPH_PROJECT_ID") or None,
            run_id=os.environ.get("CODEGRAPH_RUN_ID") or None,
            realm=os.environ.get("CODEGRAPH_REALM") or None,
            indexed_revision=os.environ["CODEGRAPH_INDEXED_REVISION"].lower(),
            codegraph_version=os.environ.get("CODEGRAPH_VERSION", "0.20.1"),
            index_profile=os.environ.get("CODEGRAPH_INDEX_PROFILE", "graph-only"),
            state_artifact_bucket=os.environ["CODEGRAPH_STATE_ARTIFACT_BUCKET"],
            state_artifact_key=os.environ["CODEGRAPH_STATE_ARTIFACT_KEY"],
            state_artifact_digest=os.environ["CODEGRAPH_STATE_ARTIFACT_DIGEST"],
            controller_url=os.environ["CODEGRAPH_CONTROLLER_URL"].rstrip("/"),
            callback_token=os.environ.get("CODEGRAPH_WORKER_CALLBACK_TOKEN") or None,
            proxy_token=os.environ.get("CODEGRAPH_WORKER_PROXY_TOKEN") or None,
            codegraph_binary=os.environ.get("CODEGRAPH_BINARY", "/usr/local/bin/codegraph-server"),
            work_root=Path(os.environ.get("CODEGRAPH_WORK_ROOT", "/workspace")),
            codegraph_home=Path(os.environ.get("CODEGRAPH_HOME", "/state/home")),
            port=int(os.environ.get("CODEGRAPH_SERVE_PORT", "8094")),
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


def _verify_codegraph_binary(config: ServeWorkerConfig) -> None:
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


def _validate_manifest(
    config: ServeWorkerConfig,
    *,
    manifest: CodeGraphStateManifest,
    workspace: Path,
) -> None:
    expected = {
        "revision": config.indexed_revision,
        "codegraph_version": config.codegraph_version,
        "index_profile": config.index_profile,
        "workspace_path": str(workspace),
        "source_bucket": config.source_bucket,
        "source_object_key": config.source_object_key,
    }
    actual = {
        "revision": manifest.revision.lower(),
        "codegraph_version": manifest.codegraph_version,
        "index_profile": manifest.index_profile,
        "workspace_path": manifest.workspace_path,
        "source_bucket": manifest.source_bucket,
        "source_object_key": manifest.source_object_key,
    }
    for name, expected_value in expected.items():
        if actual[name] != expected_value:
            raise CodeGraphStateError(
                f"CodeGraph state manifest {name} mismatch: expected {expected_value!r}, got {actual[name]!r}"
            )
    if config.repository and manifest.repository != config.repository:
        raise CodeGraphStateError("CodeGraph state manifest repository mismatch")


def _build_command(config: ServeWorkerConfig, workspace: Path) -> list[str]:
    command = [
        config.codegraph_binary,
        "--mcp",
        "--workspace",
        str(workspace),
    ]
    if config.index_profile == "graph-only":
        command.append("--graph-only")
    elif config.index_profile != "full":
        raise RuntimeError(f"unsupported CodeGraph index profile: {config.index_profile}")
    return command


class StdioMcpClient:
    def __init__(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float = 30.0,
    ):
        self.timeout_seconds = timeout_seconds
        self._next_id = 1
        self._write_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._initialized = False
        self._process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None or self._process.stderr is None:
            raise RuntimeError("failed to open CodeGraph stdio pipes")
        self._reader = threading.Thread(target=self._read_stdout, name="codegraph-mcp-stdout", daemon=True)
        self._stderr = threading.Thread(target=self._read_stderr, name="codegraph-mcp-stderr", daemon=True)
        self._reader.start()
        self._stderr.start()

    @property
    def alive(self) -> bool:
        return self._process.poll() is None

    @property
    def initialized(self) -> bool:
        return self._initialized and self.alive

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for raw in self._process.stdout:
            line = raw.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                log.warning("ignoring non-JSON CodeGraph stdout line: %s", line[:500])
                continue
            response_id = message.get("id")
            if not isinstance(response_id, int):
                continue
            with self._pending_lock:
                waiter = self._pending.get(response_id)
            if waiter is not None:
                waiter.put(message)

    def _read_stderr(self) -> None:
        assert self._process.stderr is not None
        for raw in self._process.stderr:
            line = raw.rstrip()
            if line:
                log.info("codegraph-server: %s", line)

    def _write(self, message: dict[str, Any]) -> None:
        if not self.alive:
            raise RuntimeError(f"CodeGraph process exited with code {self._process.returncode}")
        assert self._process.stdin is not None
        encoded = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
        with self._write_lock:
            self._process.stdin.write(encoded + "\n")
            self._process.stdin.flush()

    def _request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._pending_lock:
            request_id = self._next_id
            self._next_id += 1
            waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self._pending[request_id] = waiter
        try:
            message: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
            }
            if params is not None:
                message["params"] = params
            self._write(message)
            try:
                response = waiter.get(timeout=self.timeout_seconds)
            except queue.Empty as exc:
                raise TimeoutError(f"CodeGraph MCP request timed out: {method}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)
        if "error" in response:
            raise RuntimeError(f"CodeGraph MCP {method} failed: {response['error']}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"CodeGraph MCP {method} returned invalid result")
        return result

    def initialize(self) -> list[dict[str, Any]]:
        result = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "memory-steward-codegraph-adapter",
                    "version": "0.1.0",
                },
            },
        )
        if not result.get("protocolVersion"):
            raise RuntimeError("CodeGraph MCP initialize returned no protocol version")
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._initialized = True
        tools = self.list_tools()
        if not tools:
            raise RuntimeError("CodeGraph MCP returned no tools")
        return tools

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise RuntimeError("CodeGraph MCP tools/list returned invalid tools")
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )

    def close(self) -> None:
        if self.alive:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)


def create_adapter_app(client: StdioMcpClient, *, proxy_token: str | None) -> FastAPI:
    app = FastAPI(title="memory-steward-codegraph-serve", version="0.1")

    def authorize(authorization: str | None) -> None:
        if proxy_token and authorization != f"Bearer {proxy_token}":
            raise HTTPException(status_code=401, detail="invalid CodeGraph proxy token")

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        if not client.initialized:
            raise HTTPException(status_code=503, detail="CodeGraph backend unavailable")
        return {"ok": True}

    @app.get("/v1/tools")
    def tools(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        authorize(authorization)
        return {
            "tools": [
                tool
                for tool in client.list_tools()
                if tool.get("name") in AGENT_CODEGRAPH_TOOLS
            ]
        }

    @app.post("/v1/call")
    def call(
        payload: dict[str, Any],
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        authorize(authorization)
        name = payload.get("name")
        arguments = payload.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise HTTPException(status_code=400, detail="tool name is required")
        if not isinstance(arguments, dict):
            raise HTTPException(status_code=400, detail="tool arguments must be an object")
        if name not in AGENT_CODEGRAPH_TOOLS:
            raise HTTPException(status_code=403, detail="CodeGraph tool is not agent-authorized")
        return client.call_tool(name, arguments)

    return app


def _report(config: ServeWorkerConfig, payload: dict[str, Any]) -> None:
    headers: dict[str, str] = {}
    if config.callback_token:
        headers["Authorization"] = f"Bearer {config.callback_token}"
    last_error: Exception | None = None
    for attempt in range(8):
        try:
            response = requests.post(
                f"{config.controller_url}/v1/codegraph/serve-result",
                json=payload,
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            return
        except Exception as exc:  # pragma: no cover - integration/runtime behavior
            last_error = exc
            if attempt == 7:
                break
            time.sleep(min(0.25 * (2**attempt), 2.0))
    raise RuntimeError(f"failed to report CodeGraph serve result: {last_error}")


def _prepare(config: ServeWorkerConfig) -> tuple[Path, StdioMcpClient]:
    client = _minio_client()
    config.work_root.mkdir(parents=True, exist_ok=True)
    config.codegraph_home.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="codegraph-serve-", dir=config.work_root))
    try:
        source_archive = scratch / Path(config.source_object_key).name
        state_bundle = scratch / "codegraph-state.tar.gz"
        extracted = scratch / "source"
        _download_object(
            client,
            bucket=config.source_bucket,
            object_key=config.source_object_key,
            version_id=config.source_version_id,
            destination=source_archive,
        )
        _download_object(
            client,
            bucket=config.state_artifact_bucket,
            object_key=config.state_artifact_key,
            version_id=None,
            destination=state_bundle,
        )
        extract_archive(source_archive, extracted)
        workspace = prepare_canonical_workspace(extracted, config.work_root / "repo")
        actual_revision = git_revision(workspace)
        if actual_revision != config.indexed_revision:
            raise CodeGraphStateError(
                f"workspace revision mismatch: expected {config.indexed_revision}, got {actual_revision}"
            )
        manifest = restore_state_bundle(
            bundle_path=state_bundle,
            expected_digest=config.state_artifact_digest,
            codegraph_home=config.codegraph_home,
        )
        _validate_manifest(config, manifest=manifest, workspace=workspace)
        _verify_codegraph_binary(config)
        env = os.environ.copy()
        env["HOME"] = str(config.codegraph_home)
        mcp_client = StdioMcpClient(
            _build_command(config, workspace),
            cwd=workspace,
            env=env,
        )
        mcp_client.initialize()
        return workspace, mcp_client
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    config = ServeWorkerConfig.from_env()
    started = time.monotonic()
    mcp_client: StdioMcpClient | None = None
    server: uvicorn.Server | None = None
    server_thread: threading.Thread | None = None
    try:
        _workspace, mcp_client = _prepare(config)
        app = create_adapter_app(mcp_client, proxy_token=config.proxy_token)
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="0.0.0.0",
                port=config.port,
                log_level=os.environ.get("LOG_LEVEL", "info").lower(),
            )
        )
        server_thread = threading.Thread(target=server.run, name="codegraph-serve-http", daemon=True)
        server_thread.start()
        deadline = time.monotonic() + 15.0
        while not server.started and server_thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not server.started:
            raise RuntimeError("CodeGraph adapter HTTP server failed to start")

        payload = {
            "registry_id": config.registry_id,
            "worker_generation": config.worker_generation,
            "worker_endpoint": config.worker_endpoint,
            "indexed_revision": config.indexed_revision,
            "ok": True,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        _report(config, payload)
        server_thread.join()
    except Exception as exc:
        log.exception("CodeGraph serve worker failed")
        failure = {
            "registry_id": config.registry_id,
            "worker_generation": config.worker_generation,
            "worker_endpoint": config.worker_endpoint,
            "ok": False,
            "error_detail": str(exc),
        }
        try:
            _report(config, failure)
        except Exception:
            log.exception("failed to report CodeGraph serve failure")
        raise
    finally:
        if server is not None:
            server.should_exit = True
        if server_thread is not None and server_thread.is_alive():
            server_thread.join(timeout=5)
        if mcp_client is not None:
            mcp_client.close()


if __name__ == "__main__":
    main()
