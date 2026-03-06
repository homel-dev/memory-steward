# memory_router/telemetry.py
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import psycopg


log = logging.getLogger("memory-router.telemetry")

# ------------------------------------------------------------------------------
# Canonical telemetry schema alignment (docs/06_telemetry.md)
#
# telemetry.request
#   - request_id (PK), project_id
#   - t_begin/t_end
#   - origin/origin_hash/model_requested/model_sent_to_builder/decided_mode
#   - http_status/error_kind/error_detail (truncated)
#   - token accounting/budgeting fields
#
# telemetry.step
#   - id (PK), request_id (FK), project_id, name
#   - t_begin/t_end/duration_ms
#   - ok/http_status/error_detail/extra_json
#
# telemetry.retrieval
#   - request_id (PK/FK), project_id
#   - dense_candidates/selected_topk/context_tokens_est
#   - dropped_budget/dropped_no_content/dropped_other
#
# Best-effort semantics: telemetry must never break request flow.
# ------------------------------------------------------------------------------

_DEFAULT_CONNECT_TIMEOUT_SECONDS = 1
_DEFAULT_ERROR_DETAIL_MAXLEN = 1024


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _trunc(s: Optional[str], max_len: int = _DEFAULT_ERROR_DETAIL_MAXLEN) -> Optional[str]:
    if s is None:
        return None
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


@dataclass(frozen=True)
class StepHandle:
    request_id: str
    project_id: str
    name: str
    t_begin: datetime
    step_id: Optional[int]  # telemetry.step.id (None if begin insert failed)


