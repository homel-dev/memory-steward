"""AMP agent-facing MCP adapters.

These handlers are transport adapters only. Retrieval remains owned by Memory
Router; outcome admission and feedback remain owned by Memory Steward.
"""

import json
from typing import Any, Optional

import requests
from fastmcp import FastMCP

from memory_steward_mcp.config import MEMORY_ROUTER_URL, STEWARD_URL


def _json_response(response: requests.Response) -> str:
    response.raise_for_status()
    return json.dumps(response.json(), ensure_ascii=False, indent=2)


def register_agent_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="memory.retrieve_context")
    def retrieve_context(
        project_id: str,
        query: Optional[str] = None,
        mode: Optional[str] = None,
        artifact_selectors: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        """Retrieve governed structured context for an agent task."""
        payload: dict[str, Any] = {}
        if query:
            payload["query"] = query
        if mode:
            payload["mode"] = mode
        if artifact_selectors:
            payload["artifact_selectors"] = artifact_selectors
        response = requests.post(
            f"{MEMORY_ROUTER_URL}/v1/context/retrieve",
            headers={"X-Project-ID": project_id},
            json=payload,
            timeout=60,
        )
        return _json_response(response)

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
        admit_knowledge: bool = True,
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
            "admit_knowledge": admit_knowledge,
        }
        response = requests.post(
            f"{STEWARD_URL}/v1/agent/outcomes",
            json=payload,
            timeout=180,
        )
        return _json_response(response)

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
        return _json_response(response)
