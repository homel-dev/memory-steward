from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import psycopg

DEFAULT_BUILD_NOTIFY_CHANNEL = "codegraph_build_work"


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


@dataclass(frozen=True)
class FluxArtifactEvent:
    source_api_version: str
    source_kind: str
    source_namespace: str
    source_name: str
    source_uid: str | None
    artifact_revision: str
    artifact_digest: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class BuildRecord:
    build_id: str
    source_api_version: str
    source_kind: str
    source_namespace: str
    source_name: str
    source_uid: str | None
    artifact_revision: str
    artifact_digest: str
    artifact_url: str | None
    state: str
    workflow_namespace: str | None
    workflow_name: str | None
    workflow_uid: str | None
    generation_bucket: str | None
    generation_key: str | None


@dataclass(frozen=True)
class RecordResult:
    build_id: str
    inserted: bool


@dataclass(frozen=True)
class BuildTelemetrySnapshot:
    counts: dict[str, int]
    last_received_timestamp: float
    last_succeeded_timestamp: float
    oldest_active_age_seconds: float


class CodeGraphBuildStore:
    def __init__(self, dsn: str, *, notify_channel: str = DEFAULT_BUILD_NOTIFY_CHANNEL):
        self._dsn = dsn
        self.notify_channel = notify_channel

    @classmethod
    def from_env(cls, application_name: str = "memory-steward-codegraph-controller") -> "CodeGraphBuildStore":
        return cls(postgres_dsn_from_env(application_name))

    def _connect(self, *, autocommit: bool = False):
        return psycopg.connect(self._dsn, autocommit=autocommit)

    def notification_connection(self):
        return self._connect(autocommit=True)

    def telemetry_snapshot(self) -> BuildTelemetrySnapshot:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT state, count(*) FROM codegraph_builds GROUP BY state")
            counts = {str(state): int(count) for state, count in cur.fetchall()}
            cur.execute(
                """
                SELECT
                  COALESCE(EXTRACT(EPOCH FROM MAX(received_at)), 0),
                  COALESCE(EXTRACT(EPOCH FROM MAX(finished_at) FILTER (WHERE state = 'succeeded')), 0),
                  COALESCE(EXTRACT(EPOCH FROM now() - (
                    MIN(received_at) FILTER (WHERE state IN ('received', 'submitted', 'running'))
                  )), 0)
                FROM codegraph_builds
                """
            )
            received, succeeded, age = cur.fetchone()
        return BuildTelemetrySnapshot(
            counts=counts,
            last_received_timestamp=float(received),
            last_succeeded_timestamp=float(succeeded),
            oldest_active_age_seconds=max(float(age), 0.0),
        )

    @staticmethod
    def _row(row: tuple[Any, ...]) -> BuildRecord:
        return BuildRecord(
            build_id=str(row[0]),
            source_api_version=str(row[1]),
            source_kind=str(row[2]),
            source_namespace=str(row[3]),
            source_name=str(row[4]),
            source_uid=row[5],
            artifact_revision=str(row[6]),
            artifact_digest=str(row[7]),
            artifact_url=row[8],
            state=str(row[9]),
            workflow_namespace=row[10],
            workflow_name=row[11],
            workflow_uid=row[12],
            generation_bucket=row[13],
            generation_key=row[14],
        )

    def record_event(self, event: FluxArtifactEvent) -> RecordResult:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO codegraph_builds (
                  source_api_version,
                  source_kind,
                  source_namespace,
                  source_name,
                  source_uid,
                  artifact_revision,
                  artifact_digest,
                  source_event,
                  state
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'received')
                ON CONFLICT (source_namespace, source_kind, source_name, artifact_digest) DO NOTHING
                RETURNING id::text
                """,
                (
                    event.source_api_version,
                    event.source_kind,
                    event.source_namespace,
                    event.source_name,
                    event.source_uid,
                    event.artifact_revision,
                    event.artifact_digest,
                    json.dumps(event.payload, separators=(",", ":")),
                ),
            )
            row = cur.fetchone()
            if row is not None:
                build_id = str(row[0])
                cur.execute("SELECT pg_notify(%s, %s)", (self.notify_channel, build_id))
                return RecordResult(build_id=build_id, inserted=True)

            cur.execute(
                """
                SELECT id::text
                FROM codegraph_builds
                WHERE source_namespace = %s
                  AND source_kind = %s
                  AND source_name = %s
                  AND artifact_digest = %s
                """,
                (
                    event.source_namespace,
                    event.source_kind,
                    event.source_name,
                    event.artifact_digest,
                ),
            )
            existing = cur.fetchone()
            if existing is None:
                raise RuntimeError("CodeGraph build row disappeared after conflict")
            return RecordResult(build_id=str(existing[0]), inserted=False)

    def successful_generations(self) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT b.id::text, b.generation_bucket, b.generation_key,
                       b.result, b.source_name
                FROM codegraph_builds b
                WHERE b.state = 'succeeded'
                  AND b.generation_bucket IS NOT NULL
                  AND b.generation_key IS NOT NULL
                  AND b.result IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM codegraph_builds newer
                    WHERE newer.source_namespace = b.source_namespace
                      AND newer.source_kind = b.source_kind
                      AND newer.source_name = b.source_name
                      AND newer.state = 'succeeded'
                      AND newer.generation_bucket IS NOT NULL
                      AND newer.generation_key IS NOT NULL
                      AND newer.result IS NOT NULL
                      AND (newer.received_at, newer.id) > (b.received_at, b.id)
                  )
                ORDER BY b.source_namespace, b.source_name
            """)
            return [
                {"build_id": str(row[0]), "generation_bucket": row[1],
                 "generation_key": row[2], "result": row[3],
                 "repository": row[4]}
                for row in cur.fetchall()
            ]

    def activate_serving_alias(self, build: dict[str, Any], endpoint: str) -> bool:
        """Record the READY generation only if it remains the newest Flux event."""
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT build_id::text, worker_endpoint
                FROM codegraph_serving_aliases WHERE repository = %s
            """, (build["repository"],))
            if cur.fetchone() == (build["build_id"], endpoint):
                return True
            cur.execute("""
                INSERT INTO codegraph_serving_aliases (repository, build_id, worker_endpoint)
                SELECT b.source_name, b.id, %s
                FROM codegraph_builds b
                WHERE b.id = %s::uuid AND b.state = 'succeeded'
                  AND NOT EXISTS (
                    SELECT 1 FROM codegraph_builds newer
                    WHERE newer.source_namespace = b.source_namespace
                      AND newer.source_kind = b.source_kind
                      AND newer.source_name = b.source_name
                      AND newer.state = 'succeeded'
                      AND newer.generation_bucket IS NOT NULL
                      AND newer.generation_key IS NOT NULL
                      AND newer.result IS NOT NULL
                      AND (newer.received_at, newer.id) > (b.received_at, b.id)
                  )
                ON CONFLICT (repository) DO UPDATE SET
                    build_id = EXCLUDED.build_id,
                    worker_endpoint = EXCLUDED.worker_endpoint,
                    updated_at = now()
                RETURNING repository
            """, (endpoint, build["build_id"]))
            return cur.fetchone() is not None

    def retired_serving_build_ids(self, *, grace_seconds: int = 120) -> list[str]:
        """Select superseded serving generations without active pinned readers."""
        if grace_seconds < 0:
            raise ValueError("grace_seconds must be non-negative")
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT old.id::text
                FROM codegraph_serving_aliases a
                JOIN codegraph_builds live ON live.id = a.build_id
                JOIN codegraph_builds old
                  ON old.source_namespace = live.source_namespace
                 AND old.source_kind = live.source_kind
                 AND old.source_name = live.source_name
                WHERE old.state = 'succeeded'
                  AND (old.received_at, old.id) < (live.received_at, live.id)
                  AND a.updated_at < now() - (%s * interval '1 second')
                  AND NOT EXISTS (
                    SELECT 1 FROM capability_sessions session
                    JOIN codegraph_registry registry
                      ON registry.id = session.codegraph_registry_id
                    WHERE session.status = 'active'
                      AND session.expires_at > now()
                      AND session.revision <> 'latest'
                      AND registry.worker_id =
                          'cg-serve-' || replace(old.id::text, '-', '')
                  )
                ORDER BY old.source_namespace, old.source_name, old.received_at
            """, (grace_seconds,))
            return [str(row[0]) for row in cur.fetchall()]

    def pending(self, *, limit: int) -> list[BuildRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id::text, source_api_version, source_kind, source_namespace, source_name,
                  source_uid, artifact_revision, artifact_digest, artifact_url, state,
                  workflow_namespace, workflow_name, workflow_uid, generation_bucket, generation_key
                FROM codegraph_builds
                WHERE state = 'received'
                ORDER BY received_at, id
                LIMIT %s
                """,
                (limit,),
            )
            return [self._row(row) for row in cur.fetchall()]

    def active(self, *, limit: int) -> list[BuildRecord]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  id::text, source_api_version, source_kind, source_namespace, source_name,
                  source_uid, artifact_revision, artifact_digest, artifact_url, state,
                  workflow_namespace, workflow_name, workflow_uid, generation_bucket, generation_key
                FROM codegraph_builds
                WHERE state IN ('submitted', 'running')
                ORDER BY submitted_at, id
                LIMIT %s
                """,
                (limit,),
            )
            return [self._row(row) for row in cur.fetchall()]

    def mark_superseded(self, build_id: str, detail: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_builds
                SET state = 'superseded',
                    error_detail = %s,
                    finished_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid
                  AND state = 'received'
                """,
                (detail[:4000], build_id),
            )
            return cur.rowcount == 1

    def mark_submitted(
        self,
        *,
        build_id: str,
        artifact_url: str,
        workflow_namespace: str,
        workflow_name: str,
        workflow_uid: str | None,
        generation_bucket: str,
        generation_key: str,
    ) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_builds
                SET artifact_url = %s,
                    workflow_namespace = %s,
                    workflow_name = %s,
                    workflow_uid = %s,
                    generation_bucket = %s,
                    generation_key = %s,
                    state = 'submitted',
                    submitted_at = COALESCE(submitted_at, now()),
                    error_detail = NULL,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND state = 'received'
                """,
                (
                    artifact_url,
                    workflow_namespace,
                    workflow_name,
                    workflow_uid,
                    generation_bucket,
                    generation_key,
                    build_id,
                ),
            )
            return cur.rowcount == 1

    def mark_running(self, build_id: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_builds
                SET state = 'running',
                    started_at = COALESCE(started_at, now()),
                    updated_at = now()
                WHERE id = %s::uuid
                  AND state = 'submitted'
                """,
                (build_id,),
            )
            return cur.rowcount == 1

    def complete_success(self, *, build_id: str, result: dict[str, Any]) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_builds
                SET state = 'succeeded',
                    generation_digest = %s,
                    generation_schema_version = %s,
                    result = %s::jsonb,
                    error_detail = NULL,
                    finished_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid
                  AND state IN ('submitted', 'running')
                """,
                (
                    str(result["generation_digest"]),
                    int(result["generation_schema_version"]),
                    json.dumps(result, separators=(",", ":")),
                    build_id,
                ),
            )
            return cur.rowcount == 1

    def complete_failure(self, *, build_id: str, detail: str) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE codegraph_builds
                SET state = 'failed',
                    error_detail = %s,
                    finished_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid
                  AND state IN ('received', 'submitted', 'running')
                """,
                (detail[:4000], build_id),
            )
            return cur.rowcount == 1
