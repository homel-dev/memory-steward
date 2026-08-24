import json
import sys
import types
from unittest.mock import MagicMock, patch

fastmcp = types.ModuleType("fastmcp")
fastmcp.FastMCP = object
sys.modules.setdefault("fastmcp", fastmcp)

from memory_steward_mcp.agent_plane import register_agent_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, name=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn
        return decorator


def _response(payload):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = payload
    return resp


def test_retrieve_context_is_thin_router_adapter():
    mcp = FakeMCP()
    register_agent_tools(mcp)
    with patch("memory_steward_mcp.agent_plane.requests.post", return_value=_response({"ok": True})) as post:
        result = mcp.tools["memory.retrieve_context"](
            "rr",
            "inspect repo",
            "engineering",
            [{"artifact_type": "repository_ir", "repository": "rr", "revision": "abc"}],
        )
    assert json.loads(result) == {"ok": True}
    assert post.call_args.args[0].endswith("/v1/context/retrieve")
    assert post.call_args.kwargs["headers"] == {"X-Project-ID": "rr"}
    assert post.call_args.kwargs["json"]["artifact_selectors"][0]["artifact_type"] == "repository_ir"


def test_submit_outcome_is_thin_steward_adapter():
    mcp = FakeMCP()
    register_agent_tools(mcp)
    with patch("memory_steward_mcp.agent_plane.requests.post", return_value=_response({"ok": True})) as post:
        result = mcp.tools["memory.submit_agent_outcome"](
            project_id="rr",
            outcome_id="o-1",
            objective="analyze",
            result="done",
        )
    assert json.loads(result) == {"ok": True}
    assert post.call_args.args[0].endswith("/v1/agent/outcomes")
    assert post.call_args.kwargs["json"]["outcome_id"] == "o-1"


def test_feedback_is_thin_steward_adapter():
    mcp = FakeMCP()
    register_agent_tools(mcp)
    with patch("memory_steward_mcp.agent_plane.requests.post", return_value=_response({"ok": True})) as post:
        result = mcp.tools["memory.submit_context_feedback"](
            project_id="rr",
            context_request_id="ctx-1",
            used_memory_ids=["m1"],
        )
    assert json.loads(result) == {"ok": True}
    assert post.call_args.args[0].endswith("/v1/context/feedback")
    assert post.call_args.kwargs["json"]["used_memory_ids"] == ["m1"]
