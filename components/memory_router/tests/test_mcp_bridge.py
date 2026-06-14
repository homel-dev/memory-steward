# components/memory_router/tests/test_mcp_bridge.py
"""
Unit + dispatch tests for memory_router/mcp_bridge.py (schema-driven GLAP bridge).

Covers:
- value coercion (int / number / bool / json / string)
- key=value parsing, quoting, and the <<< ... >>> heredoc
- JSON-payload fallback and bare single-arg positional
- project_id injection for context-required args
- unknown-arg and missing-required handling (no raw exceptions)
- usage card / command-list rendering from schema
- ALIASES integrity (every alias points at a real tool)
- end-to-end handle_glap dispatch: list, help, execute, alias, unknown, error safety

External deps (fastmcp) are stubbed; a configurable fake MCP client is injected.
"""
import importlib.util
import pathlib
import sys
import types

import pytest

# fastmcp may not be importable in the router test venv; stub it only if absent.
if "fastmcp" not in sys.modules:
    try:
        import fastmcp  # noqa: F401
    except Exception:
        _stub = types.ModuleType("fastmcp")
        _stub.Client = object
        sys.modules["fastmcp"] = _stub

# Load the REAL bridge directly from its file. test_integration.py and
# test_router_unit.py replace sys.modules["memory_router.mcp_bridge"] with a
# MagicMock at import time; loading by path under a private name sidesteps that
# pollution entirely so we exercise the actual implementation.
_BRIDGE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "src" / "memory_router" / "mcp_bridge.py"
)
_spec = importlib.util.spec_from_file_location("_real_mcp_bridge", _BRIDGE_PATH)
b = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b)


# ---------------------------------------------------------------------------
# Fake MCP client plumbing
# ---------------------------------------------------------------------------

class _Tool:
    def __init__(self, name, description, properties=None, required=None):
        self.name = name
        self.description = description
        self.inputSchema = {
            "properties": properties or {},
            "required": required or [],
        }


class _Block:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, text):
        self.content = [_Block(text)]


def make_client(tools, call_handler=None, raise_on_call=None):
    """Return a factory usable as a drop-in for mcp_bridge.MCPClient."""
    class _FakeClient:
        def __init__(self, url):
            self.url = url

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def list_tools(self):
            return tools

        async def call_tool(self, name, payload):
            if raise_on_call:
                raise raise_on_call
            if call_handler:
                return _Result(call_handler(name, payload))
            return _Result(f"OK {name} {payload}")

    return _FakeClient


GWF = _Tool(
    "git_write_file",
    "[Git] Write a file to a repository (create or update).",
    {
        "connection": {"type": "string"},
        "project": {"type": "string"},
        "file_path": {"type": "string"},
        "content": {"type": "string"},
        "commit_message": {"type": "string"},
        "ref": {"type": "string", "default": "main"},
        "overwrite": {"type": "boolean", "default": False},
    },
    ["connection", "project", "file_path", "content", "commit_message"],
)
RTEST = _Tool("repo_test", "[Connections] Verify a connection.",
              {"name": {"type": "string"}}, ["name"])
METRICS = _Tool("diag_metrics", "[Diagnostics] Metrics over a window.",
                {"window_minutes": {"type": "integer", "default": 60},
                 "project_id": {"type": "string"}},
                ["project_id"])
HEALTH = _Tool("diag_health", "[Diagnostics] Liveness check.", {}, [])


def run(text, pid="proj1"):
    out = b.handle_glap(text, pid)
    return out[0], out[1]["choices"][0]["message"]["content"]


def content_of(status_and_text):
    return status_and_text[1]


# ---------------------------------------------------------------------------
# Coercion
# ---------------------------------------------------------------------------

def test_coerce_types():
    assert b._coerce("42", "integer", "k") == 42
    assert b._coerce("3.5", "number", "k") == 3.5
    assert b._coerce("true", "boolean", "k") is True
    assert b._coerce("off", "boolean", "k") is False
    assert b._coerce('{"a":1}', "object", "k") == {"a": 1}
    assert b._coerce("plain", "string", "k") == "plain"


def test_coerce_bad_int_raises_argerror():
    with pytest.raises(b.ArgError):
        b._coerce("notanint", "integer", "window_minutes")


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_kv_basic_and_quoted():
    parsed = b._parse_kv('connection=gl commit_message="add the runbook"')
    assert parsed == {"connection": "gl", "commit_message": "add the runbook"}


def test_heredoc_preserves_newlines_quotes_spaces():
    args = (
        'connection=gl project=g/d file_path=x.md commit_message="m" '
        'content=<<<\n# Title\nline with "quotes" and    spaces\n- bullet\n>>>'
    )
    payload = b._build_payload(GWF, args, "proj1")
    assert payload["content"] == '# Title\nline with "quotes" and    spaces\n- bullet'
    assert payload["commit_message"] == "m"


def test_unterminated_heredoc_is_argerror():
    with pytest.raises(b.ArgError):
        b._parse_kv("content=<<<\nno closing fence")


