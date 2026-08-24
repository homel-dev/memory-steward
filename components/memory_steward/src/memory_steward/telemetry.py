# memory_steward/telemetry.py
import logging
from typing import Optional
from datetime import datetime, timezone

import psycopg

log = logging.getLogger("memory-steward.telemetry")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class StewardTelemetryWriter:
    """
    Postgres-backed telemetry writer (best-effort; must never break admission flow).

    Table used by Steward: telemetry.admission
    """

    def __init__(self, dsn: str):
        self._dsn = dsn

    def _pg(self):
        return psycopg.connect(self._dsn)

    def admission_write(
        self,
        *,
        request_id: str,
        project_id: str,
        fragments_extracted: int,
        fragments_inserted: int,
        qdrant_upserts: int,
        ok: bool,
        error_detail: Optional[str],
    ) -> None:
        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry.admission (
                      request_id,
                      project_id,
                      t_begin,
                      fragments_extracted,
                      fragments_inserted,
                      qdrant_upserts,
                      ok,
                      error_detail
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (request_id) DO UPDATE SET
                      project_id = EXCLUDED.project_id,
                      fragments_extracted = EXCLUDED.fragments_extracted,
                      fragments_inserted = EXCLUDED.fragments_inserted,
                      qdrant_upserts = EXCLUDED.qdrant_upserts,
                      ok = EXCLUDED.ok,
                      error_detail = EXCLUDED.error_detail
                    """,
                    (
                        request_id,
                        project_id,
                        _utcnow(),
                        fragments_extracted,
                        fragments_inserted,
                        qdrant_upserts,
                        ok,
                        error_detail,
                    ),
                )
        except Exception as e:
            log.warning("telemetry.admission_write failed: %s", e)
    def agent_outcome_write(
        self,
        *,
        outcome_id: str,
        project_id: str,
        context_request_id: Optional[str],
        fragments_extracted: int,
        fragments_inserted: int,
        artifacts_received: int,
        artifacts_inserted: int,
        qdrant_upserts: int,
        idempotent_replay: bool,
        ok: bool,
        error_detail: Optional[str],
    ) -> None:
        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry.agent_outcome (
                      outcome_id, project_id, context_request_id,
                      fragments_extracted, fragments_inserted,
                      artifacts_received, artifacts_inserted, qdrant_upserts,
                      idempotent_replay, ok, error_detail
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        outcome_id, project_id, context_request_id,
                        fragments_extracted, fragments_inserted,
                        artifacts_received, artifacts_inserted, qdrant_upserts,
                        idempotent_replay, ok, error_detail,
                    ),
                )
        except Exception as e:
            log.warning("telemetry.agent_outcome_write failed: %s", e)

    def context_feedback_write(
        self,
        *,
        feedback_id: str,
        context_request_id: str,
        project_id: str,
        used_count: int,
        irrelevant_count: int,
        missing_context_reported: bool,
    ) -> None:
        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry.context_feedback (
                      feedback_id, context_request_id, project_id,
                      used_count, irrelevant_count, missing_context_reported
                    )
                    VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (feedback_id) DO NOTHING
                    """,
                    (
                        feedback_id, context_request_id, project_id,
                        used_count, irrelevant_count, missing_context_reported,
                    ),
                )
        except Exception as e:
            log.warning("telemetry.context_feedback_write failed: %s", e)

