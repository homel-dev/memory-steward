# components/steward_tui/tests/test_schema.py
"""Pure-logic tests: no network, no Textual. Mirrors the real MCP tool schemas
(e.g. ref_ingest_url, static_create) as FastMCP emits them."""
import pytest

from steward_tui.mcp_client import ToolField, coerce, fields_from_schema, render_result


def test_fields_basic_required_and_optional():
    schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "source url"},
            "product": {"type": "string"},
            "version": {"type": "string", "default": "latest"},
        },
        "required": ["url", "product"],
    }
    fields = fields_from_schema(schema)
    by = {f.name: f for f in fields}
    assert by["url"].required and by["url"].type == "string"
    assert by["product"].required
    assert not by["version"].required and by["version"].default == "latest"
    assert [f.name for f in fields] == ["url", "product", "version"]  # order preserved


def test_fields_anyof_optional_union_picks_scalar():
    # FastMCP renders `dict[str,str] | None` / `int | None` as anyOf unions.
    schema = {
        "type": "object",
        "properties": {
            "limit": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": 8},
            "filters": {"anyOf": [{"type": "object"}, {"type": "null"}]},
        },
    }
    by = {f.name: f for f in fields_from_schema(schema)}
    assert by["limit"].type == "integer"
    assert by["filters"].type == "object"


def test_fields_empty_and_non_object():
    assert fields_from_schema(None) == []
    assert fields_from_schema({"type": "string"}) == []
    assert fields_from_schema({"type": "object"}) == []


def test_coerce_types():
    i = ToolField("limit", "integer", required=False)
    n = ToolField("rate", "number", required=False)
    b = ToolField("dry_run", "boolean", required=False)
    s = ToolField("q", "string", required=True)
    assert coerce(i, "8") == 8
    assert coerce(n, "0.5") == 0.5
    assert coerce(b, "true") is True
    assert coerce(b, "0") is False
    assert coerce(s, "hello") == "hello"


def test_coerce_json_object_and_array():
    obj = ToolField("reference_filters", "object", required=False)
    arr = ToolField("items", "array", required=False)
    assert coerce(obj, '{"product":"kicad","version":"9.0"}') == {
        "product": "kicad",
        "version": "9.0",
    }
    assert coerce(arr, '["a","b"]') == ["a", "b"]
    with pytest.raises(ValueError, match="JSON object"):
        coerce(obj, '["not-an-object"]')
    with pytest.raises(ValueError, match="valid JSON"):
        coerce(obj, "{")


def test_coerce_optional_empty_is_none_required_raises():
    opt = ToolField("version", "string", required=False)
    req = ToolField("product", "string", required=True)
    assert coerce(opt, "   ") is None
    with pytest.raises(ValueError):
        coerce(req, "")


class _Block:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, content=None, structured=None, is_error=False):
        self.content = content or []
        self.structured_content = structured
        self.is_error = is_error


def test_render_prefers_structured_then_text_and_flags_error():
    assert "chunks" in render_result(_Result(structured={"chunks": 3}))
    assert render_result(_Result(content=[_Block("done")])) == "done"
    out = render_result(_Result(content=[_Block("boom")], is_error=True))
    assert "TOOL ERROR" in out and "boom" in out
