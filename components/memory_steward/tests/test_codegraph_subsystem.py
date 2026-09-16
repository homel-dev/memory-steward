from __future__ import annotations

import io
import subprocess
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from memory_steward.codegraph_controller import CodeGraphController
from memory_steward.codegraph_controller import create_app as create_controller_app
from memory_steward.codegraph_listener import _discovery_record, create_app
from memory_steward.codegraph_registry import (
    DiscoveryResult,
    IncrementalBase,
    IndexSuccess,
    IndexWork,
    QueuedWork,
    source_identity,
)
from memory_steward.codegraph_state import (
    STATE_ARTIFACT_SCHEMA_VERSION,
    CodeGraphStateError,
    CodeGraphStateManifest,
    create_state_bundle,
    extract_archive,
    git_revision,
    incremental_is_safe,
    restore_state_bundle,
    state_artifact_key,
)
from memory_steward.codegraph_worker import (
    IndexWorkerConfig,
    UnindexableError,
    _verify_codegraph_binary,
    run_index,
)


def _minio_record(*, event_name: str = "s3:ObjectCreated:Put") -> dict:
    return {
        "eventName": event_name,
        "eventTime": "2026-09-15T20:00:00.000Z",
        "s3": {
            "bucket": {"name": "rr-exports"},
            "object": {
                "key": "runs%2Frun-123%2Frepo.tar.zst",
                "size": 12345,
                "eTag": "etag-1",
                "versionId": "version-1",
                "sequencer": "abc123",
                "userMetadata": {
                    "project-id": "project-1",
                    "run_id": "run-123",
                    "realm": "workspace",
                    "repository": "homel-dev/example",
                },
            },
        },
    }


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _create_git_repo(root: Path) -> Path:
    repo = root / "repo-src"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "test")
    (repo / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _archive_repo(repo: Path, output: Path) -> None:
    with tarfile.open(output, "w:gz") as archive:
        archive.add(repo, arcname="repo")


class _ObjectResponse(io.BytesIO):
    def release_conn(self) -> None:
        return None


class _FakeMinio:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}

    def get_object(self, bucket: str, object_key: str, version_id: str | None = None):
        del version_id
        return _ObjectResponse(self.objects[(bucket, object_key)])

    def fput_object(
        self,
        bucket: str,
        object_key: str,
        source: str,
        *,
        content_type: str,
        metadata: dict[str, str],
    ) -> None:
        assert content_type == "application/gzip"
        self.objects[(bucket, object_key)] = Path(source).read_bytes()
        self.metadata[(bucket, object_key)] = metadata


def test_source_identity_is_stable_and_revision_of_object_sensitive():
    first = source_identity(
        bucket="bucket",
        object_key="repo.tar.zst",
        version_id="v1",
        sequencer="seq-a",
        etag="etag-a",
    )
    same = source_identity(
        bucket="bucket",
        object_key="repo.tar.zst",
        version_id="v1",
        sequencer="seq-a",
        etag="etag-a",
    )
    changed = source_identity(
        bucket="bucket",
        object_key="repo.tar.zst",
        version_id="v2",
        sequencer="seq-b",
        etag="etag-b",
    )

    assert first == same
    assert first != changed


def test_discovery_record_extracts_minio_identity_and_metadata():
    record = _discovery_record(_minio_record())

    assert record is not None
    assert record.source_bucket == "rr-exports"
    assert record.source_object_key == "runs/run-123/repo.tar.zst"
    assert record.project_id == "project-1"
    assert record.run_id == "run-123"
    assert record.realm == "workspace"
    assert record.repository == "homel-dev/example"


def test_discovery_record_ignores_non_created_events():
    assert _discovery_record(_minio_record(event_name="s3:ObjectRemoved:Delete")) is None


def test_listener_inserts_new_event_and_counts_duplicate(monkeypatch):
    registry = MagicMock()
    registry.discover.side_effect = [
        DiscoveryResult(registry_id="id-1", inserted=True),
        DiscoveryResult(registry_id="id-1", inserted=False),
    ]
    monkeypatch.setenv("CODEGRAPH_MINIO_BUCKETS", "rr-exports")
    app = create_app(registry)
    client = TestClient(app)
    payload = {"Records": [_minio_record()]}

    first = client.post("/events/minio", json=payload)
    second = client.post("/events/minio", json=payload)

    assert first.status_code == 200
    assert first.json() == {"accepted": 1, "duplicates": 0, "ignored": 0}
    assert second.status_code == 200
    assert second.json() == {"accepted": 0, "duplicates": 1, "ignored": 0}
    assert registry.discover.call_count == 2


