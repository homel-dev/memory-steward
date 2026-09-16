"""Durable Postgres queue primitives for large reference ingestion."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row

from memory_steward_mcp.config import POSTGRES_DSN


def enqueue_url_job(*, url: str, product: str, version: str, scope: str) -> str:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO reference_ingestion_jobs (url, product, version, scope)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (url, product, version, scope),
        )
        row = cur.fetchone()
        assert row is not None
        return str(row[0])


def get_job(job_id: str) -> dict[str, Any] | None:
    with psycopg.connect(POSTGRES_DSN, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM reference_ingestion_jobs WHERE id = %s",
            (job_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_jobs(*, limit: int = 20) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 200))
    with psycopg.connect(POSTGRES_DSN, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT *
            FROM reference_ingestion_jobs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (safe_limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def requeue_stale_jobs(*, lease_seconds: int) -> int:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reference_ingestion_jobs
            SET status = CASE WHEN cancel_requested THEN 'cancelled' ELSE 'queued' END,
                worker_id = NULL,
                heartbeat_at = NULL,
                finished_at = CASE WHEN cancel_requested THEN now() ELSE NULL END,
                updated_at = now(),
                error = CASE
                    WHEN cancel_requested THEN 'cancelled after worker lease expired'
                    ELSE 'worker lease expired; requeued'
                END
            WHERE status = 'running'
              AND heartbeat_at < now() - (%s * interval '1 second')
            """,
            (lease_seconds,),
        )
        return cur.rowcount


def claim_next_job(*, worker_id: str) -> dict[str, Any] | None:
    with psycopg.connect(POSTGRES_DSN, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            WITH candidate AS (
                SELECT id
                FROM reference_ingestion_jobs
                WHERE status = 'queued'
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE reference_ingestion_jobs AS jobs
            SET status = 'running',
                worker_id = %s,
                attempt_count = jobs.attempt_count + 1,
                started_at = now(),
                heartbeat_at = now(),
                finished_at = NULL,
                error = NULL,
                updated_at = now()
            FROM candidate
            WHERE jobs.id = candidate.id
            RETURNING jobs.*
            """,
            (worker_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _owned_update(
    *,
    job_id: str,
    worker_id: str,
    attempt_count: int,
    assignments: str,
    params: tuple[Any, ...],
) -> bool:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE reference_ingestion_jobs
            SET {assignments}, updated_at = now()
            WHERE id = %s
              AND status = 'running'
              AND worker_id = %s
              AND attempt_count = %s
            """,
            (*params, job_id, worker_id, attempt_count),
        )
        return cur.rowcount == 1


def update_progress(
    *,
    job_id: str,
    worker_id: str,
    attempt_count: int,
    chunk_count: int,
    processed_chunks: int,
    upserted_count: int,
) -> bool:
    return _owned_update(
        job_id=job_id,
        worker_id=worker_id,
        attempt_count=attempt_count,
        assignments=(
            "chunk_count = %s, processed_chunks = %s, upserted_count = %s, heartbeat_at = now()"
        ),
        params=(chunk_count, processed_chunks, upserted_count),
    )


def cancel_requested(*, job_id: str, worker_id: str, attempt_count: int) -> bool:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT cancel_requested
            FROM reference_ingestion_jobs
            WHERE id = %s
              AND status = 'running'
              AND worker_id = %s
              AND attempt_count = %s
            """,
            (job_id, worker_id, attempt_count),
        )
        row = cur.fetchone()
        if row is None:
            return True
        return bool(row[0])


def finish_job(
    *,
    job_id: str,
    worker_id: str,
    attempt_count: int,
    status: str,
    chunk_count: int,
    processed_chunks: int,
    upserted_count: int,
    error: str | None = None,
) -> bool:
    if status not in {"succeeded", "failed", "cancelled"}:
        raise ValueError(f"invalid final status: {status}")
    return _owned_update(
        job_id=job_id,
        worker_id=worker_id,
        attempt_count=attempt_count,
        assignments=(
            "status = %s, chunk_count = %s, processed_chunks = %s, "
            "upserted_count = %s, error = %s, heartbeat_at = now(), finished_at = now()"
        ),
        params=(status, chunk_count, processed_chunks, upserted_count, error),
    )


def request_cancel(job_id: str) -> str:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reference_ingestion_jobs
            SET status = CASE WHEN status = 'queued' THEN 'cancelled' ELSE status END,
                cancel_requested = CASE WHEN status = 'running' THEN TRUE ELSE cancel_requested END,
                finished_at = CASE WHEN status = 'queued' THEN now() ELSE finished_at END,
                updated_at = now()
            WHERE id = %s
              AND status IN ('queued', 'running')
            RETURNING status
            """,
            (job_id,),
        )
        row = cur.fetchone()
        if row is None:
            return "not-active"
        return str(row[0])


def retry_job(job_id: str) -> bool:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reference_ingestion_jobs
            SET status = 'queued',
                worker_id = NULL,
                cancel_requested = FALSE,
                chunk_count = 0,
                processed_chunks = 0,
                upserted_count = 0,
                error = NULL,
                started_at = NULL,
                heartbeat_at = NULL,
                finished_at = NULL,
                updated_at = now()
            WHERE id = %s
              AND status IN ('failed', 'cancelled')
            """,
            (job_id,),
        )
        return cur.rowcount == 1


def release_job(*, job_id: str, worker_id: str, attempt_count: int) -> bool:
    """Return an owned running job to the queue during graceful worker shutdown."""
    return _owned_update(
        job_id=job_id,
        worker_id=worker_id,
        attempt_count=attempt_count,
        assignments="status = 'queued', worker_id = NULL, heartbeat_at = NULL",
        params=(),
    )


def finish_success_with_provenance(
    *,
    job_id: str,
    worker_id: str,
    attempt_count: int,
    product: str,
    version: str,
    scope: str,
    source_url: str,
    chunk_count: int,
    processed_chunks: int,
    upserted_count: int,
) -> bool:
    """Fence the worker and atomically persist job success plus provenance."""
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE reference_ingestion_jobs
            SET status = 'succeeded',
                chunk_count = %s,
                processed_chunks = %s,
                upserted_count = %s,
                error = NULL,
                heartbeat_at = now(),
                finished_at = now(),
                updated_at = now()
            WHERE id = %s
              AND status = 'running'
              AND worker_id = %s
              AND attempt_count = %s
            """,
            (
                chunk_count,
                processed_chunks,
                upserted_count,
                job_id,
                worker_id,
                attempt_count,
            ),
        )
        if cur.rowcount != 1:
            return False
        cur.execute(
            """
            INSERT INTO reference_ingestion
                (product, version, scope, source_url, chunk_count, upserted_count, ingested_at)
            VALUES (%s, %s, %s, %s, %s, %s, now())
            """,
            (product, version, scope, source_url, chunk_count, upserted_count),
        )
        return True
