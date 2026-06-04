# components/memory_router/src/memory_router/mcp_bridge.py
# memory_router/mcp_bridge.py

import os
import json
import logging
import asyncio
import threading
import time
import uuid
from typing import Dict, Any, Tuple

import requests
from fastmcp import Client as MCPClient

log = logging.getLogger("uvicorn.error")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

MCP_URL = os.environ.get("MCP_URL")
if not MCP_URL:
    raise RuntimeError("Missing required env var: MCP_URL")

# Open WebUI integration — lazy slash-command seeding on first /glap use
OPEN_WEBUI_URL = os.environ.get("OPEN_WEBUI_URL", "http://open-webui:8080")
OPEN_WEBUI_API_KEY = os.environ.get("OPEN_WEBUI_API_KEY", "")

# ------------------------------------------------------------------------------
# Open WebUI slash-command seeding
# ------------------------------------------------------------------------------

def _owui_headers() -> dict:
    h = {"Content-Type": "application/json"}
    if OPEN_WEBUI_API_KEY:
        h["Authorization"] = f"Bearer {OPEN_WEBUI_API_KEY}"
    return h


def _seed_glap_commands_if_needed() -> None:
    """
    Checks if /glap commands already exist in Open WebUI.
    If not: fetches the MCP tool list, generates a slash command per tool,
    and POSTs them to Open WebUI's prompts API.
    Fails silently — never blocks the actual /glap request.
    """
    try:
        # 1. Check what commands already exist
        r = requests.get(
            f"{OPEN_WEBUI_URL}/api/v1/prompts/",
            headers=_owui_headers(),
            timeout=5,
        )
        if not r.ok:
            log.warning("glap.seed_check_failed status=%s", r.status_code)
            return

        existing = {p.get("command", "") for p in r.json()}
        if any(cmd.startswith("/glap") for cmd in existing):
            log.debug("glap.commands_already_seeded skipping")
            return

        # 2. Fetch MCP tool list
        tools = asyncio.run(_list_mcp_tools())
        if not tools:
            log.warning("glap.seed_no_tools_found")
            return

        # 3. Register each tool as a slash command
        seeded = 0
        for tool in tools:
            name = tool.name
            # First line of docstring only
            description = (tool.description or "").strip().split("\n")[0][:200]

            # Build content template from tool's input schema
            schema = getattr(tool, "inputSchema", {}) or {}
            props = schema.get("properties", {})

            if props:
                args = " ".join(
                    f"{k}="
                    for k in props
                    if k != "project_id"  # injected by router automatically
                )
                content = f"/glap {name} {args}".strip()
            else:
                content = f"/glap {name}"

            payload = {
                "command": f"/glap-{name.replace('_', '-').replace('.', '-')}",
                "title": f"GLAP: {description or name}",
                "content": content,
            }

            pr = requests.post(
                f"{OPEN_WEBUI_URL}/api/v1/prompts/",
                headers=_owui_headers(),
                json=payload,
                timeout=5,
            )
            if pr.ok:
                seeded += 1
            else:
                log.warning("glap.seed_failed name=%s status=%s body=%s",
                            name, pr.status_code, pr.text[:200])

        # Seed the bare /glap command that lists everything
        requests.post(
            f"{OPEN_WEBUI_URL}/api/v1/prompts/",
            headers=_owui_headers(),
            json={"command": "/glap", "title": "GLAP: List all commands", "content": "/glap"},
            timeout=5,
        )

        log.info("glap.commands_seeded count=%d", seeded + 1)

    except Exception as e:
        log.warning("glap.seed_error error=%s", e)


async def _list_mcp_tools() -> list:
    try:
        async with MCPClient(MCP_URL) as client:
            return await client.list_tools()
    except Exception as e:
        log.warning("glap.list_tools_failed error=%s", e)
        return []


# Thread-safe one-shot per process lifetime.
# Re-checks Open WebUI each time (cheap) so deleted commands get re-seeded.
_seed_lock = threading.Lock()
_seed_triggered = False


def _trigger_seed_once() -> None:
    global _seed_triggered
    if _seed_triggered:
        return
    with _seed_lock:
        if _seed_triggered:
            return
        _seed_triggered = True
    threading.Thread(target=_seed_glap_commands_if_needed, daemon=True).start()