def test_listener_rejects_wrong_webhook_token(monkeypatch):
    registry = MagicMock()
    monkeypatch.setenv("CODEGRAPH_MINIO_WEBHOOK_TOKEN", "secret")
    app = create_app(registry)
    client = TestClient(app)

    response = client.post("/events/minio", json={"Records": [_minio_record()]})

    assert response.status_code == 401
    registry.discover.assert_not_called()


def test_controller_queues_discovered_work_without_launcher():
    registry = MagicMock()
    registry.claim_discovered.return_value = [
        QueuedWork(
            registry_id="id-1",
            source_bucket="rr-exports",
            source_object_key="repo.tar.zst",
            repository="homel-dev/example",
            run_id="run-123",
            realm="workspace",
        )
    ]
    controller = CodeGraphController(registry, launcher=None, batch_size=4, idle_poll_seconds=1.0)

    count = controller.drain_once()

    assert count == 1
    registry.claim_discovered.assert_called_once_with(limit=4)
    registry.reserve_queued_index_work.assert_not_called()


def test_controller_launches_reserved_index_work():
    registry = MagicMock()
    registry.claim_discovered.return_value = []
    work = IndexWork(
        registry_id="00000000-0000-0000-0000-000000000001",
        worker_generation=1,
        worker_id="cg-index-000000000000-g1",
        source_bucket="rr-exports",
        source_object_key="repo.tar.gz",
        source_version_id=None,
        project_id="project-1",
        run_id="run-1",
        realm="workspace",
        repository="homel-dev/example",
        base=IncrementalBase(
            artifact_bucket="rr-exports",
            artifact_key="old.codegraph/state.tar.gz",
            artifact_digest="deadbeef",
            revision="a" * 40,
        ),
    )
    registry.reserve_queued_index_work.return_value = [work]
    launcher = MagicMock()
    controller = CodeGraphController(registry, launcher=launcher, batch_size=4)

    count = controller.drain_once()

    assert count == 1
    registry.reserve_queued_index_work.assert_called_once_with(
        limit=4,
        codegraph_version="0.20.1",
        index_profile="graph-only",
    )
    launcher.launch.assert_called_once_with(work)


def test_controller_accepts_successful_worker_callback():
    registry = MagicMock()
    registry.complete_index_success.return_value = True
    controller = CodeGraphController(registry)
    client = TestClient(create_controller_app(controller, callback_token="secret"))

    response = client.post(
        "/v1/codegraph/index-result",
        headers={"Authorization": "Bearer secret"},
        json={
            "registry_id": "00000000-0000-0000-0000-000000000001",
            "worker_generation": 2,
            "ok": True,
            "indexed_revision": "a" * 40,
            "codegraph_version": "0.20.1",
            "index_profile": "graph-only",
            "index_mode": "incremental",
            "base_revision": "b" * 40,
            "state_artifact_bucket": "rr-exports",
            "state_artifact_key": "repo.codegraph/state.tar.gz",
            "state_artifact_digest": "c" * 64,
            "state_artifact_schema_version": 1,
            "duration_ms": 123,
        },
    )

    assert response.status_code == 200
    result = registry.complete_index_success.call_args.args[0]
    assert isinstance(result, IndexSuccess)
    assert result.index_mode == "incremental"
    assert result.duration_ms == 123


def test_state_bundle_round_trip(tmp_path):
    home = tmp_path / "home"
    state = home / ".codegraph"
    (state / "projects" / "repo").mkdir(parents=True)
    (state / "graph.db").mkdir()
    (state / "graph.db" / "CURRENT").write_text("MANIFEST-1", encoding="utf-8")
    (state / "projects" / "repo" / "index_state.json").write_text('{"a.py":1}', encoding="utf-8")
    manifest = CodeGraphStateManifest(
        schema_version=STATE_ARTIFACT_SCHEMA_VERSION,
        repository="homel-dev/example",
        revision="a" * 40,
        codegraph_version="0.20.1",
        index_profile="graph-only",
        workspace_path="/workspace/repo",
        source_bucket="rr-exports",
        source_object_key="repo.tar.gz",
    )
    bundle = tmp_path / "state.tar.gz"

    digest = create_state_bundle(codegraph_home=home, manifest=manifest, output_path=bundle)
    restored_home = tmp_path / "restored"
    restored = restore_state_bundle(
        bundle_path=bundle,
        expected_digest=digest,
        codegraph_home=restored_home,
    )

    assert restored == manifest
    assert (restored_home / ".codegraph" / "graph.db" / "CURRENT").read_text() == "MANIFEST-1"
    assert (restored_home / ".codegraph" / "projects" / "repo" / "index_state.json").is_file()


