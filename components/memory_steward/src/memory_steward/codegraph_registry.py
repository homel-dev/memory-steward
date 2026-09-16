from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg

DEFAULT_NOTIFY_CHANNEL = "codegraph_registry_work"


def postgres_dsn_from_env(application_name: str) -> str:
    host = os.environ["POSTGRES_SERVICE_HOST"]
    port = os.environ["POSTGRES_SERVICE_PORT"]
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    database = os.environ["POSTGRES_DB"]
    sslmode = os.environ.get("POSTGRES_SSLMODE", "disable")
    return (
        f"postgresql://{user}:{password}@{host}:{port}/{database}"
        f"?sslmode={sslmode}&application_name={application_name}"
    )


def source_identity(
    *,
    bucket: str,
    object_key: str,
    version_id: str | None,
    sequencer: str | None,
    etag: str | None,
) -> str:
    generation = version_id or sequencer or etag or ""
    canonical = json.dumps(
        [bucket, object_key, generation],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DiscoveryRecord:
    source_identity: str
    source_bucket: str
    source_object_key: str
    source_version_id: str | None
    source_etag: str | None
    source_size_bytes: int | None
    source_event_name: str
    source_event_time: datetime | None
    source_sequencer: str | None
    source_metadata: dict[str, Any]
    source_event: dict[str, Any]
    project_id: str | None = None
    run_id: str | None = None
    realm: str | None = None
    repository: str | None = None


@dataclass(frozen=True)
class DiscoveryResult:
    registry_id: str
    inserted: bool


@dataclass(frozen=True)
class QueuedWork:
    registry_id: str
    source_bucket: str
    source_object_key: str
    repository: str | None
    run_id: str | None
    realm: str | None


@dataclass(frozen=True)
class IncrementalBase:
    artifact_bucket: str
    artifact_key: str
    artifact_digest: str
    revision: str


@dataclass(frozen=True)
class IndexWork:
    registry_id: str
    worker_generation: int
    worker_id: str
    source_bucket: str
    source_object_key: str
    source_version_id: str | None
    project_id: str | None
    run_id: str | None
    realm: str | None
    repository: str | None
    base: IncrementalBase | None


@dataclass(frozen=True)
class ServeWork:
    registry_id: str
    worker_generation: int
    worker_id: str
    worker_endpoint: str
    source_bucket: str
    source_object_key: str
    source_version_id: str | None
    project_id: str | None
    run_id: str | None
    realm: str | None
    repository: str | None
    indexed_revision: str
    codegraph_version: str
    index_profile: str
    state_artifact_bucket: str
    state_artifact_key: str
    state_artifact_digest: str


@dataclass(frozen=True)
class IndexSuccess:
    registry_id: str
    worker_generation: int
    indexed_revision: str
    codegraph_version: str
    index_profile: str
    index_mode: str
    base_revision: str | None
    state_artifact_bucket: str
    state_artifact_key: str
    state_artifact_digest: str
    state_artifact_schema_version: int
    duration_ms: int | None = None


class CodeGraphRegistry:
    def __init__(self, dsn: str, *, notify_channel: str = DEFAULT_NOTIFY_CHANNEL):
        self._dsn = dsn
        self.notify_channel = notify_channel

    def _connect(self, *, autocommit: bool = False):
        return psycopg.connect(self._dsn, autocommit=autocommit)

    def notification_connection(self):
        return self._connect(autocommit=True)

    def discover(self, record: DiscoveryRecord) -> DiscoveryResult:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO codegraph_registry (
                  source_identity,
                  source_bucket,
                  source_object_key,
                  source_version_id,
                  source_etag,
                  source_size_bytes,
                  source_event_name,
                  source_event_time,
                  source_sequencer,
                  source_metadata,
                  source_event,
                  project_id,
                  run_id,
                  realm,
                  repository,
                  ready,
                  state
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s::jsonb, %s::jsonb, %s, %s, %s, %s, FALSE, 'discovered'
                )
                ON CONFLICT (source_identity) DO NOTHING
                RETURNING id::text
                """,
                (
                    record.source_identity,
                    record.source_bucket,
                    record.source_object_key,
                    record.source_version_id,
                    record.source_etag,
                    record.source_size_bytes,
                    record.source_event_name,
                    record.source_event_time,
                    record.source_sequencer,
                    json.dumps(record.source_metadata, separators=(",", ":")),
                    json.dumps(record.source_event, separators=(",", ":")),
                    record.project_id,
                    record.run_id,
                    record.realm,
                    record.repository,
                ),
            )
            row = cur.fetchone()
            if row is not None:
                registry_id = str(row[0])
                cur.execute("SELECT pg_notify(%s, %s)", (self.notify_channel, registry_id))
                return DiscoveryResult(registry_id=registry_id, inserted=True)

            cur.execute(
                "SELECT id::text FROM codegraph_registry WHERE source_identity = %s",
                (record.source_identity,),
            )
            existing = cur.fetchone()
            if existing is None:
                raise RuntimeError("codegraph discovery record disappeared after conflict")
            return DiscoveryResult(registry_id=str(existing[0]), inserted=False)

    def claim_discovered(self, *, limit: int) -> list[QueuedWork]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                WITH candidates AS (
                  SELECT id
                  FROM codegraph_registry
                  WHERE ready = FALSE
                    AND state = 'discovered'
                  ORDER BY discovered_at, id
                  FOR UPDATE SKIP LOCKED
                  LIMIT %s
                )
                UPDATE codegraph_registry AS registry
                SET state = 'queued',
                    controller_claimed_at = now(),
                    updated_at = now()
                FROM candidates
                WHERE registry.id = candidates.id
                RETURNING
                  registry.id::text,
                  registry.source_bucket,
                  registry.source_object_key,
                  registry.repository,
                  registry.run_id,
                  registry.realm
                """,
                (limit,),
            )
            return [
                QueuedWork(
                    registry_id=str(row[0]),
                    source_bucket=str(row[1]),
                    source_object_key=str(row[2]),
                    repository=row[3],
                    run_id=row[4],
                    realm=row[5],
                )
                for row in cur.fetchall()
            ]

    def reserve_queued_index_work(
        self,
        *,
        limit: int,
        codegraph_version: str,
        index_profile: str,
    ) -> list[IndexWork]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id::text,
                  worker_generation + 1,
                  source_bucket,
                  source_object_key,
                  source_version_id,
                  project_id,
                  run_id,
                  realm,
                  repository
                FROM codegraph_registry
                WHERE ready = FALSE
                  AND state = 'queued'
                ORDER BY controller_claimed_at, discovered_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            work_items: list[IndexWork] = []
            for row in rows:
                registry_id = str(row[0])
                generation = int(row[1])
                worker_id = f"cg-index-{registry_id.replace('-', '')[:12]}-g{generation}"
                project_id = row[5]
                realm = row[7]
                repository = row[8]

                base: IncrementalBase | None = None
                if repository:
                    cur.execute(
                        """
                        SELECT
                          state_artifact_bucket,
                          state_artifact_key,
                          state_artifact_digest,
                          indexed_revision
                        FROM codegraph_registry
                        WHERE id <> %s::uuid
                          AND repository = %s
                          AND project_id IS NOT DISTINCT FROM %s
                          AND realm IS NOT DISTINCT FROM %s
                          AND codegraph_version = %s
                          AND index_profile = %s
                          AND indexed_revision IS NOT NULL
                          AND state_artifact_bucket IS NOT NULL
                          AND state_artifact_key IS NOT NULL
                          AND state_artifact_digest IS NOT NULL
                        ORDER BY indexing_finished_at DESC NULLS LAST, updated_at DESC
                        LIMIT 1
                        """,
                        (
                            registry_id,
                            repository,
                            project_id,
                            realm,
                            codegraph_version,
                            index_profile,
                        ),
                    )
                    base_row = cur.fetchone()
                    if base_row is not None:
                        base = IncrementalBase(
                            artifact_bucket=str(base_row[0]),
                            artifact_key=str(base_row[1]),
                            artifact_digest=str(base_row[2]),
                            revision=str(base_row[3]),
                        )

                cur.execute(
                    """
                    UPDATE codegraph_registry
                    SET worker_generation = %s,
                        worker_id = %s,
                        codegraph_version = %s,
                        index_profile = %s,
                        state = 'indexing',
                        ready = FALSE,
                        indexing_started_at = now(),
                        error_detail = NULL,
                        updated_at = now()
                    WHERE id = %s::uuid
                      AND state = 'queued'
                    """,
                    (
                        generation,
                        worker_id,
                        codegraph_version,
                        index_profile,
                        registry_id,
                    ),
                )
                work_items.append(
                    IndexWork(
                        registry_id=registry_id,
                        worker_generation=generation,
                        worker_id=worker_id,
                        source_bucket=str(row[2]),
                        source_object_key=str(row[3]),
                        source_version_id=row[4],
                        project_id=project_id,
                        run_id=row[6],
                        realm=realm,
                        repository=repository,
                        base=base,
                    )
                )
            return work_items

    def mark_index_launch_failed(self, work: IndexWork, error_detail: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_registry
                SET state = 'failed',
                    ready = FALSE,
                    error_detail = %s,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND worker_generation = %s
                """,
                (error_detail[:4000], work.registry_id, work.worker_generation),
            )
            return cur.rowcount == 1

    def complete_index_success(self, result: IndexSuccess) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_registry
                SET indexed_revision = %s,
                    codegraph_version = %s,
                    index_profile = %s,
                    index_mode = %s,
                    base_revision = %s,
                    state_artifact_bucket = %s,
                    state_artifact_key = %s,
                    state_artifact_digest = %s,
                    state_artifact_schema_version = %s,
                    indexing_finished_at = now(),
                    state = 'activating',
                    worker_endpoint = NULL,
                    ready_at = NULL,
                    ready = FALSE,
                    error_detail = NULL,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND worker_generation = %s
                  AND state = 'indexing'
                """,
                (
                    result.indexed_revision,
                    result.codegraph_version,
                    result.index_profile,
                    result.index_mode,
                    result.base_revision,
                    result.state_artifact_bucket,
                    result.state_artifact_key,
                    result.state_artifact_digest,
                    result.state_artifact_schema_version,
                    result.registry_id,
                    result.worker_generation,
                ),
            )
            updated = cur.rowcount == 1
            if updated:
                cur.execute(
                    """
                    INSERT INTO telemetry.codegraph_index (
                      registry_id,
                      worker_generation,
                      project_id,
                      run_id,
                      repository,
                      revision,
                      base_revision,
                      index_mode,
                      codegraph_version,
                      index_profile,
                      duration_ms,
                      ok
                    )
                    SELECT
                      id,
                      worker_generation,
                      project_id,
                      run_id,
                      repository,
                      indexed_revision,
                      base_revision,
                      index_mode,
                      codegraph_version,
                      index_profile,
                      %s,
                      TRUE
                    FROM codegraph_registry
                    WHERE id = %s::uuid
                    """,
                    (result.duration_ms, result.registry_id),
                )
            return updated

    def complete_index_failure(
        self,
        *,
        registry_id: str,
        worker_generation: int,
        failure_state: str,
        error_detail: str,
    ) -> bool:
        if failure_state not in {"failed", "unindexable"}:
            failure_state = "failed"
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_registry
                SET state = %s,
                    ready = FALSE,
                    indexing_finished_at = now(),
                    error_detail = %s,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND worker_generation = %s
                  AND state = 'indexing'
                """,
                (failure_state, error_detail[:4000], registry_id, worker_generation),
            )
            updated = cur.rowcount == 1
            if updated:
                cur.execute(
                    """
                    INSERT INTO telemetry.codegraph_index (
                      registry_id,
                      worker_generation,
                      project_id,
                      run_id,
                      repository,
                      codegraph_version,
                      index_profile,
                      ok,
                      error_detail
                    )
                    SELECT
                      id,
                      worker_generation,
                      project_id,
                      run_id,
                      repository,
                      codegraph_version,
                      index_profile,
                      FALSE,
                      %s
                    FROM codegraph_registry
                    WHERE id = %s::uuid
                    """,
                    (error_detail[:4000], registry_id),
                )
            return updated

    def reserve_activating_serve_work(
        self,
        *,
        limit: int,
        namespace: str,
        port: int = 8094,
    ) -> list[ServeWork]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id::text,
                  worker_generation + 1,
                  source_bucket,
                  source_object_key,
                  source_version_id,
                  project_id,
                  run_id,
                  realm,
                  repository,
                  indexed_revision,
                  codegraph_version,
                  index_profile,
                  state_artifact_bucket,
                  state_artifact_key,
                  state_artifact_digest
                FROM codegraph_registry
                WHERE ready = FALSE
                  AND state = 'activating'
                  AND worker_endpoint IS NULL
                  AND indexed_revision IS NOT NULL
                  AND codegraph_version IS NOT NULL
                  AND index_profile IS NOT NULL
                  AND state_artifact_bucket IS NOT NULL
                  AND state_artifact_key IS NOT NULL
                  AND state_artifact_digest IS NOT NULL
                ORDER BY indexing_finished_at, updated_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            work_items: list[ServeWork] = []
            for row in rows:
                registry_id = str(row[0])
                generation = int(row[1])
                worker_id = f"cg-serve-{registry_id.replace('-', '')[:12]}-g{generation}"
                worker_endpoint = f"http://{worker_id}.{namespace}.svc.cluster.local:{port}"
                cur.execute(
                    """
                    UPDATE codegraph_registry
                    SET worker_generation = %s,
                        worker_id = %s,
                        worker_endpoint = %s,
                        error_detail = NULL,
                        updated_at = now()
                    WHERE id = %s::uuid
                      AND state = 'activating'
                      AND ready = FALSE
                      AND worker_endpoint IS NULL
                    """,
                    (generation, worker_id, worker_endpoint, registry_id),
                )
                if cur.rowcount != 1:
                    continue
                work_items.append(
                    ServeWork(
                        registry_id=registry_id,
                        worker_generation=generation,
                        worker_id=worker_id,
                        worker_endpoint=worker_endpoint,
                        source_bucket=str(row[2]),
                        source_object_key=str(row[3]),
                        source_version_id=row[4],
                        project_id=row[5],
                        run_id=row[6],
                        realm=row[7],
                        repository=row[8],
                        indexed_revision=str(row[9]),
                        codegraph_version=str(row[10]),
                        index_profile=str(row[11]),
                        state_artifact_bucket=str(row[12]),
                        state_artifact_key=str(row[13]),
                        state_artifact_digest=str(row[14]),
                    )
                )
            return work_items

    def mark_serve_launch_failed(self, work: ServeWork, error_detail: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_registry
                SET state = 'failed',
                    ready = FALSE,
                    error_detail = %s,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND worker_generation = %s
                  AND worker_endpoint = %s
                  AND state = 'activating'
                """,
                (
                    error_detail[:4000],
                    work.registry_id,
                    work.worker_generation,
                    work.worker_endpoint,
                ),
            )
            return cur.rowcount == 1

    def complete_serve_success(
        self,
        *,
        registry_id: str,
        worker_generation: int,
        indexed_revision: str,
        worker_endpoint: str,
    ) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_registry
                SET state = 'ready',
                    ready = TRUE,
                    ready_at = COALESCE(ready_at, now()),
                    error_detail = NULL,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND worker_generation = %s
                  AND worker_endpoint = %s
                  AND indexed_revision = %s
                  AND state IN ('activating', 'ready')
                """,
                (
                    registry_id,
                    worker_generation,
                    worker_endpoint,
                    indexed_revision,
                ),
            )
            return cur.rowcount == 1

    def complete_serve_failure(
        self,
        *,
        registry_id: str,
        worker_generation: int,
        worker_endpoint: str,
        error_detail: str,
    ) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_registry
                SET state = 'failed',
                    ready = FALSE,
                    error_detail = %s,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND worker_generation = %s
                  AND worker_endpoint = %s
                  AND state = 'activating'
                """,
                (
                    error_detail[:4000],
                    registry_id,
                    worker_generation,
                    worker_endpoint,
                ),
            )
            return cur.rowcount == 1