def test_bool_and_default_not_injected():
    args = ("connection=gl project=g/d file_path=x.md "
            'commit_message=m content=hello overwrite=true')
    payload = b._build_payload(GWF, args, "proj1")
    assert payload["overwrite"] is True
    # optional args with schema defaults are NOT client-injected (server applies them)
    assert "ref" not in payload


def test_bare_positional_single_required():
    assert b._build_payload(RTEST, "gl", "proj1") == {"name": "gl"}


def test_bare_positional_rejected_for_multi_required():
    with pytest.raises(b.ArgError):
        b._build_payload(GWF, "just-one-word", "proj1")


def test_json_payload_fallback():
    assert b._build_payload(RTEST, '{"name":"gl"}', "proj1") == {"name": "gl"}


def test_bad_json_payload_is_argerror():
    with pytest.raises(b.ArgError):
        b._build_payload(RTEST, '{"name": gl}', "proj1")


def test_unknown_arg_is_argerror():
    with pytest.raises(b.ArgError):
        b._build_payload(RTEST, "naem=gl", "proj1")


def test_project_id_injected_when_required():
    payload = b._build_payload(METRICS, "window_minutes=120", "projX")
    assert payload == {"window_minutes": 120, "project_id": "projX"}


def test_operator_required_excludes_context():
    assert b._operator_required(METRICS) == []  # project_id is context-injected
    assert set(b._operator_required(GWF)) == {
        "connection", "project", "file_path", "content", "commit_message"
    }


# ---------------------------------------------------------------------------
# Help rendering
# ---------------------------------------------------------------------------

def test_usage_card_lists_missing_and_signature():
    card = b._usage_card(GWF, missing=["content", "commit_message"])
    assert "Missing required: content, commit_message" in card
    assert "/glap git_write_file" in card
    assert "Required:" in card and "Optional:" in card


def test_command_list_groups_by_tag():
    txt = b._render_command_list([GWF, RTEST, HEALTH])
    assert "Git" in txt and "Connections" in txt and "Diagnostics" in txt
    assert "`git_write_file`" in txt


# ---------------------------------------------------------------------------
# Alias integrity
# ---------------------------------------------------------------------------

def test_aliases_are_strings_and_nonempty():
    assert all(isinstance(k, str) and isinstance(v, str) and v for k, v in b.ALIASES.items())


def test_alias_examples_resolve():
    assert b.ALIASES["get_project_memory"] == "dyn_inspect"
    assert b.ALIASES["diagnostics.logs.read"] == "diag_logs"
    assert b.ALIASES["set_token_budget"] == "config_set_budget"


# ---------------------------------------------------------------------------
# End-to-end dispatch via handle_glap (real entry point)
# ---------------------------------------------------------------------------

def test_bare_glap_lists_commands(monkeypatch):
    monkeypatch.setattr(b, "MCPClient", make_client([GWF, RTEST, HEALTH]))
    status, txt = run("/glap")
    assert status == 200
    assert "git_write_file" in txt and "repo_test" in txt


def test_help_for_command(monkeypatch):
    monkeypatch.setattr(b, "MCPClient", make_client([GWF]))
    _, txt = run("/glap help git_write_file")
    assert "Usage:" in txt and "git_write_file" in txt


def test_missing_required_returns_usage_not_trace(monkeypatch):
    monkeypatch.setattr(b, "MCPClient", make_client([GWF]))
    _, txt = run("/glap git_write_file connection=gl")
    assert "Missing required:" in txt
    assert "Traceback" not in txt


def test_successful_execution(monkeypatch):
    captured = {}

    def handler(name, payload):
        captured["name"] = name
        captured["payload"] = payload
        return "committed abc123"

    monkeypatch.setattr(b, "MCPClient", make_client([GWF], call_handler=handler))
    args = ('git_write_file connection=gl project=g/d file_path=x.md '
            'commit_message=m content=hello')
    _, txt = run("/glap " + args)
    assert "committed abc123" in txt
    assert captured["name"] == "git_write_file"
    assert captured["payload"]["content"] == "hello"


def test_alias_resolves_old_name(monkeypatch):
    seen = {}

    def handler(name, payload):
        seen["n"] = name
        return "ok"

    monkeypatch.setattr(b, "MCPClient", make_client([METRICS], call_handler=handler))
    # operator types the OLD name; bridge should dispatch to canonical diag_metrics
    _, txt = run("/glap get_metrics window_minutes=30")
    assert seen["n"] == "diag_metrics"
    assert "ok" in txt


def test_unknown_command_is_friendly(monkeypatch):
    monkeypatch.setattr(b, "MCPClient", make_client([GWF, RTEST]))
    _, txt = run("/glap nope_not_real")
    assert "Unknown command" in txt
    assert "Traceback" not in txt


def test_internal_error_is_masked_with_ref(monkeypatch):
    monkeypatch.setattr(
        b, "MCPClient",
        make_client([HEALTH], raise_on_call=RuntimeError("secret stack detail")),
    )
    _, txt = run("/glap diag_health")
    assert "secret stack detail" not in txt
    assert "ref " in txt.lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