def test_incremental_is_safe_for_add_modify_and_rejects_delete(tmp_path):
    repo = _create_git_repo(tmp_path)
    first_revision = git_revision(repo)
    manifest = CodeGraphStateManifest(
        schema_version=1,
        repository="homel-dev/example",
        revision=first_revision,
        codegraph_version="0.20.1",
        index_profile="graph-only",
        workspace_path=str(repo),
        source_bucket="rr-exports",
        source_object_key="repo.tar.gz",
    )

    (repo / "main.py").write_text("def main():\n    return 2\n", encoding="utf-8")
    (repo / "new.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "modify and add")
    second_revision = git_revision(repo)

    safe, reason = incremental_is_safe(
        repository_root=repo,
        target_revision=second_revision,
        base_manifest=manifest,
        repository="homel-dev/example",
        codegraph_version="0.20.1",
        index_profile="graph-only",
        canonical_workspace=repo,
    )
    assert safe is True
    assert reason == "compatible_incremental_base"

    (repo / "new.py").unlink()
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "delete")
    third_revision = git_revision(repo)
    safe, reason = incremental_is_safe(
        repository_root=repo,
        target_revision=third_revision,
        base_manifest=CodeGraphStateManifest(
            **{**manifest.__dict__, "revision": second_revision}
        ),
        repository="homel-dev/example",
        codegraph_version="0.20.1",
        index_profile="graph-only",
        canonical_workspace=repo,
    )
    assert safe is False
    assert reason == "delete_or_rename_requires_full_rebuild"


def test_state_artifact_key_is_versioned_and_adjacent():
    key = state_artifact_key(
        source_object_key="runs/run-1/repo.tar.gz",
        revision="a" * 40,
        codegraph_version="0.20.1",
        index_profile="graph-only",
    )
    assert key.startswith("runs/run-1/repo.tar.gz.codegraph/")
    assert "/codegraph-0.20.1/graph-only/state-v1.tar.gz" in key


