# components/memory_router/src/memory_router/mcp_bridge.py
# memory_router/mcp_bridge.py
#
# GLAP command bridge (schema-driven).
#
# Design notes:
#   * The MCP server (memory_steward_mcp) is the SINGLE SOURCE OF TRUTH for
#     command names, arguments, types, defaults, and descriptions. This bridge
#     holds NO domain knowledge -- it only parses operator input and renders
#     help/errors from the live schema returned by list_tools().
#   * Operator grammar:
#         /glap                         -> grouped command list
#         /glap help <cmd>              -> usage card for one command
#         /glap <cmd>                   -> execute (or usage card if required args missing)
#         /glap <cmd> key=value ...     -> key=value args (quoted values allowed)
#         /glap <cmd> body=<<< ... >>>  -> heredoc for multi-line / multi-quote values
#         /glap <cmd> {json...}         -> raw JSON payload (power-user fallback)
#         /glap <cmd> <value>           -> bare positional, ONLY for single-required-arg tools
#   * No internal validation error or stack trace is ever surfaced to chat.

import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastmcp import Client as MCPClient

log = logging.getLogger("uvicorn.error")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

MCP_URL = os.environ.get("MCP_URL")
if not MCP_URL:
    raise RuntimeError("Missing required env var: MCP_URL")

# Backward-compat aliases: {accepted_name: canonical_tool_name}.
# Kept empty for now. When MCP tool names are normalized, add old->new mappings
# here so existing operator muscle memory and runbooks keep working.
ALIASES: Dict[str, str] = {
    # Reference memory
    "ingest_reference_url": "ref_ingest_url",
    "ingest_reference_text": "ref_ingest_text",
    "list_reference_namespaces": "ref_list",
    "inspect_reference": "ref_inspect",
    "purge_reference": "ref_purge",
    # Static memory
    "list_static": "static_list",
    "create_static": "static_create",
    "update_static": "static_update",
    "toggle_static": "static_toggle",
    "delete_static": "static_delete",
    # Cache / control
    "control_cache": "cache_control",
    # Config (stability plane)
    "set_token_budget": "config_set_budget",
    "force_mode": "config_force_mode",
    "configure_hysteresis": "config_set_hysteresis",
    "get_stability_config": "config_show",
    # Diagnostics
    "get_system_health": "diag_health",
    "explain_decision": "diag_explain",
    "explain_last_decision": "diag_explain_last",
    "get_metrics": "diag_metrics",
    "get_qdrant_stats": "diag_qdrant_stats",
    "logs_read": "diag_logs",
    "diagnostics.logs.read": "diag_logs",
    # Dynamic memory (was named diagnostically)
    "get_project_memory": "dyn_inspect",
    "simulate_retrieval": "dyn_simulate_retrieval",
    # Connections (repo_*) and Git ops (git_*) keep their original names.
}

# project_id is injected by the router from the request context. If a tool
# declares it required, we fill it automatically and never ask the operator.
_CONTEXT_INJECTED = {"project_id"}


# ------------------------------------------------------------------------------
# OpenAI-shaped response wrapper (unchanged contract with server.py)
# ------------------------------------------------------------------------------


