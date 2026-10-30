"""Optional, guarded first-install restore from a MinIO backup pair.

If MINIO_BUCKET is absent this stage is a no-op. A configured bucket with no
manifest also means a fresh install. Never restore into a populated database.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import urlopen

import psycopg
from minio import Minio
from minio.error import S3Error


BACKUPS = Path("/backups")
MARKER = BACKUPS / "restore-incomplete"


def log(message: str) -> None:
    print(f"bootstrap_restore: {message}", flush=True)


def postgres_has_schema() -> bool:
    # Empty database: no application-defined tables. schema_migrations itself
    # counts as a previously initialized database, even if no rows are left.
    with psycopg.connect(
        host=os.environ.get("PGHOST", "postgres"),
        dbname=os.environ.get("PGDATABASE", "homel"),
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    ) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT EXISTS (
              SELECT 1 FROM pg_catalog.pg_tables
              WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            )
        """)
        return bool(cur.fetchone()[0])


def qdrant_collection_exists() -> bool:
    url = os.environ.get("QDRANT_URL", "http://qdrant:6333").rstrip("/")
    collection = os.environ.get("QDRANT_COLLECTION", "homel_memory")
    try:
        with urlopen(f"{url}/collections/{collection}", timeout=15) as response:
            return response.status == 200
    except HTTPError as exc:
        if exc.code == 404:
            return False
        raise


def checked_section(manifest: dict, section: str) -> tuple[str, str]:
    entry = manifest.get(section)
    if not isinstance(entry, dict):
        raise ValueError(f"backup manifest missing {section} object")
    key, digest = entry.get("key"), entry.get("sha256")
    if not isinstance(key, str) or not key or not isinstance(digest, str):
        raise ValueError(f"invalid {section} key/checksum in backup manifest")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError(f"invalid {section} SHA-256 in backup manifest")
    return key, digest


def download(client: Minio, bucket: str, key: str, checksum: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    client.fget_object(bucket, key, str(path))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != checksum:
        raise RuntimeError(f"backup checksum mismatch for {key}")


def main() -> None:
    if MARKER.exists():
        raise RuntimeError(
            "a previous restore was interrupted; inspect backup and data state "
            "before clearing /backups/restore-incomplete"
        )

    if postgres_has_schema():
        log("existing Postgres schema; skipping restore (never overwrite live data)")
        return

    bucket = os.environ.get("MINIO_BUCKET")
    if not bucket:
        if qdrant_collection_exists():
            raise RuntimeError("Postgres empty but Qdrant collection exists; refusing inconsistent fresh install")
        log("no MinIO restore configuration; fresh install will use migrations")
        return

    required = ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY")
    missing = [key for key in required if not os.environ.get(key)]
    if missing:
        raise ValueError(f"MINIO_BUCKET configured but missing: {', '.join(missing)}")

    endpoint = os.environ["MINIO_ENDPOINT"].removeprefix("http://").removeprefix("https://")
    secure = os.environ.get("MINIO_SECURE", "false").lower() in ("true", "1", "yes")
    if os.environ["MINIO_ENDPOINT"].startswith("https://"):
        secure = True
    client = Minio(
        endpoint,
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=secure,
    )
    manifest_key = os.environ.get("MINIO_MANIFEST_KEY", "memory-steward/latest.json")
    try:
        obj = client.get_object(bucket, manifest_key)
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            if qdrant_collection_exists():
                raise RuntimeError("Postgres empty but Qdrant collection exists; backup manifest missing") from exc
            log(f"no backup manifest at s3://{bucket}/{manifest_key}; fresh install")
            return
        raise
    try:
        manifest = json.loads(obj.read())
    finally:
        obj.close()
        obj.release_conn()
    if not isinstance(manifest, dict):
        raise ValueError("MinIO backup manifest must be a JSON object")

    pg_key, pg_hash = checked_section(manifest, "postgres")
    q_key, q_hash = checked_section(manifest, "qdrant")
    if qdrant_collection_exists():
        raise RuntimeError("Postgres empty but Qdrant collection exists; refusing partial overwrite")

    dump = BACKUPS / "pg" / "bootstrap-from-minio.dump"
    snapshot = BACKUPS / "qdrant" / "bootstrap-from-minio.snapshot"
    download(client, bucket, pg_key, pg_hash, dump)
    download(client, bucket, q_key, q_hash, snapshot)

    # An interrupted two-store restore must fail closed on the next run.
    BACKUPS.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(f"s3://{bucket}/{manifest_key}\n")
    log("validated backup pair; restoring Postgres and Qdrant")
    env = {**os.environ, "DUMP_FILE": dump.name, "SNAPSHOT_FILE": snapshot.name}
    subprocess.run(["bash", "/opt/tooling/restore.sh"], env=env, check=True)
    MARKER.unlink()
    log("restore completed; migration stage may proceed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"FAILED: {exc}")
        sys.exit(1)
