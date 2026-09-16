from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

STATE_ARTIFACT_SCHEMA_VERSION = 1
CANONICAL_WORKSPACE = Path("/workspace/repo")


class CodeGraphStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class CodeGraphStateManifest:
    schema_version: int
    repository: str | None
    revision: str
    codegraph_version: str
    index_profile: str
    workspace_path: str
    source_bucket: str
    source_object_key: str
    base_revision: str | None = None
    index_mode: str = "full"

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "CodeGraphStateManifest":
        if int(value.get("schema_version", -1)) != STATE_ARTIFACT_SCHEMA_VERSION:
            raise CodeGraphStateError("unsupported CodeGraph state artifact schema")
        return cls(
            schema_version=STATE_ARTIFACT_SCHEMA_VERSION,
            repository=value.get("repository"),
            revision=str(value["revision"]),
            codegraph_version=str(value["codegraph_version"]),
            index_profile=str(value["index_profile"]),
            workspace_path=str(value["workspace_path"]),
            source_bucket=str(value["source_bucket"]),
            source_object_key=str(value["source_object_key"]),
            base_revision=value.get("base_revision"),
            index_mode=str(value.get("index_mode") or "full"),
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative_path(name: str) -> Path:
    pure = PurePosixPath(name)
    if pure.is_absolute():
        raise CodeGraphStateError(f"unsafe archive path: {name!r}")
    parts: list[str] = []
    for part in pure.parts:
        if part in ("", "."):
            continue
        if part == "..":
            raise CodeGraphStateError(f"unsafe archive path: {name!r}")
        parts.append(part)
    return Path(*parts) if parts else Path(".")


def _safe_link_target(member_name: str, link_name: str) -> str:
    link = PurePosixPath(link_name)
    if link.is_absolute():
        raise CodeGraphStateError(f"unsafe absolute archive link: {link_name!r}")
    parent = PurePosixPath(member_name).parent
    parts: list[str] = []
    for part in (parent / link).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise CodeGraphStateError(f"archive link escapes extraction root: {link_name!r}")
            parts.pop()
        else:
            parts.append(part)
    return link_name


def _extract_tar(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    symlinks: list[tarfile.TarInfo] = []
    with tarfile.open(path, "r:*") as archive:
        members = archive.getmembers()
        for member in members:
            rel = _safe_relative_path(member.name)
            if member.issym():
                _safe_link_target(member.name, member.linkname)
                symlinks.append(member)
                continue
            if member.islnk():
                raise CodeGraphStateError("hard links are not accepted in repository/state archives")
            target = destination / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise CodeGraphStateError(f"unsupported tar member type: {member.name!r}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise CodeGraphStateError(f"cannot read archive member: {member.name!r}")
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            os.chmod(target, member.mode & 0o777)

        # Symlinks are created last so regular-file extraction can never traverse
        # an archive-created symlink outside the destination.
        for member in symlinks:
            rel = _safe_relative_path(member.name)
            target = destination / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(_safe_link_target(member.name, member.linkname))


def _zip_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def _extract_zip(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    symlinks: list[zipfile.ZipInfo] = []
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            rel = _safe_relative_path(info.filename.rstrip("/"))
            target = destination / rel
            mode = _zip_mode(info)
            if stat.S_ISLNK(mode):
                symlinks.append(info)
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            if mode:
                os.chmod(target, mode & 0o777)

        for info in symlinks:
            rel = _safe_relative_path(info.filename)
            target = destination / rel
            link_name = archive.read(info).decode("utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(_safe_link_target(info.filename, link_name))


def extract_archive(path: Path, destination: Path) -> None:
    lower = path.name.lower()
    if lower.endswith(".zip"):
        _extract_zip(path, destination)
        return
    if lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")):
        _extract_tar(path, destination)
        return
    if lower.endswith((".tar.zst", ".tzst", ".zst")):
        try:
            import zstandard
        except ImportError as exc:  # pragma: no cover - dependency is present in the image
            raise CodeGraphStateError("zstandard dependency is required for .zst archives") from exc
        with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
            tar_path = Path(tmp.name)
        try:
            with path.open("rb") as compressed, tar_path.open("wb") as raw:
                zstandard.ZstdDecompressor().copy_stream(compressed, raw)
            _extract_tar(tar_path, destination)
        finally:
            tar_path.unlink(missing_ok=True)
        return
    raise CodeGraphStateError(f"unsupported repository archive format: {path.name}")


def find_repository_root(extracted_root: Path) -> Path:
    candidates = sorted(
        (path.parent for path in extracted_root.rglob(".git") if path.is_dir()),
        key=lambda path: len(path.relative_to(extracted_root).parts),
    )
    if not candidates:
        raise CodeGraphStateError("repository snapshot does not contain a .git directory")

    root = candidates[0]
    disjoint = [candidate for candidate in candidates[1:] if root not in candidate.parents]
    if disjoint:
        raise CodeGraphStateError("repository snapshot contains multiple disjoint .git repositories")
    return root


def git_revision(repository_root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "--verify", "HEAD^{commit}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise CodeGraphStateError(f"cannot resolve Git HEAD: {result.stderr.strip()}")
    revision = result.stdout.strip()
    if len(revision) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in revision):
        raise CodeGraphStateError("Git HEAD did not resolve to a full commit SHA")
    return revision.lower()


def prepare_canonical_workspace(extracted_root: Path, canonical_path: Path = CANONICAL_WORKSPACE) -> Path:
    repository_root = find_repository_root(extracted_root)
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    if canonical_path.exists() or canonical_path.is_symlink():
        if canonical_path.is_dir() and not canonical_path.is_symlink():
            shutil.rmtree(canonical_path)
        else:
            canonical_path.unlink()
    shutil.move(str(repository_root), str(canonical_path))
    return canonical_path


def create_state_bundle(
    *,
    codegraph_home: Path,
    manifest: CodeGraphStateManifest,
    output_path: Path,
) -> str:
    state_dir = codegraph_home / ".codegraph"
    if not state_dir.is_dir():
        raise CodeGraphStateError("CodeGraph state directory was not created")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="codegraph-state-") as tmp_dir:
        stage = Path(tmp_dir)
        (stage / "manifest.json").write_text(
            json.dumps(asdict(manifest), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        shutil.copytree(state_dir, stage / ".codegraph", symlinks=True)
        with tarfile.open(output_path, "w:gz") as archive:
            archive.add(stage / "manifest.json", arcname="manifest.json", recursive=False)
            archive.add(stage / ".codegraph", arcname=".codegraph", recursive=True)
    return sha256_file(output_path)


def restore_state_bundle(
    *,
    bundle_path: Path,
    expected_digest: str | None,
    codegraph_home: Path,
) -> CodeGraphStateManifest:
    if expected_digest and sha256_file(bundle_path) != expected_digest:
        raise CodeGraphStateError("CodeGraph state artifact digest mismatch")

    with tempfile.TemporaryDirectory(prefix="codegraph-restore-") as tmp_dir:
        extracted = Path(tmp_dir)
        _extract_tar(bundle_path, extracted)
        manifest_path = extracted / "manifest.json"
        state_dir = extracted / ".codegraph"
        if not manifest_path.is_file() or not state_dir.is_dir():
            raise CodeGraphStateError("CodeGraph state artifact is incomplete")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise CodeGraphStateError("CodeGraph state artifact manifest is invalid")
        manifest = CodeGraphStateManifest.from_json(raw)

        destination = codegraph_home / ".codegraph"
        if destination.exists():
            shutil.rmtree(destination)
        codegraph_home.mkdir(parents=True, exist_ok=True)
        shutil.copytree(state_dir, destination, symlinks=True)
        return manifest


def state_artifact_key(
    *,
    source_object_key: str,
    revision: str,
    codegraph_version: str,
    index_profile: str,
) -> str:
    safe_profile = index_profile.replace("/", "-")
    return (
        f"{source_object_key}.codegraph/{revision}/"
        f"codegraph-{codegraph_version}/{safe_profile}/state-v{STATE_ARTIFACT_SCHEMA_VERSION}.tar.gz"
    )


def _git(repository_root: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def incremental_is_safe(
    *,
    repository_root: Path,
    target_revision: str,
    base_manifest: CodeGraphStateManifest,
    repository: str | None,
    codegraph_version: str,
    index_profile: str,
    canonical_workspace: Path = CANONICAL_WORKSPACE,
) -> tuple[bool, str]:
    if not repository or base_manifest.repository != repository:
        return False, "repository_identity_mismatch"
    if base_manifest.codegraph_version != codegraph_version:
        return False, "codegraph_version_mismatch"
    if base_manifest.index_profile != index_profile:
        return False, "index_profile_mismatch"
    if base_manifest.workspace_path != str(canonical_workspace):
        return False, "workspace_path_mismatch"

    base_revision = base_manifest.revision
    exists = _git(repository_root, "cat-file", "-e", f"{base_revision}^{{commit}}")
    if exists.returncode != 0:
        return False, "base_revision_unavailable"

    ancestor = _git(repository_root, "merge-base", "--is-ancestor", base_revision, target_revision)
    if ancestor.returncode != 0:
        return False, "base_revision_not_ancestor"

    diff = _git(
        repository_root,
        "diff",
        "--name-status",
        "--find-renames",
        f"{base_revision}..{target_revision}",
    )
    if diff.returncode != 0:
        return False, "git_diff_failed"

    for line in diff.stdout.splitlines():
        status_code = line.split("\t", 1)[0]
        if status_code.startswith(("D", "R")):
            return False, "delete_or_rename_requires_full_rebuild"
    return True, "compatible_incremental_base"
