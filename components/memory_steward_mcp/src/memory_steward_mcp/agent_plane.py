"""AMP agent-facing MCP adapters.

These handlers are transport adapters only. Retrieval remains owned by Memory
Router; outcome admission and feedback remain owned by Memory Steward.
"""

import json
import logging
from typing import Any, Optional

import requests
from fastmcp import FastMCP
from fastmcp.server.context import request_ctx

from memory_steward_mcp.config import MEMORY_ROUTER_URL, STEWARD_URL
from memory_steward_mcp.metrics import observe as observe_tool, started as metric_started

log = logging.getLogger("memory-steward-mcp.agent")


def _json_response(response: requests.Response) -> str:
    response.raise_for_status()
    return json.dumps(response.json(), ensure_ascii=False, indent=2)


def _request_metadata() -> dict[str, str]:
    try:
        context = request_ctx.get()
    except (LookupError, RuntimeError):
        return {}
    request = getattr(context, "request", None)
    headers = getattr(request, "headers", None)
    if headers is None:
        return {}
    names = {
        "x-request-id": "transport_request_id",
        "x-run-id": "run_id",
        "x-objective-id": "objective_id",
        "x-agent-role": "agent_role",
    }
    return {field: value for header, field in names.items() if (value := headers.get(header))}


def _backend_request_id(result: str) -> str | None:
    try:
        payload = json.loads(result)
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get("context_request_id") or payload.get("request_id")
    return value if isinstance(value, str) else None


