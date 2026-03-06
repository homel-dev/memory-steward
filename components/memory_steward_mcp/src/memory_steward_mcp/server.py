"""
Memory Steward "Glass Pane" - MCP Server.
Exposes an ASGI application for use with Uvicorn (HTTP Transport).
"""

import logging
import time
import os
import json
import requests
from collections import deque
from typing import Optional

# 3rd Party
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from qdrant_client import QdrantClient
import psycopg

# Internal Config
from memory_steward_mcp.config import (
    QDRANT_URL, QDRANT_COLLECTION, POSTGRES_DSN, LOG_DIR,
    MAX_CONTEXT_TOKENS, HYSTERESIS_WINDOW, APP_VERSION, EMBEDDINGS_URL
)

# Plane Registries
from memory_steward_mcp.content_plane import register_content_tools
from memory_steward_mcp.stability_plane import register_stability_tools
from memory_steward_mcp.diagnostics_plane import register_diagnostics_tools

# Configure Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("steward-mcp")

# ==============================================================================
# 1. INITIALIZATION
# ==============================================================================

mcp = FastMCP("Memory Steward Glass Pane")

@mcp.custom_route("/healthz", methods=["GET"])
async def health_check(request: Request) -> PlainTextResponse:
    return PlainTextResponse("OK")

try:
    qdrant = QdrantClient(QDRANT_URL, timeout=5)
except Exception as e:
    log.error(f"Failed to init Qdrant: {e}")
    qdrant = None

def embed_text(text: str) -> list[float]:
    r = requests.post(EMBEDDINGS_URL, json={"text": text}, timeout=10)
    r.raise_for_status()
    return r.json()["vector"]

# ==============================================================================
# 2. PLANE REGISTRATION
# ==============================================================================

if qdrant:
    register_content_tools(mcp, qdrant, embed_text)
    register_diagnostics_tools(mcp, qdrant)

register_stability_tools(mcp)

# ==============================================================================
# 3. ENTRYPOINT
# ==============================================================================
if __name__ == "__main__":
    mcp.run(
      transport="http",
      host="0.0.0.0",
      port=8081,
      log_level="DEBUG",
    )
