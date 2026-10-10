from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from memory_steward.argo_workflows import ArgoWorkflowClient, WorkflowRef
from memory_steward.codegraph_builds import BuildRecord, RecordResult
from memory_steward.codegraph_controller import CodeGraphController, create_app
from memory_steward.codegraph_state import extract_archive
from memory_steward.codegraph_worker import FluxIndexWorkerConfig, _verify_flux_digest, run_flux_index
from memory_steward.flux_source import FluxArtifactStatus, FluxSourceClient, parse_flux_new_artifact


def _event(*, digest: str = "sha256:" + "a" * 64) -> dict:
    return {
        "involvedObject": {
            "apiVersion": "source.toolkit.fluxcd.io/v1",
            "kind": "GitRepository",
            "name": "project-source",
            "namespace": "flux-system",
            "uid": "11111111-2222-3333-4444-555555555555",
        },
        "metadata": {
            "source.toolkit.fluxcd.io/revision": "main@sha1:" + "b" * 40,
            "source.toolkit.fluxcd.io/digest": digest,
        },
        "reason": "NewArtifact",
        "reportingController": "source-controller",
        "severity": "info",
    }


def _build(*, state: str = "received") -> BuildRecord:
    return BuildRecord(
        build_id="00000000-0000-0000-0000-000000000001",
        source_api_version="source.toolkit.fluxcd.io/v1",
        source_kind="GitRepository",
        source_namespace="flux-system",
        source_name="project-source",
        source_uid="11111111-2222-3333-4444-555555555555",
        artifact_revision="main@sha1:" + "b" * 40,
        artifact_digest="sha256:" + "a" * 64,
        artifact_url=None if state == "received" else "http://source-controller/artifact.tar.gz",
        state=state,
        workflow_namespace=None if state == "received" else "ms",
        workflow_name=None if state == "received" else "cg-build-00000000000000000000000000000001",
        workflow_uid=None,
        generation_bucket=None if state == "received" else "codegraph",
        generation_key=None if state == "received" else "codegraph/builds/00000000-0000-0000-0000-000000000001/generation-v1.tar.gz",
    )


def test_parse_flux_new_artifact():
    parsed = parse_flux_new_artifact(_event())
    assert parsed is not None
    assert parsed.source_name == "project-source"
    assert parsed.artifact_revision.endswith("b" * 40)
    assert parsed.artifact_digest == "sha256:" + "a" * 64


def test_parse_flux_ignores_non_new_artifact():
    payload = _event()
    payload["reason"] = "Succeeded"
    assert parse_flux_new_artifact(payload) is None




def test_flux_source_client_reads_current_artifact():
    api = MagicMock()
    api.get_namespaced_custom_object.return_value = {
        "status": {
            "artifact": {
                "url": "http://source-controller/artifact.tar.gz",
                "revision": "main@sha1:" + "b" * 40,
                "digest": "sha256:" + "a" * 64,
            }
        }
    }
    event = parse_flux_new_artifact(_event())
    assert event is not None

    artifact = FluxSourceClient(api=api).get_artifact(event)

    assert artifact.url == "http://source-controller/artifact.tar.gz"
    assert artifact.revision == event.artifact_revision
    assert artifact.digest == event.artifact_digest
    api.get_namespaced_custom_object.assert_called_once_with(
        group="source.toolkit.fluxcd.io",
        version="v1",
        namespace="flux-system",
        plural="gitrepositories",
        name="project-source",
    )