def _finish_tool_log(
    *,
    tool: str,
    project_id: str,
    outcome: str,
    started_at: float,
    query: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    duration_ms = observe_tool(tool, outcome, started_at)
    event: dict[str, Any] = {
        "event": "memory_steward.mcp_tool",
        "tool": tool,
        "project_id": project_id,
        "outcome": outcome,
        "duration_ms": duration_ms,
    }
    if query is not None:
        event["query"] = query[:512]
    event.update(_request_metadata())
    if extra:
        event.update(extra)
    log.info("%s", json.dumps(event, ensure_ascii=False, sort_keys=True))


def register_agent_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="memory.retrieve_context")
    def retrieve_context(
        project_id: str,
        query: Optional[str] = None,
        mode: Optional[str] = None,
        artifact_selectors: Optional[list[dict[str, Any]]] = None,
        reference_filters: Optional[dict[str, str]] = None,
    ) -> str:
        """Retrieve governed structured context for an agent task."""
        payload: dict[str, Any] = {}
        if query:
            payload["query"] = query
        if mode:
            payload["mode"] = mode
        if artifact_selectors:
            payload["artifact_selectors"] = artifact_selectors
        if reference_filters is not None:
            payload["reference_filters"] = reference_filters
        started_at = metric_started()
        try:
            response = requests.post(
                f"{MEMORY_ROUTER_URL}/v1/context/retrieve",
                headers={"X-Project-ID": project_id},
                json=payload,
                timeout=60,
            )
            result = _json_response(response)
        except Exception:
            _finish_tool_log(
                tool="memory.retrieve_context",
                project_id=project_id,
                outcome="error",
                started_at=started_at,
                query=query,
            )
            raise
        _finish_tool_log(
            tool="memory.retrieve_context",
            project_id=project_id,
            outcome="ok",
            started_at=started_at,
            query=query,
            extra={"reference_filters": reference_filters or {}, "backend_request_id": _backend_request_id(result)},
        )
        return result

    @mcp.tool(name="memory.reference.search")
    def reference_search(
        project_id: str,
        query: str,
        reference_filters: Optional[dict[str, str]] = None,
        limit: int = 8,
    ) -> str:
        """Search read-only canonical Reference Memory for an agent task."""
        payload: dict[str, Any] = {"query": query, "limit": limit}
        if reference_filters is not None:
            payload["reference_filters"] = reference_filters
        started_at = metric_started()
        try:
            response = requests.post(
                f"{MEMORY_ROUTER_URL}/v1/reference/search",
                headers={"X-Project-ID": project_id},
                json=payload,
                timeout=60,
            )
            result = _json_response(response)
        except Exception:
            _finish_tool_log(
                tool="memory.reference.search",
                project_id=project_id,
                outcome="error",
                started_at=started_at,
                query=query,
            )
            raise
        _finish_tool_log(
            tool="memory.reference.search",
            project_id=project_id,
            outcome="ok",
            started_at=started_at,
            query=query,
            extra={"reference_filters": reference_filters or {}, "limit": limit, "backend_request_id": _backend_request_id(result)},
        )
        return result

    @mcp.tool(name="memory.reference.get")
    def reference_get(project_id: str, chunk_id: str) -> str:
        """Fetch one full Reference Memory chunk by stable chunk id."""
        started_at = metric_started()
        try:
            response = requests.get(
                f"{MEMORY_ROUTER_URL}/v1/reference/{chunk_id}",
                headers={"X-Project-ID": project_id},
                timeout=30,
            )
            result = _json_response(response)
        except Exception:
            _finish_tool_log(
                tool="memory.reference.get",
                project_id=project_id,
                outcome="error",
                started_at=started_at,
            )
            raise
        _finish_tool_log(
            tool="memory.reference.get",
            project_id=project_id,
            outcome="ok",
            started_at=started_at,
            extra={"chunk_id": chunk_id, "backend_request_id": _backend_request_id(result)},
        )
        return result

    @mcp.tool(name="memory.submit_agent_outcome")
    def submit_agent_outcome(
        project_id: str,
        outcome_id: str,
        objective: str,
        result: Any,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        context_request_id: Optional[str] = None,
        decisions: Optional[list[Any]] = None,
        findings: Optional[list[Any]] = None,
        verification: Optional[dict[str, Any]] = None,
        artifacts: Optional[list[dict[str, Any]]] = None,
        repository_state: Optional[dict[str, Any]] = None,
        evidence: Optional[list[Any]] = None,
        scope: Optional[str] = None,
        admit_knowledge: bool = False,
    ) -> str:
        """Submit structured agent execution evidence for governed admission."""
        payload = {
            "project_id": project_id,
            "outcome_id": outcome_id,
            "task_id": task_id,
            "session_id": session_id,
            "context_request_id": context_request_id,
            "objective": objective,
            "result": result,
            "decisions": decisions or [],
            "findings": findings or [],
            "verification": verification or {},
            "artifacts": artifacts or [],
            "repository_state": repository_state or {},
            "evidence": evidence or [],
            "scope": scope,
            "admit_knowledge": False,
        }
        started_at = metric_started()
        try:
            response = requests.post(
                f"{STEWARD_URL}/v1/agent/outcomes",
                json=payload,
                timeout=180,
            )
            output = _json_response(response)
        except Exception:
            _finish_tool_log(
                tool="memory.submit_agent_outcome",
                project_id=project_id,
                outcome="error",
                started_at=started_at,
            )
            raise
        _finish_tool_log(
            tool="memory.submit_agent_outcome",
            project_id=project_id,
            outcome="ok",
            started_at=started_at,
            extra={"outcome_id": outcome_id},
        )
        return output

    @mcp.tool(name="memory.submit_context_feedback")
    def submit_context_feedback(
        project_id: str,
        context_request_id: str,
        used_memory_ids: Optional[list[str]] = None,
        irrelevant_memory_ids: Optional[list[str]] = None,
        missing_context: Optional[str] = None,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        feedback_id: Optional[str] = None,
    ) -> str:
        """Report retrieval quality; this operation never mutates memory directly."""
        started_at = metric_started()
        try:
            response = requests.post(
                f"{STEWARD_URL}/v1/context/feedback",
                json={
                    "project_id": project_id,
                    "context_request_id": context_request_id,
                    "feedback_id": feedback_id,
                    "task_id": task_id,
                    "session_id": session_id,
                    "used_memory_ids": used_memory_ids or [],
                    "irrelevant_memory_ids": irrelevant_memory_ids or [],
                    "missing_context": missing_context,
                },
                timeout=30,
            )
            output = _json_response(response)
        except Exception:
            _finish_tool_log(
                tool="memory.submit_context_feedback",
                project_id=project_id,
                outcome="error",
                started_at=started_at,
            )
            raise
        _finish_tool_log(
            tool="memory.submit_context_feedback",
            project_id=project_id,
            outcome="ok",
            started_at=started_at,
            extra={"context_request_id": context_request_id},
        )
        return output
