"""Serve an immutable Flux CodeGraph generation through the existing MCP adapter."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import uvicorn

from memory_steward.codegraph_serve import StdioMcpClient, _download_object, _minio_client, create_adapter_app
from memory_steward.codegraph_state import (
    GENERATION_ARTIFACT_SCHEMA_VERSION,
    _extract_tar,
    sha256_file,
)

log = logging.getLogger("memory-steward.codegraph-generation-serve")


class _SuppressSuccessfulProbes(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (
            record.name == "uvicorn.access"
            and isinstance(args, tuple)
            and len(args) == 5
            and args[1] == "GET"
            and args[2] in {"/healthz", "/metrics"}
            and args[4] == 200
        )


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    bucket = os.environ["CODEGRAPH_GENERATION_BUCKET"]
    key = os.environ["CODEGRAPH_GENERATION_KEY"]
    digest = os.environ["CODEGRAPH_GENERATION_DIGEST"]
    source_ref = os.environ["CODEGRAPH_SOURCE_REF"]
    revision = os.environ["CODEGRAPH_SOURCE_REVISION"]
    source_digest = os.environ["CODEGRAPH_SOURCE_DIGEST"]
    version = os.environ["CODEGRAPH_VERSION"]
    profile = os.environ["CODEGRAPH_INDEX_PROFILE"]
    binary = os.environ.get("CODEGRAPH_BINARY", "/usr/local/bin/codegraph-server")
    home = Path("/state/home")
    workspace = Path("/workspace/repo")
    home.mkdir(parents=True, exist_ok=True)
    workspace.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cg-generation-") as temp:
        archive = Path(temp) / "generation.tar.gz"
        extracted = Path(temp) / "extracted"
        _download_object(_minio_client(), bucket=bucket, object_key=key,
                         version_id=None, destination=archive)
        actual_digest = sha256_file(archive)
        if actual_digest != digest:
            raise RuntimeError(f"CodeGraph generation digest mismatch: {digest} != {actual_digest}")
        _extract_tar(archive, extracted)
        manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
        expected = {
            "schema_version": GENERATION_ARTIFACT_SCHEMA_VERSION,
            "source_ref": source_ref,
            "source_revision": revision,
            "source_digest": source_digest,
            "codegraph_version": version,
            "index_profile": profile,
            "workspace_path": str(workspace),
        }
        if not isinstance(manifest, dict) or any(manifest.get(k) != v for k, v in expected.items()):
            raise RuntimeError("CodeGraph generation manifest does not match requested source identity")
        if not (extracted / "workspace").is_dir() or not (extracted / ".codegraph").is_dir():
            raise RuntimeError("CodeGraph generation is incomplete")
        shutil.move(str(extracted / "workspace"), str(workspace))
        shutil.move(str(extracted / ".codegraph"), str(home / ".codegraph"))

    result = subprocess.run([binary, "--version"], capture_output=True, text=True,
                            check=True, timeout=30)
    if not result.stdout.strip().endswith(version):
        raise RuntimeError(f"CodeGraph producer mismatch: {result.stdout.strip()} != {version}")
    command = [binary, "--mcp", "--workspace", str(workspace)]
    if profile == "graph-only":
        command.append("--graph-only")
    elif profile != "full":
        raise RuntimeError(f"unsupported CodeGraph profile: {profile}")
    env = os.environ.copy()
    env["HOME"] = str(home)
    client = StdioMcpClient(command, cwd=workspace, env=env)
    try:
        tools = client.initialize()
        log.info("codegraph_stage=serving source=%s revision=%s tools=%s", source_ref, revision, len(tools))
        app = create_adapter_app(client, proxy_token=os.environ.get("CODEGRAPH_WORKER_PROXY_TOKEN") or None)
        logging.getLogger("uvicorn.access").addFilter(_SuppressSuccessfulProbes())
        uvicorn.run(app, host="0.0.0.0", port=8094, log_level="info", access_log=False)
    finally:
        client.close()


if __name__ == "__main__":
    main()