def test_argo_submit_uses_deterministic_workflow_and_template_parameters():
    api = MagicMock()
    api.create_namespaced_custom_object.return_value = {"metadata": {"uid": "workflow-uid"}}
    client = ArgoWorkflowClient(namespace="ms", workflow_template="codegraph-build", api=api)

    ref = client.submit(
        build_id="00000000-0000-0000-0000-000000000001",
        source_ref="source.toolkit.fluxcd.io/v1:flux-system/GitRepository/project-source",
        source_url="http://source-controller/artifact.tar.gz",
        source_revision="main@sha1:" + "b" * 40,
        source_digest="sha256:" + "a" * 64,
        generation_bucket="codegraph",
        generation_key="codegraph/builds/1/generation-v1.tar.gz",
        worker_image="ghcr.io/homel-dev/memory-steward/memory-steward@sha256:" + "c" * 64,
        codegraph_version="0.20.1",
        index_profile="graph-only",
    )

    assert ref.name == "cg-build-00000000000000000000000000000001"
    body = api.create_namespaced_custom_object.call_args.kwargs["body"]
    assert body["spec"]["workflowTemplateRef"] == {"name": "codegraph-build"}
    params = {item["name"]: item["value"] for item in body["spec"]["arguments"]["parameters"]}
    assert params["worker-image"].endswith("c" * 64)
    assert params["source-digest"] == "sha256:" + "a" * 64


def test_flux_ingress_persists_and_deduplicates():
    store = MagicMock()
    store.record_event.side_effect = [
        RecordResult(build_id="id-1", inserted=True),
        RecordResult(build_id="id-1", inserted=False),
    ]
    client = TestClient(create_app(MagicMock(), store))

    first = client.post("/events/flux", json=_event())
    second = client.post("/events/flux", json=_event())

    assert first.status_code == 200
    assert first.json() == {"accepted": True, "duplicate": False, "build_id": "id-1"}
    assert second.json() == {"accepted": False, "duplicate": True, "build_id": "id-1"}
    assert store.record_event.call_count == 2


def test_controller_submits_current_flux_artifact():
    store = MagicMock()
    store.pending.return_value = [_build()]
    store.active.return_value = []
    flux = MagicMock()
    flux.get_artifact.return_value = FluxArtifactStatus(
        url="http://source-controller/artifact.tar.gz",
        revision="main@sha1:" + "b" * 40,
        digest="sha256:" + "a" * 64,
    )
    argo = MagicMock()
    argo.submit.return_value = WorkflowRef(namespace="ms", name="cg-build-1", uid="workflow-uid")
    controller = CodeGraphController(store, flux=flux, argo=argo, generation_bucket="codegraph", worker_image="memory-steward@sha256:test")

    assert controller.drain_once() == 1
    argo.submit.assert_called_once()
    store.mark_submitted.assert_called_once()
    store.mark_superseded.assert_not_called()


def test_controller_supersedes_stale_event_without_workflow():
    store = MagicMock()
    store.pending.return_value = [_build()]
    store.active.return_value = []
    flux = MagicMock()
    flux.get_artifact.return_value = FluxArtifactStatus(
        url="http://source-controller/new.tar.gz",
        revision="main@sha1:" + "c" * 40,
        digest="sha256:" + "d" * 64,
    )
    argo = MagicMock()
    controller = CodeGraphController(store, flux=flux, argo=argo, generation_bucket="codegraph", worker_image="memory-steward@sha256:test")

    assert controller.drain_once() == 1
    store.mark_superseded.assert_called_once()
    argo.submit.assert_not_called()


class _ObjectResponse(io.BytesIO):
    def release_conn(self) -> None:
        return None


