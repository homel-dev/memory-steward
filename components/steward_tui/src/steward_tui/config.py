# components/steward_tui/src/steward_tui/config.py
"""Runtime configuration for the Glass Pane operator TUI.

The only knob is the MCP endpoint. It defaults to the port-forwarded address an
operator gets from `kubectl port-forward svc/memory-steward-mcp 8081:8081`.
"""
from __future__ import annotations

import os

DEFAULT_MCP_URL = "http://localhost:8081/mcp/"


def mcp_url() -> str:
    """Resolve the MCP endpoint from STEWARD_MCP_URL, falling back to the default.

    An empty/blank env value is treated as unset so a stray export never wins.
    """
    return os.environ.get("STEWARD_MCP_URL", "").strip() or DEFAULT_MCP_URL
