"""Background worker for durable, bounded reference URL ingestion."""

from __future__ import annotations

import logging
import os
import signal
import socket
import time
from threading import Event

from qdrant_client import QdrantClient

from memory_steward_mcp.config import QDRANT_URL
from memory_steward_mcp.content_plane import IngestionCancelled, _fetch_url, _ingest_reference_content
from memory_steward_mcp.ingest_jobs import (
    cancel_requested,
    claim_next_job,
    finish_job,
    finish_success_with_provenance,
    get_job,
    release_job,
    requeue_stale_jobs,
    update_progress,
)

log = logging.getLogger("memory-steward-mcp.ingest-worker")
POLL_SECONDS = float(os.environ.get("REFERENCE_INGEST_POLL_SECONDS", "2"))
LEASE_SECONDS = int(os.environ.get("REFERENCE_INGEST_LEASE_SECONDS", "300"))
WORKER_ID = os.environ.get("REFERENCE_INGEST_WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"

stop_event = Event()


class WorkerStopping(RuntimeError):
    """Raised after a safe batch boundary during graceful shutdown."""


def _handle_signal(signum, _frame) -> None:
    log.info("received signal %s; stopping after current safe batch", signum)
    stop_event.set()


def _process_job(qdrant: QdrantClient, job: dict) -> None:
    job_id = str(job["id"])
    attempt_count = int(job["attempt_count"])
    product = str(job["product"])
    version = str(job["version"])
    scope = str(job["scope"])
    url = str(job["url"])

    log.info(
        "starting reference ingestion job=%s attempt=%s product=%s version=%s url=%s",
        job_id,
        attempt_count,
        product,
        version,
        url,
    )

    if stop_event.is_set():
        release_job(job_id=job_id, worker_id=WORKER_ID, attempt_count=attempt_count)
        return

    text = _fetch_url(url)

    def progress(total: int, processed: int, upserted: int) -> None:
        owned = update_progress(
            job_id=job_id,
            worker_id=WORKER_ID,
            attempt_count=attempt_count,
            chunk_count=total,
            processed_chunks=processed,
            upserted_count=upserted,
        )
        if not owned:
            raise RuntimeError("ingestion lease ownership lost")
        if stop_event.is_set():
            raise WorkerStopping("worker shutdown requested")

    def cancelled() -> bool:
        return cancel_requested(
            job_id=job_id,
            worker_id=WORKER_ID,
            attempt_count=attempt_count,
        )

    stats = _ingest_reference_content(
        qdrant,
        text=text,
        product=product,
        version=version,
        scope=scope,
        source_url=url,
        progress_fn=progress,
        cancel_fn=cancelled,
        record_provenance=False,
    )

    if not finish_success_with_provenance(
        job_id=job_id,
        worker_id=WORKER_ID,
        attempt_count=attempt_count,
        product=product,
        version=version,
        scope=scope,
        source_url=url,
        chunk_count=stats["chunk_count"],
        processed_chunks=stats["processed_chunks"],
        upserted_count=stats["upserted_count"],
    ):
        raise RuntimeError("ingestion lease ownership lost before completion")

    log.info(
        "completed reference ingestion job=%s chunks=%s",
        job_id,
        stats["upserted_count"],
    )


def run() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    qdrant = QdrantClient(QDRANT_URL, timeout=30)
    last_requeue = 0.0

    while not stop_event.is_set():
        now = time.monotonic()
        try:
            if now - last_requeue >= max(10.0, LEASE_SECONDS / 2):
                count = requeue_stale_jobs(lease_seconds=LEASE_SECONDS)
                if count:
                    log.warning("requeued %s stale reference ingestion job(s)", count)
                last_requeue = now

            job = claim_next_job(worker_id=WORKER_ID)
        except Exception as exc:
            log.warning("reference ingestion queue unavailable: %s", exc)
            stop_event.wait(POLL_SECONDS)
            continue

        if job is None:
            stop_event.wait(POLL_SECONDS)
            continue

        job_id = str(job["id"])
        attempt_count = int(job["attempt_count"])
        try:
            _process_job(qdrant, job)
        except WorkerStopping:
            release_job(job_id=job_id, worker_id=WORKER_ID, attempt_count=attempt_count)
        except IngestionCancelled as exc:
            current = get_job(job_id) or job
            finish_job(
                job_id=job_id,
                worker_id=WORKER_ID,
                attempt_count=attempt_count,
                status="cancelled",
                chunk_count=int(current.get("chunk_count") or 0),
                processed_chunks=int(current.get("processed_chunks") or 0),
                upserted_count=int(current.get("upserted_count") or 0),
                error=str(exc),
            )
        except Exception as exc:
            log.exception("reference ingestion job failed job=%s", job_id)
            current = get_job(job_id) or job
            finish_job(
                job_id=job_id,
                worker_id=WORKER_ID,
                attempt_count=attempt_count,
                status="failed",
                chunk_count=int(current.get("chunk_count") or 0),
                processed_chunks=int(current.get("processed_chunks") or 0),
                upserted_count=int(current.get("upserted_count") or 0),
                error=str(exc)[:4000],
            )


if __name__ == "__main__":
    run()
