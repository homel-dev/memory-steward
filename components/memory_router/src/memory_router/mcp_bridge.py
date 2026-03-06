# memory_router/mcp_bridge.py

import os
import json
import logging
import asyncio
import time
import uuid
from typing import Dict, Any, Tuple

from fastmcp import Client as MCPClient

log = logging.getLogger("uvicorn.error")

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

MCP_URL = os.environ.get("MCP_URL")
if not MCP_URL:
    raise RuntimeError("Missing required env var: MCP_URL")


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

                        # Force exact injection of project_id if the tool requires it
                        if "project_id" in required:
                            payload["project_id"] = project_id
                            required.remove("project_id")

                        # --- MULTI-ARGUMENT POSITIONAL MAPPING ---
                        if len(required) > 1:
                            # Split raw string into chunks matching the number of remaining required args
                            split_args = args_raw.split(maxsplit=len(required) - 1)

                            if len(split_args) == len(required):
                                for idx, req_key in enumerate(required):
                                    val = split_args[idx]
                                    p_type = props.get(req_key, {}).get("type", "string")

                                    # Type casting
                                    if p_type == "integer":
                                        try: val = int(val)
                                        except ValueError: pass

                                    payload[req_key] = val
                            else:
                                payload = {"input": args_raw} # Failsafe

                        # --- SINGLE-ARGUMENT MAPPING ---
                        elif len(required) == 1:
                            param_name = required[0]
                            val = args_raw
                            p_type = props.get(param_name, {}).get("type", "string")

                            # Type casting
                            if p_type == "integer":
                                try: val = int(val)
                                except ValueError: pass

                            payload[param_name] = val
                            
                        # If project_id was the *only* required arg, and there's leftover text, map it to a generic input if possible
                        elif "project_id" in props and len(required) == 0 and args_raw:
                            payload["input"] = args_raw

            # If no args_raw was provided, but the tool strictly requires project_id
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
    """
    try:
        # We use asyncio.run() to bridge from the sync thread pool to the async MCP client
        return asyncio.run(_handle_glap_async(user_text, project_id))
    except Exception as e:
        log.error(f"GLAP Bridge Error: {e}", exc_info=True)
        return 500, _wrap_openai(f"Bridge error: {str(e)}")

