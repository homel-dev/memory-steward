# components/steward_tui/src/steward_tui/mcp_client.py
"""Thin async wrapper over the FastMCP client, plus PURE helpers that turn a
tool's JSON-Schema into form fields and coerce UI strings back into typed args.

The pure helpers (`fields_from_schema`, `coerce`, `render_result`) carry no
network and are unit-tested in isolation. Only `fetch_tools`/`invoke_tool` touch
the wire.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from fastmcp import Client

from steward_tui.config import mcp_url

# JSON-Schema scalar type -> the input widget kind we render for it.
_SCALARS = {"string", "integer", "number", "boolean"}


@dataclass
class ToolField:
    name: str
    type: str  # one of _SCALARS
    required: bool
    default: Any = None
    description: str = ""
    enum: Optional[list] = None


@dataclass
class ToolSpec:
    name: str
    description: str
    fields: list[ToolField] = field(default_factory=list)

    @property
    def plane(self) -> str:
        """Group tools by their namespace prefix (``ref``, ``static``, ``diag``,
        ``config``, ``memory`` ...). Handles both ``ref_ingest_url`` and the
        dotted ``memory.reference.search`` naming used by the agent plane."""
        for sep in (".", "_"):
            if sep in self.name:
                return self.name.split(sep, 1)[0]
        return self.name


def fields_from_schema(schema: dict | None) -> list[ToolField]:
    """PURE: turn a JSON-Schema object into an ordered list of ToolField.

    Tolerates the ``anyOf`` unions FastMCP emits for Optional params
    (e.g. ``dict[str, str] | None``) by picking the first concrete scalar.
    Non-scalar shapes (objects/arrays) fall back to a free-text ``string``
    field so the operator can hand-type JSON if needed.
    """
    if not schema or schema.get("type") != "object":
        return []
    props = schema.get("properties", {}) or {}
    required = set(schema.get("required", []) or [])
    out: list[ToolField] = []
    for pname, pschema in props.items():
        if not isinstance(pschema, dict):
            continue
        jtype = pschema.get("type")
        if jtype not in _SCALARS:
            for alt in pschema.get("anyOf", []) or []:
                if isinstance(alt, dict) and alt.get("type") in _SCALARS:
                    jtype = alt["type"]
                    break
        ftype = jtype if jtype in _SCALARS else "string"
        out.append(
            ToolField(
                name=pname,
                type=ftype,
                required=pname in required,
                default=pschema.get("default"),
                description=(pschema.get("description") or "").strip(),
                enum=pschema.get("enum"),
            )
        )
    return out


def coerce(fld: ToolField, raw: str) -> Any:
    """PURE: coerce a raw UI string into the field's JSON type.

    An empty value for an optional field returns None (caller omits it).
    An empty value for a required field raises ValueError.
    """
    raw = (raw or "").strip()
    if raw == "":
        if fld.required:
            raise ValueError(f"{fld.name} is required")
        return None
    if fld.type == "integer":
        return int(raw)
    if fld.type == "number":
        return float(raw)
    if fld.type == "boolean":
        return raw.lower() in ("1", "true", "yes", "y", "on")
    return raw


def render_result(res: Any) -> str:
    """PURE: flatten a CallToolResult into human-readable text.

    Prefers structured output; falls back to text content blocks; never throws.
    """
    parts: list[str] = []
    if getattr(res, "is_error", False):
        parts.append("⚠️  TOOL ERROR")
    data = getattr(res, "structured_content", None)
    if data is None:
        data = getattr(res, "data", None)
    if data is not None:
        try:
            parts.append(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            parts.append(str(data))
    for block in getattr(res, "content", None) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else str(res)


async def fetch_tools(url: str | None = None) -> list[ToolSpec]:
    """List tools from the MCP server, sorted by plane then name."""
    url = url or mcp_url()
    specs: list[ToolSpec] = []
    async with Client(url) as client:
        for t in await client.list_tools():
            specs.append(
                ToolSpec(
                    name=t.name,
                    description=(t.description or "").strip(),
                    fields=fields_from_schema(getattr(t, "inputSchema", None)),
                )
            )
    specs.sort(key=lambda s: (s.plane, s.name))
    return specs


async def invoke_tool(name: str, arguments: dict, url: str | None = None) -> str:
    """Call a tool and return its rendered result. Errors are returned, not raised."""
    url = url or mcp_url()
    async with Client(url) as client:
        res = await client.call_tool(name, arguments, raise_on_error=False)
    return render_result(res)