class TelemetryWriter:
    """Postgres-backed telemetry writer (best-effort; must never break request flow)."""

    def __init__(self, dsn: str, *, connect_timeout_seconds: int = _DEFAULT_CONNECT_TIMEOUT_SECONDS):
        self._dsn = dsn
        self._connect_timeout_seconds = connect_timeout_seconds

    def _pg(self):
        # psycopg3 connect_timeout is in seconds
        return psycopg.connect(self._dsn, connect_timeout=self._connect_timeout_seconds)

    # --------------------------------------------------------------------------
    # telemetry.request
    # --------------------------------------------------------------------------

    def request_begin(
        self,
        *,
        request_id: str,
        project_id: str,
        origin: Optional[str] = None,
        origin_hash: Optional[str] = None,
        model_requested: Optional[str] = None,
        decided_mode: Optional[str] = None,
        context_budget_max: Optional[int] = None,
        static_tokens_est: Optional[int] = None,
        dynamic_tokens_est: Optional[int] = None,
    ) -> None:
        t_begin = _utcnow()
        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry.request (
                      request_id,
                      project_id,
                      t_begin,
                      origin,
                      origin_hash,
                      model_requested,
                      decided_mode,
                      context_budget_max,
                      static_tokens_est,
                      dynamic_tokens_est
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (request_id) DO NOTHING
                    """,
                    (
                        request_id,
                        project_id,
                        t_begin,
                        origin,
                        origin_hash,
                        model_requested,
                        decided_mode,
                        context_budget_max,
                        static_tokens_est,
                        dynamic_tokens_est,
                    ),
                )
        except Exception as e:
            log.warning("telemetry.request_begin failed: %s", e)

    def request_end(
        self,
        *,
        request_id: str,
        http_status: Optional[int] = None,
        error_kind: Optional[str] = None,
        error_detail: Optional[str] = None,
        model_sent_to_builder: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        context_budget_max: Optional[int] = None,
        static_tokens_est: Optional[int] = None,
        dynamic_tokens_est: Optional[int] = None,
    ) -> None:
        t_end = _utcnow()
        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE telemetry.request
                    SET
                      t_end                 = %s,
                      http_status           = COALESCE(%s, http_status),
                      error_kind            = COALESCE(%s, error_kind),
                      error_detail          = COALESCE(%s, error_detail),
                      model_sent_to_builder = COALESCE(%s, model_sent_to_builder),
                      prompt_tokens         = COALESCE(%s, prompt_tokens),
                      completion_tokens     = COALESCE(%s, completion_tokens),
                      total_tokens          = COALESCE(%s, total_tokens),
                      context_budget_max    = COALESCE(%s, context_budget_max),
                      static_tokens_est     = COALESCE(%s, static_tokens_est),
                      dynamic_tokens_est    = COALESCE(%s, dynamic_tokens_est)
                    WHERE request_id = %s
                    """,
                    (
                        t_end,
                        http_status,
                        error_kind,
                        _trunc(error_detail),
                        model_sent_to_builder,
                        prompt_tokens,
                        completion_tokens,
                        total_tokens,
                        context_budget_max,
                        static_tokens_est,
                        dynamic_tokens_est,
                        request_id,
                    ),
                )
        except Exception as e:
            log.warning("telemetry.request_end failed: %s", e)

    # --------------------------------------------------------------------------
    # telemetry.step
    # --------------------------------------------------------------------------

    def step_begin(
        self,
        *,
        request_id: str,
        project_id: str,
        name: str,
        extra_json: Optional[Dict[str, Any]] = None,
    ) -> StepHandle:
        t_begin = _utcnow()
        step_id: Optional[int] = None

        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry.step (
                      request_id,
                      project_id,
                      name,
                      t_begin,
                      extra_json
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        request_id,
                        project_id,
                        name,
                        t_begin,
                        psycopg.types.json.Json(extra_json or {}),
                    ),
                )
                row = cur.fetchone()
                if row:
                    step_id = int(row[0])
        except Exception as e:
            log.warning("telemetry.step_begin failed: %s", e)

        return StepHandle(
            request_id=request_id,
            project_id=project_id,
            name=name,
            t_begin=t_begin,
            step_id=step_id,
        )

    def step_end(
        self,
        *,
        handle: StepHandle,
        ok: bool,
        http_status: Optional[int] = None,
        error_detail: Optional[str] = None,
        extra_json: Optional[Dict[str, Any]] = None,
    ) -> None:
        if handle.step_id is None:
            return

        t_end = _utcnow()
        duration_ms = int((t_end - handle.t_begin).total_seconds() * 1000)

        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE telemetry.step
                    SET
                      t_end        = %s,
                      duration_ms  = %s,
                      ok           = %s,
                      http_status  = COALESCE(%s, http_status),
                      error_detail = COALESCE(%s, error_detail),
                      extra_json   = COALESCE(%s::jsonb, extra_json)
                    WHERE id = %s
                    """,
                    (
                        t_end,
                        duration_ms,
                        ok,
                        http_status,
                        _trunc(error_detail),
                        psycopg.types.json.Json(extra_json) if extra_json is not None else None,
                        handle.step_id,
                    ),
                )
        except Exception as e:
            log.warning("telemetry.step_end failed: %s", e)

    @contextmanager
    def step(
        self,
        *,
        request_id: str,
        project_id: str,
        name: str,
        extra_json: Optional[Dict[str, Any]] = None,
    ):
        h = self.step_begin(request_id=request_id, project_id=project_id, name=name, extra_json=extra_json)
        try:
            yield h
            self.step_end(handle=h, ok=True)
        except Exception as e:
            self.step_end(handle=h, ok=False, error_detail=str(e))
            raise

    # --------------------------------------------------------------------------
    # telemetry.retrieval
    # --------------------------------------------------------------------------

    def retrieval_write(
        self,
        *,
        request_id: str,
        project_id: str,
        dense_candidates: int,
        selected_topk: int,
        context_tokens_est: int,
        dropped_budget: int = 0,
        dropped_no_content: int = 0,
        dropped_other: int = 0,
    ) -> None:
        try:
            with self._pg() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO telemetry.retrieval (
                      request_id,
                      project_id,
                      dense_candidates,
                      selected_topk,
                      context_tokens_est,
                      dropped_budget,
                      dropped_no_content,
                      dropped_other
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (request_id) DO UPDATE SET
                      project_id         = EXCLUDED.project_id,
                      dense_candidates   = EXCLUDED.dense_candidates,
                      selected_topk      = EXCLUDED.selected_topk,
                      context_tokens_est = EXCLUDED.context_tokens_est,
                      dropped_budget     = EXCLUDED.dropped_budget,
                      dropped_no_content = EXCLUDED.dropped_no_content,
                      dropped_other      = EXCLUDED.dropped_other
                    """,
                    (
                        request_id,
                        project_id,
                        dense_candidates,
                        selected_topk,
                        context_tokens_est,
                        dropped_budget,
                        dropped_no_content,
                        dropped_other,
                    ),
                )
        except Exception as e:
            log.warning("telemetry.retrieval_write failed: %s", e)

