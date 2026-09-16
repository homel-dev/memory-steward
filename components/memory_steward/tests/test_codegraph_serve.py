from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from memory_steward.codegraph_controller import CodeGraphController
from memory_steward.codegraph_controller import create_app as create_controller_app
from memory_steward.codegraph_registry import ServeWork
from memory_steward.codegraph_serve import (
    ServeWorkerConfig,
    _build_command,
    create_adapter_app,
)


def _serve_work() -> ServeWork:
    return ServeWork(
        registry_id="00000000-0000-0000-0000-000000000001",
        worker_generation=2,
        worker_id="cg-serve-000000000000-g2",
        worker_endpoint="http://cg-serve-000000000000-g2.ms.svc.cluster.local:8094",
        source_bucket="rr-exports",
        source_object_key="runs/1/repo.tar.gz",
        source_version_id=None,
        project_id="project-1",
        run_id="run-1",
        realm="workspace",
        repository="homel-dev/example",
        indexed_revision="a" * 40,
        codegraph_version="0.20.1",
        index_profile="graph-only",
        state_artifact_bucket="rr-exports",
        state_artifact_key="runs/1/repo.tar.gz.codegraph/state.tar.gz",
        state_artifact_digest="b" * 64,
    )


def _config() -> ServeWorkerConfig:
    work = _serve_work()
    return ServeWorkerConfig(
        registry_id=work.registry_id,
        worker_generation=work.worker_generation,
        worker_endpoint=work.worker_endpoint,
        source_bucket=work.source_bucket,
        source_object_key=work.source_object_key,
        source_version_id=work.source_version_id,
        repository=work.repository,
        project_id=work.project_id,
        run_id=work.run_id,
        realm=work.realm,
        indexed_revision=work.indexed_revision,
        codegraph_version=work.codegraph_version,
        index_profile=work.index_profile,
        state_artifact_bucket=work.state_artifact_bucket,
        state_artifact_key=work.state_artifact_key,
        state_artifact_digest=work.state_artifact_digest,
        controller_url="http://controller:8093",
        callback_token=None,
        proxy_token=None,
        codegraph_binary="/usr/local/bin/codegraph-server",
        work_root=Path("/workspace"),
        codegraph_home=Path("/state/home"),
        port=8094,
    )


def test_controller_launches_reserved_serve_work():
    registry = MagicMock()
    registry.claim_discovered.return_value = []
    registry.reserve_queued_index_work.return_value = []
    registry.reserve_activating_serve_work.return_value = [_serve_work()]
    index_launcher = MagicMock()
    serve_launcher = MagicMock()
    controller = CodeGraphController(
        registry,
        launcher=index_launcher,
        serve_launcher=serve_launcher,
        namespace="ms",
        batch_size=4,
    )

    count = controller.drain_serve_once()

    assert count == 1
    registry.reserve_activating_serve_work.assert_called_once_with(limit=4, namespace="ms")
    serve_launcher.launch.assert_called_once()


def test_controller_accepts_serve_callback_only_after_probe(monkeypatch):
    registry = MagicMock()
    registry.complete_serve_success.return_value = True
    controller = CodeGraphController(registry)

    class _Response:
        def __init__(self, payload=None):
            self._payload = payload or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    monkeypatch.setattr(
        "memory_steward.codegraph_controller.requests.get",
        lambda url, **kwargs: _Response({"tools": [{"name": "codegraph_symbol_search"}]})
        if url.endswith("/v1/tools")
        else _Response(),
    )
    client = TestClient(
        create_controller_app(
            controller,
            callback_token="callback",
            proxy_token="proxy",
        )
    )
    work = _serve_work()
    response = client.post(
        "/v1/codegraph/serve-result",
        headers={"Authorization": "Bearer callback"},
        json={
            "registry_id": work.registry_id,
            "worker_generation": work.worker_generation,
            "worker_endpoint": work.worker_endpoint,
            "indexed_revision": work.indexed_revision,
            "ok": True,
        },
    )

    assert response.status_code == 200
    registry.complete_serve_success.assert_called_once_with(
        registry_id=work.registry_id,
        worker_generation=work.worker_generation,
        indexed_revision=work.indexed_revision,
        worker_endpoint=work.worker_endpoint,
    )


def test_controller_rejects_arbitrary_serve_endpoint_before_probe(monkeypatch):
    registry = MagicMock()
    controller = CodeGraphController(registry, namespace="ms")
    probe = MagicMock()
    monkeypatch.setattr("memory_steward.codegraph_controller.requests.get", probe)
    client = TestClient(create_controller_app(controller))
    work = _serve_work()

    response = client.post(
        "/v1/codegraph/serve-result",
        json={
            "registry_id": work.registry_id,
            "worker_generation": work.worker_generation,
            "worker_endpoint": "http://postgres.ms.svc.cluster.local:5432",
            "indexed_revision": work.indexed_revision,
            "ok": True,
        },
    )

    assert response.status_code == 409
    probe.assert_not_called()
    registry.complete_serve_success.assert_not_called()


def test_adapter_requires_proxy_token_and_routes_tool_calls():
    backend = MagicMock()
    backend.initialized = True
    backend.list_tools.return_value = [
        {"name": "codegraph_get_callers"},
        {"name": "codegraph_reindex_workspace"},
    ]
    backend.call_tool.return_value = {"content": [{"type": "text", "text": "ok"}]}
    client = TestClient(create_adapter_app(backend, proxy_token="secret"))

    assert client.get("/v1/tools").status_code == 401
    tools = client.get("/v1/tools", headers={"Authorization": "Bearer secret"})
    assert tools.status_code == 200
    assert [tool["name"] for tool in tools.json()["tools"]] == ["codegraph_get_callers"]

    result = client.post(
        "/v1/call",
        headers={"Authorization": "Bearer secret"},
        json={"name": "codegraph_get_callers", "arguments": {"name": "main"}},
    )
    assert result.status_code == 200
    backend.call_tool.assert_called_once_with("codegraph_get_callers", {"name": "main"})

    backend.call_tool.reset_mock()
    denied = client.post(
        "/v1/call",
        headers={"Authorization": "Bearer secret"},
        json={"name": "codegraph_reindex_workspace", "arguments": {}},
    )
    assert denied.status_code == 403
    backend.call_tool.assert_not_called()


def test_serve_command_uses_upstream_mcp_mode_and_same_profile():
    config = _config()
    command = _build_command(config, Path("/workspace/repo"))
    assert command == [
        "/usr/local/bin/codegraph-server",
        "--mcp",
        "--workspace",
        "/workspace/repo",
        "--graph-only",
    ]