# ------------------------------------------------------------------------------
# Helpers
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
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    }

# ------------------------------------------------------------------------------
# Async Implementation (Internal)
# ------------------------------------------------------------------------------

async def _handle_glap_async(user_text: str, project_id: str) -> Tuple[int, Dict[str, Any]]:
    """
    Internal async logic.
    """
    raw = user_text.strip()
    if raw.startswith("/glap"):
        command_part = raw[len("/glap"):].strip()
    else:
        command_part = raw

    try:
        async with MCPClient(MCP_URL) as client:

            # 1. List Tools (No command provided)
            if not command_part:
                tools = await client.list_tools()

                if not tools:
                    content = "No MCP tools available."
                else:
                    lines = ["Available GLAP commands:"]
                    for t in sorted(tools, key=lambda x: x.name):
                        desc = t.description or ""
                        lines.append(f"- {t.name}: {desc}")
                    content = "\n".join(lines)

                return 200, _wrap_openai(content)

            # 2. Execute Tool
            parts = command_part.split(maxsplit=1)
            tool_name = parts[0]
            args_raw = parts[1] if len(parts) > 1 else ""

            # Construct Payload
            payload = {}
            if args_raw:
                try:
                    payload = json.loads(args_raw)
                    if not isinstance(payload, dict):
                        raise ValueError("Not a dict")
                except (json.JSONDecodeError, ValueError):
                    tools = await client.list_tools()
                    target_tool = next((t for t in tools if t.name == tool_name), None)

                    if target_tool and hasattr(target_tool, "inputSchema"):
                        schema = target_tool.inputSchema
                        props = schema.get("properties", {})
                        required = schema.get("required", [])

                        if "project_id" in required:
                            payload["project_id"] = project_id
                            required.remove("project_id")

                        if len(required) > 1:
                            split_args = args_raw.split(maxsplit=len(required) - 1)

                            if len(split_args) == len(required):
                                for idx, req_key in enumerate(required):
                                    val = split_args[idx]
                                    p_type = props.get(req_key, {}).get("type", "string")
                                    if p_type == "integer":
                                        try: val = int(val)
                                        except ValueError: pass
                                    payload[req_key] = val
                            else:
                                payload = {"input": args_raw}

                        elif len(required) == 1:
                            param_name = required[0]
                            val = args_raw
                            p_type = props.get(param_name, {}).get("type", "string")
                            if p_type == "integer":
                                try: val = int(val)
                                except ValueError: pass
                            payload[param_name] = val

                        elif "project_id" in props and len(required) == 0 and args_raw:
                            payload["input"] = args_raw

            elif not args_raw:
                tools = await client.list_tools()
                target_tool = next((t for t in tools if t.name == tool_name), None)
                if target_tool and hasattr(target_tool, "inputSchema"):
                    required = target_tool.inputSchema.get("required", [])
                    if "project_id" in required:
                        payload["project_id"] = project_id

            # Call Tool
            result = await client.call_tool(tool_name, payload)

            # Parse Result
            if hasattr(result, "content") and isinstance(result.content, list):
                content = "\n".join([
                    c.text for c in result.content if hasattr(c, "text")
                ])
            elif isinstance(result, dict) and "result" in result:
                content = str(result["result"])
            else:
                content = str(result)

            return 200, _wrap_openai(content)

    except Exception as e:
        log.error(f"GLAP internal error: {e}", exc_info=True)
        return 500, _wrap_openai(f"MCP error: {str(e)}")


# ------------------------------------------------------------------------------
# Public Sync Entry Point
# ------------------------------------------------------------------------------

def handle_glap(user_text: str, project_id: str) -> Tuple[int, Dict[str, Any]]:
    """
    Synchronous wrapper for compatibility with server.py.
    Triggers slash-command seeding on first call.
    """
    _trigger_seed_once()
    try:
        return asyncio.run(_handle_glap_async(user_text, project_id))
    except Exception as e:
        log.error(f"GLAP Bridge Error: {e}", exc_info=True)
        return 500, _wrap_openai(f"Bridge error: {str(e)}")