def test_index_worker_full_then_incremental(monkeypatch, tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    repo = _create_git_repo(source_root)
    first_revision = git_revision(repo)
    first_archive = tmp_path / "first.tar.gz"
    _archive_repo(repo, first_archive)

    fake_minio = _FakeMinio()
    fake_minio.objects[("rr-exports", "runs/1/repo.tar.gz")] = first_archive.read_bytes()
    monkeypatch.setattr("memory_steward.codegraph_worker._minio_client", lambda: fake_minio)
    monkeypatch.setattr("memory_steward.codegraph_worker._verify_codegraph_binary", lambda _config: None)

    def fake_run(config: IndexWorkerConfig, _repository_root: Path):
        state = config.codegraph_home / ".codegraph"
        (state / "graph.db").mkdir(parents=True, exist_ok=True)
        (state / "graph.db" / "CURRENT").write_text("MANIFEST-1", encoding="utf-8")
        (state / "projects" / "repo").mkdir(parents=True, exist_ok=True)
        (state / "projects" / "repo" / "index_state.json").write_text("{}", encoding="utf-8")
        return "{}", ""

    monkeypatch.setattr("memory_steward.codegraph_worker._run_codegraph", fake_run)

    work_root = tmp_path / "work"
    home = tmp_path / "cg-home"
    first_config = IndexWorkerConfig(
        registry_id="id-1",
        worker_generation=1,
        source_bucket="rr-exports",
        source_object_key="runs/1/repo.tar.gz",
        source_version_id=None,
        repository="homel-dev/example",
        project_id="project-1",
        run_id="run-1",
        realm="workspace",
        codegraph_version="0.20.1",
        index_profile="graph-only",
        controller_url="http://controller",
        callback_token=None,
        codegraph_binary="codegraph-server",
        index_timeout_seconds=60,
        work_root=work_root,
        codegraph_home=home,
        base_artifact_bucket=None,
        base_artifact_key=None,
        base_artifact_digest=None,
    )
    first = run_index(first_config)
    assert first["index_mode"] == "full"
    assert first["indexed_revision"] == first_revision

    (repo / "main.py").write_text("def main():\n    return 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "second")
    second_revision = git_revision(repo)
    second_archive = tmp_path / "second.tar.gz"
    _archive_repo(repo, second_archive)
    fake_minio.objects[("rr-exports", "runs/2/repo.tar.gz")] = second_archive.read_bytes()

    second_config = IndexWorkerConfig(
        **{
            **first_config.__dict__,
            "registry_id": "id-2",
            "worker_generation": 2,
            "source_object_key": "runs/2/repo.tar.gz",
            "run_id": "run-2",
            "base_artifact_bucket": first["state_artifact_bucket"],
            "base_artifact_key": first["state_artifact_key"],
            "base_artifact_digest": first["state_artifact_digest"],
        }
    )
    second = run_index(second_config)

    assert second["index_mode"] == "incremental"
    assert second["base_revision"] == first_revision
    assert second["indexed_revision"] == second_revision
    assert fake_minio.metadata[("rr-exports", second["state_artifact_key"])]["git-sha"] == second_revision


def test_index_worker_rejects_snapshot_without_git(monkeypatch, tmp_path):
    source = tmp_path / "plain"
    source.mkdir()
    (source / "main.py").write_text("print('x')\n", encoding="utf-8")
    archive = tmp_path / "plain.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(source, arcname="repo")

    fake_minio = _FakeMinio()
    fake_minio.objects[("rr-exports", "plain.tar.gz")] = archive.read_bytes()
    monkeypatch.setattr("memory_steward.codegraph_worker._minio_client", lambda: fake_minio)
    config = IndexWorkerConfig(
        registry_id="id-1",
        worker_generation=1,
        source_bucket="rr-exports",
        source_object_key="plain.tar.gz",
        source_version_id=None,
        repository="homel-dev/example",
        project_id=None,
        run_id=None,
        realm=None,
        codegraph_version="0.20.1",
        index_profile="graph-only",
        controller_url="http://controller",
        callback_token=None,
        codegraph_binary="codegraph-server",
        index_timeout_seconds=60,
        work_root=tmp_path / "work",
        codegraph_home=tmp_path / "home",
        base_artifact_bucket=None,
        base_artifact_key=None,
        base_artifact_digest=None,
    )

    try:
        run_index(config)
    except UnindexableError as exc:
        assert ".git directory" in str(exc)
    else:
        raise AssertionError("snapshot without .git must be rejected")


def test_archive_extraction_accepts_dot_prefix_and_rejects_traversal(tmp_path):
    safe = tmp_path / "safe.tar.gz"
    payload = b"ok"
    with tarfile.open(safe, "w:gz") as archive:
        info = tarfile.TarInfo("./repo/file.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    destination = tmp_path / "safe-out"
    extract_archive(safe, destination)
    assert (destination / "repo" / "file.txt").read_bytes() == payload

    unsafe = tmp_path / "unsafe.tar.gz"
    with tarfile.open(unsafe, "w:gz") as archive:
        info = tarfile.TarInfo("../escape.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    try:
        extract_archive(unsafe, tmp_path / "unsafe-out")
    except CodeGraphStateError as exc:
        assert "unsafe archive path" in str(exc)
    else:
        raise AssertionError("archive traversal must be rejected")


def test_codegraph_binary_version_match_is_exact(monkeypatch, tmp_path):
    config = IndexWorkerConfig(
        registry_id="id-1",
        worker_generation=1,
        source_bucket="bucket",
        source_object_key="repo.tar.gz",
        source_version_id=None,
        repository="homel-dev/example",
        project_id=None,
        run_id=None,
        realm=None,
        codegraph_version="0.20.1",
        index_profile="graph-only",
        controller_url="http://controller",
        callback_token=None,
        codegraph_binary="codegraph-server",
        index_timeout_seconds=60,
        work_root=tmp_path / "work",
        codegraph_home=tmp_path / "home",
        base_artifact_bucket=None,
        base_artifact_key=None,
        base_artifact_digest=None,
    )
    monkeypatch.setattr(
        "memory_steward.codegraph_worker.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "codegraph-server 0.20.10\n", ""),
    )
    try:
        _verify_codegraph_binary(config)
    except RuntimeError as exc:
        assert "version mismatch" in str(exc)
    else:
        raise AssertionError("0.20.10 must not satisfy expected 0.20.1")
