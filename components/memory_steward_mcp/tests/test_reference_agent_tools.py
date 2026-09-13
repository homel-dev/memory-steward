import importlib
import json
import sys
import types
from unittest.mock import MagicMock, patch


fastmcp = types.ModuleType("fastmcp")
fastmcp.FastMCP = object
sys.modules.setdefault("fastmcp", fastmcp)

register_agent_tools = importlib.import_module(
    "memory_steward_mcp.agent_plane"
).register_agent_tools


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, name=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn
        return decorator


def _response(payload):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


def test_reference_search_is_thin_router_adapter():
    mcp = FakeMCP()
    register_agent_tools(mcp)
    with patch(
        "memory_steward_mcp.agent_plane.requests.post",
        return_value=_response({"items": []}),
    ) as post:
        result = mcp.tools["memory.reference.search"](
            project_id="rr",
            query="schematic file format",
            reference_filters={"product": "kicad", "version": "10"},
            limit=6,
        )

    assert json.loads(result) == {"items": []}
    assert post.call_args.args[0].endswith("/v1/reference/search")
    assert post.call_args.kwargs["headers"] == {"X-Project-ID": "rr"}
    assert post.call_args.kwargs["json"] == {
        "query": "schematic file format",
        "limit": 6,
        "reference_filters": {"product": "kicad", "version": "10"},
    }


def test_reference_get_is_thin_router_adapter():
    mcp = FakeMCP()
    register_agent_tools(mcp)
    with patch(
        "memory_steward_mcp.agent_plane.requests.get",
        return_value=_response({"id": "chunk-1"}),
    ) as get:
        result = mcp.tools["memory.reference.get"](
            project_id="rr",
            chunk_id="chunk-1",
        )

    assert json.loads(result) == {"id": "chunk-1"}
    assert get.call_args.args[0].endswith("/v1/reference/chunk-1")
    assert get.call_args.kwargs["headers"] == {"X-Project-ID": "rr"}
