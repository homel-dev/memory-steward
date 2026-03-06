# diagnostics_plane.py
"""
Diagnostics Plane: health, version, env/contract, logs, stats.
Refactored to FastMCP tools to satisfy the Glass Pane specification.
"""

import os
import logging
import psycopg
import requests
from urllib.parse import urlparse
from fastmcp import FastMCP
from memory_steward_mcp.config import (
    POSTGRES_DSN, LOG_DIR, QDRANT_URL, MAX_CONTEXT_TOKENS, 
    HYSTERESIS_WINDOW, APP_VERSION, QDRANT_COLLECTION, EMBEDDINGS_URL
)

log = logging.getLogger("memory-steward-mcp.diagnostics")

def register_diagnostics_tools(mcp: FastMCP, qdrant):

    @mcp.tool(name="diagnostics.logs.read")
    def logs_read(service: str, lines: int = 200) -> str:
        """[Diagnostics Plane] Read bounded container logs for a specific service."""
        max_lines = min(lines, 1000)
        log_path = os.path.join(LOG_DIR, f"{service}.log")
        
        try:
            with open(log_path, "r") as f:
                tail = f.readlines()[-max_lines:]
                return "".join(tail)
        except FileNotFoundError:
            return f"Log file not found for service: {service}"
        except Exception as e:
            return f"Log read failed: {str(e)}"

    @mcp.tool(name="explain_decision")
    def explain_decision(request_id: str) -> str:
        """[Diagnostics Plane] Returns the deterministic Blame Trace for a specific request."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT dropped_budget, dropped_no_content, dropped_other 
                    FROM telemetry.retrieval 
                    WHERE request_id = %s
                    """, 
                    (request_id,)
                )
                row = cur.fetchone()
                if not row:
                    return "Retrieval telemetry missing (not executed or not recorded)."
                
                return (
                    f"Dropped candidates breakdown for {request_id}:\n"
                    f"- Budget: {row[0]}\n"
                    f"- No Content: {row[1]}\n"
                    f"- Other: {row[2]}"
                )
        except Exception as e:
            return f"Database query failed: {str(e)}"

    @mcp.tool()
    def explain_last_decision() -> str:
        """[Diagnostics Plane] Blame trace for last request."""
        query_last = """
            SELECT request_id
            FROM telemetry.request
            ORDER BY t_begin DESC
            LIMIT 1
        """
        try:
            with psycopg.connect(POSTGRES_DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute(query_last)
                    row = cur.fetchone()
                    if not row:
                        return "No telemetry recorded yet."
                    request_id = row[0]
        except Exception as e:
            return f"DB error: {str(e)}"
        return explain_decision(request_id)

    @mcp.resource("diagnostics://contract")
    def get_runtime_contract() -> str:
        """[Diagnostics Plane] Read-only access to immutable rules and environment contract."""
        return str({
            "QDRANT_URL": QDRANT_URL,
            "MAX_CONTEXT_TOKENS": MAX_CONTEXT_TOKENS,
            "HYSTERESIS_WINDOW": HYSTERESIS_WINDOW,
            "VERSION": APP_VERSION
        })

    @mcp.tool()
    def get_system_health() -> str:
        """[Diagnostics Plane] connectivity check."""
        health = {"qdrant": "unknown", "postgres": "unknown", "embeddings": "unknown", "list_transcribe": "unknown"}
        
        try:
            qdrant.get_collection(QDRANT_COLLECTION)
            health["qdrant"] = "ok"
        except Exception as e:
            health["qdrant"] = f"error: {str(e)}"

        try:
            with psycopg.connect(POSTGRES_DSN) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            health["postgres"] = "ok"
        except Exception as e:
            health["postgres"] = f"error: {str(e)}"

        try:
            r = requests.get(f"{EMBEDDINGS_URL}/healthz", timeout=2)
            health["embeddings"] = "ok" if r.ok else f"degraded: {r.status_code}"
        except Exception as e:
            health["embeddings"] = f"error: {str(e)}"

        list_url = os.environ.get("LIST_URL", "http://memory-steward-list:8001/v1/list/transcribe")
        try:
            parsed = urlparse(list_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}/ping"
            r = requests.get(base_url, timeout=2)
            health["list_transcribe"] = "ok" if r.ok else f"degraded: {r.status_code}"
        except Exception as e:
            health["list_transcribe"] = f"error: {str(e)}"

        return str(health)