class _FakeMinio:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self.buckets: set[str] = set()

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.buckets

    def make_bucket(self, bucket: str) -> None:
        self.buckets.add(bucket)

    def fput_object(
        self,
        bucket: str,
        object_key: str,
        source: str,
        *,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.objects[(bucket, object_key)] = Path(source).read_bytes()
        self.metadata[(bucket, object_key)] = metadata or {}

    def get_object(self, bucket: str, object_key: str):
        return _ObjectResponse(self.objects[(bucket, object_key)])


def _plain_flux_archive(path: Path) -> str:
    source = path.parent / "source"
    source.mkdir()
    (source / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    with tarfile.open(path, "w:gz") as archive:
        archive.add(source / "main.py", arcname="main.py")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def test_flux_worker_indexes_snapshot_without_git_and_publishes_generation(monkeypatch, tmp_path):
    archive = tmp_path / "artifact.tar.gz"
    digest = _plain_flux_archive(archive)
    fake_minio = _FakeMinio()

    def fake_download(*, url: str, destination: Path) -> None:
        assert url == "http://source-controller/artifact.tar.gz"
        destination.write_bytes(archive.read_bytes())

    def fake_run(config: FluxIndexWorkerConfig, repository_root: Path):
        assert (repository_root / "main.py").is_file()
        state = config.codegraph_home / ".codegraph"
        state.mkdir(parents=True)
        (state / "index.db").write_text("ok", encoding="utf-8")
        return "{}", ""

    monkeypatch.setattr("memory_steward.codegraph_worker._download_flux_artifact", fake_download)
    monkeypatch.setattr("memory_steward.codegraph_worker._minio_client", lambda: fake_minio)
    monkeypatch.setattr("memory_steward.codegraph_worker._verify_codegraph_binary", lambda _config: None)
    monkeypatch.setattr("memory_steward.codegraph_worker._run_codegraph", fake_run)

    config = FluxIndexWorkerConfig(
        build_id="build-1",
        source_ref="source.toolkit.fluxcd.io/v1:flux-system/GitRepository/project-source",
        source_url="http://source-controller/artifact.tar.gz",
        source_revision="main@sha1:" + "b" * 40,
        source_digest=digest,
        generation_bucket="codegraph",
        generation_key="codegraph/builds/build-1/generation-v1.tar.gz",
        codegraph_version="0.20.1",
        index_profile="graph-only",
        codegraph_binary="codegraph-server",
        index_timeout_seconds=60,
        work_root=tmp_path / "work",
        codegraph_home=tmp_path / "home",
    )

    result = run_flux_index(config)
    assert result["index_mode"] == "full"
    assert result["source_ref"] == config.source_ref
    assert result["source_digest"] == digest
    assert ("codegraph", config.generation_key) in fake_minio.objects
    assert ("codegraph", config.generation_key + ".result.json") in fake_minio.objects

    bundle = tmp_path / "generation.tar.gz"
    bundle.write_bytes(fake_minio.objects[("codegraph", config.generation_key)])
    extracted = tmp_path / "generation"
    extract_archive(bundle, extracted)
    assert (extracted / "workspace" / "main.py").is_file()
    assert (extracted / ".codegraph" / "index.db").is_file()
    manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_ref"] == config.source_ref
    assert manifest["source_revision"] == config.source_revision
    assert manifest["source_digest"] == digest


def test_flux_digest_mismatch_is_rejected(tmp_path):
    artifact = tmp_path / "artifact.tar.gz"
    artifact.write_bytes(b"not-the-expected-artifact")
    try:
        _verify_flux_digest(artifact, "sha256:" + "0" * 64)
    except RuntimeError as exc:
        assert "digest mismatch" in str(exc)
    else:
        raise AssertionError("digest mismatch must fail")


def test_controller_completes_only_from_matching_worker_result():
    build = _build(state="running")
    store = MagicMock()
    store.pending.return_value = []
    store.active.return_value = [build]
    argo = MagicMock()
    argo.get.return_value = {"status": {"phase": "Succeeded"}}
    fake_minio = _FakeMinio()
    fake_minio.buckets.add("codegraph")
    result = {
        "build_id": build.build_id,
        "source_ref": "source.toolkit.fluxcd.io/v1:flux-system/GitRepository/project-source",
        "source_revision": build.artifact_revision,
        "source_digest": build.artifact_digest,
        "codegraph_version": "0.20.1",
        "index_profile": "graph-only",
        "index_mode": "full",
        "generation_bucket": build.generation_bucket,
        "generation_key": build.generation_key,
        "generation_digest": "e" * 64,
        "generation_schema_version": 1,
        "duration_ms": 10,
    }
    fake_minio.objects[("codegraph", build.generation_key + ".result.json")] = json.dumps(result).encode()
    controller = CodeGraphController(
        store,
        flux=MagicMock(),
        argo=argo,
        generation_bucket="codegraph",
        worker_image="memory-steward@sha256:test",
        minio_client=fake_minio,
    )

    assert controller.drain_once() == 1
    store.complete_success.assert_called_once_with(build_id=build.build_id, result=result)