def _wrap_openai(content: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-glap-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "glap-mcp-bridge",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


# ------------------------------------------------------------------------------
# Schema helpers
# ------------------------------------------------------------------------------


def _schema_of(tool) -> Dict[str, Any]:
    return getattr(tool, "inputSchema", None) or {}


def _props(tool) -> Dict[str, Any]:
    return _schema_of(tool).get("properties", {}) or {}


def _required(tool) -> List[str]:
    return list(_schema_of(tool).get("required", []) or [])


def _operator_required(tool) -> List[str]:
    """Required args the operator must actually supply (context-injected removed)."""
    return [r for r in _required(tool) if r not in _CONTEXT_INJECTED]


def _jtype(props: Dict[str, Any], key: str) -> str:
    spec = props.get(key, {}) or {}
    t = spec.get("type")
    if isinstance(t, list):  # e.g. ["string","null"]
        t = next((x for x in t if x != "null"), "string")
    return t or "string"


def _group_tag(desc: str) -> str:
    """Tools tag themselves in their description, e.g. '[Git] ...' / '[Diagnostics] ...'."""
    m = re.match(r"\s*\[([^\]]+)\]", desc or "")
    return m.group(1).strip() if m else "Other"


def _short_desc(desc: str) -> str:
    """First sentence/line of the description with the [Tag] prefix stripped."""
    d = re.sub(r"^\s*\[[^\]]+\]\s*", "", (desc or "").strip())
    d = d.split("\n", 1)[0].strip()
    return d


# ------------------------------------------------------------------------------
# Help rendering (all derived from the schema)
# ------------------------------------------------------------------------------


def _render_command_list(tools) -> str:
    groups: Dict[str, List] = {}
    for t in tools:
        groups.setdefault(_group_tag(t.description or ""), []).append(t)

    lines = ["**GLAP commands**", ""]
    for group in sorted(groups):
        lines.append(f"__{group}__")
        for t in sorted(groups[group], key=lambda x: x.name):
            lines.append(f"  `{t.name}` — {_short_desc(t.description or '')}")
        lines.append("")
    lines.append("Run `/glap help <command>` for arguments and an example.")
    return "\n".join(lines).rstrip()


def _usage_card(tool, missing: Optional[List[str]] = None) -> str:
    props = _props(tool)
    req = _operator_required(tool)
    opt = [k for k in props if k not in req and k not in _CONTEXT_INJECTED]

    sig_parts = [f"{k}=<{_jtype(props, k)}>" for k in req]
    for k in opt:
        default = props.get(k, {}).get("default")
        sig_parts.append(f"[{k}={default if default is not None else _jtype(props, k)}]")

    lines: List[str] = []
    if missing:
        lines.append(f"Missing required: {', '.join(missing)}")
        lines.append("")
    lines.append(f"**{tool.name}** — {_short_desc(tool.description or '')}")
    lines.append(f"Usage: `/glap {tool.name} " + " ".join(sig_parts) + "`")

    if req:
        lines.append("Required: " + ", ".join(req))
    if opt:
        opt_desc = []
        for k in opt:
            d = props.get(k, {}).get("default")
            opt_desc.append(f"{k} (default: {d})" if d is not None else k)
        lines.append("Optional: " + ", ".join(opt_desc))

    # Example with a heredoc if any string arg looks like free text.
    text_arg = next(
        (k for k in req if _jtype(props, k) == "string" and k in ("content", "body", "text")),
        None,
    )
    example_args = []
    for k in req:
        if k == text_arg:
            continue
        example_args.append(f'{k}=<{_jtype(props, k)}>')
    example = f"/glap {tool.name} " + " ".join(example_args)
    if text_arg:
        example += f"\n{text_arg}=<<<\n...multi-line value...\n>>>"
    lines.append("")
    lines.append("Example:")
    lines.append(example)
    if text_arg:
        lines.append("")
        lines.append("Multi-line / quoted values: use `key=<<<` ... `>>>`.")
    return "\n".join(lines)


# ------------------------------------------------------------------------------
# Argument parsing
# ------------------------------------------------------------------------------

_KEY_RE = re.compile(r"([A-Za-z_][\w.-]*)=")


class ArgError(ValueError):
    """Operator-facing parse error. Message is safe to show in chat."""


def _coerce(value: str, jtype: str, key: str):
    try:
        if jtype == "integer":
            return int(value)
        if jtype == "number":
            return float(value)
        if jtype == "boolean":
            return str(value).strip().lower() in ("true", "1", "yes", "on")
        if jtype in ("object", "array"):
            return json.loads(value)
        return value
    except (ValueError, json.JSONDecodeError):
        raise ArgError(f"Argument `{key}` expects type {jtype}, got: {value!r}")


def _read_value(s: str, i: int) -> Tuple[str, int]:
    """Read one value starting at index i. Returns (value, next_index)."""
    n = len(s)
    # Heredoc: <<< ... >>>
    if s.startswith("<<<", i):
        end = s.find(">>>", i + 3)
        if end == -1:
            raise ArgError("Unterminated `<<<` heredoc (missing closing `>>>`).")
        val = s[i + 3 : end]
        if val.startswith("\n"):
            val = val[1:]
        if val.endswith("\n"):
            val = val[:-1]
        return val, end + 3
    # Quoted
    if s[i] in ("'", '"'):
        q = s[i]
        j = i + 1
        buf = []
        while j < n:
            c = s[j]
            if c == "\\" and j + 1 < n:
                buf.append(s[j + 1])
                j += 2
                continue
            if c == q:
                return "".join(buf), j + 1
            buf.append(c)
            j += 1
        raise ArgError(f"Unterminated {q} quote.")
    # Balanced JSON value
    if s[i] in ("{", "["):
        depth = 0
        in_str = False
        q = ""
        j = i
        while j < n:
            c = s[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == q:
                    in_str = False
            else:
                if c in ("'", '"'):
                    in_str = True
                    q = c
                elif c in ("{", "["):
                    depth += 1
                elif c in ("}", "]"):
                    depth -= 1
                    if depth == 0:
                        return s[i : j + 1], j + 1
            j += 1
        raise ArgError("Unbalanced JSON value.")
    # Bareword: read to next whitespace
    m = re.compile(r"\S+").match(s, i)
    return m.group(0), m.end()


def _parse_kv(args_raw: str) -> Dict[str, str]:
    """Parse `key=value key2="v 2" body=<<< ... >>>` into raw string values."""
    out: Dict[str, str] = {}
    s = args_raw
    i = 0
    n = len(s)
    while i < n:
        if s[i].isspace():
            i += 1
            continue
        m = _KEY_RE.match(s, i)
        if not m:
            raise ArgError(
                "Expected `key=value` arguments. "
                "For a multi-line value use `key=<<<` ... `>>>`."
            )
        key = m.group(1)
        i = m.end()
        if i < n and s[i].isspace():
            raise ArgError(f"No value after `{key}=`.")
        val, i = _read_value(s, i)
        out[key] = val
    return out


def _build_payload(tool, args_raw: str, project_id: str) -> Dict[str, Any]:
    props = _props(tool)
    op_req = _operator_required(tool)
    payload: Dict[str, Any] = {}

    args_raw = args_raw.strip()

    if args_raw.startswith("{"):
        # JSON payload (power-user fallback)
        try:
            parsed = json.loads(args_raw)
        except json.JSONDecodeError as e:
            raise ArgError(f"Invalid JSON payload: {e.msg}")
        if not isinstance(parsed, dict):
            raise ArgError("JSON payload must be an object.")
        payload.update(parsed)
    elif args_raw and not _KEY_RE.match(args_raw):
        # Bare positional -- only unambiguous for a single operator-required arg.
        if len(op_req) == 1:
            key = op_req[0]
            payload[key] = _coerce(args_raw, _jtype(props, key), key)
        else:
            raise ArgError(
                f"`{tool.name}` needs named arguments. Run `/glap help {tool.name}`."
            )
    elif args_raw:
        raw_kv = _parse_kv(args_raw)
        unknown = [k for k in raw_kv if k not in props]
        if unknown:
            raise ArgError(
                f"Unknown argument(s): {', '.join(unknown)}. "
                f"Valid: {', '.join(props.keys())}."
            )
        for k, v in raw_kv.items():
            payload[k] = _coerce(v, _jtype(props, k), k)

    # Inject context args the operator should never type.
    for k in _CONTEXT_INJECTED:
        if k in _required(tool) and k not in payload:
            payload[k] = project_id

    return payload


# ------------------------------------------------------------------------------
# Async core
# ------------------------------------------------------------------------------


async def _handle_glap_async(user_text: str, project_id: str) -> Tuple[int, Dict[str, Any]]:
    raw = user_text.strip()
    command_part = raw[len("/glap"):].strip() if raw.lower().startswith("/glap") else raw

    try:
        async with MCPClient(MCP_URL) as client:
            tools = await client.list_tools()
            by_name = {t.name: t for t in tools}

            # 1) Bare /glap -> command list
            if not command_part:
                if not tools:
                    return 200, _wrap_openai("No MCP tools available.")
                return 200, _wrap_openai(_render_command_list(tools))

            parts = command_part.split(maxsplit=1)
            head = parts[0]
            rest = parts[1] if len(parts) > 1 else ""

            # 2) /glap help <cmd>
            if head.lower() in ("help", "-h", "--help"):
                target = rest.split(maxsplit=1)[0] if rest else ""
                target = ALIASES.get(target, target)
                if target and target in by_name:
                    return 200, _wrap_openai(_usage_card(by_name[target]))
                return 200, _wrap_openai(_render_command_list(tools))

            # Resolve command (with alias support)
            tool_name = ALIASES.get(head, head)
            tool = by_name.get(tool_name)
            if tool is None:
                near = [n for n in by_name if head.lower() in n.lower()][:5]
                hint = f" Did you mean: {', '.join(near)}?" if near else ""
                return 200, _wrap_openai(
                    f"Unknown command `{head}`.{hint}\nRun `/glap` to list commands."
                )

            # 3) Trailing 'help' on a command -> usage card
            if rest.strip().lower() in ("help", "-h", "--help"):
                return 200, _wrap_openai(_usage_card(tool))

            # 4) Build + validate payload entirely client-side
            try:
                payload = _build_payload(tool, rest, project_id)
            except ArgError as e:
                return 200, _wrap_openai(f"{e}\n\n{_usage_card(tool)}")

            missing = [k for k in _operator_required(tool) if k not in payload]
            if missing:
                return 200, _wrap_openai(_usage_card(tool, missing=missing))

            # 5) Execute
            result = await client.call_tool(tool_name, payload)

            if hasattr(result, "content") and isinstance(result.content, list):
                content = "\n".join(c.text for c in result.content if hasattr(c, "text"))
            elif isinstance(result, dict) and "result" in result:
                content = str(result["result"])
            else:
                content = str(result)

            return 200, _wrap_openai(content or "(no output)")

    except Exception as e:
        # Operators get a short, safe message; the trace goes to the server log only.
        err_id = uuid.uuid4().hex[:8]
        log.error("GLAP internal error [%s]: %s", err_id, e, exc_info=True)
        return 200, _wrap_openai(
            f"GLAP could not complete that command (ref {err_id}). "
            f"Check the command syntax with `/glap help`, or see router logs for ref {err_id}."
        )


# ------------------------------------------------------------------------------
# Public sync entry point (unchanged signature for server.py)
# ------------------------------------------------------------------------------


def handle_glap(user_text: str, project_id: str) -> Tuple[int, Dict[str, Any]]:
    try:
        return asyncio.run(_handle_glap_async(user_text, project_id))
    except Exception as e:
        err_id = uuid.uuid4().hex[:8]
        log.error("GLAP bridge error [%s]: %s", err_id, e, exc_info=True)
        return 200, _wrap_openai(
            f"GLAP bridge error (ref {err_id}). See router logs for details."
        )
