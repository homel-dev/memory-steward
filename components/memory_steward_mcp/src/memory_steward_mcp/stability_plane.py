# stability_plane.py
"""
Stability Plane: token budget, force mode, hysteresis controls.

IMPORTANT: os.environ writes only affect the MCP pod itself.
Config changes are persisted to Postgres (runtime_config table) so the
router and steward can pick them up on their next config reload cycle.
"""

import os
import logging
import psycopg
from fastmcp import FastMCP
from memory_steward_mcp.config import POSTGRES_DSN

log = logging.getLogger("memory-steward-mcp.stability")

VALID_MODES = {"engineering", "implementation", "brainstorming", "formal_spec", "casual"}

def _set_config(key: str, value: str) -> None:
    """Upsert a runtime config key into Postgres so all pods can read it."""
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO runtime_config (key, value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """, (key, value))

def _get_config(key: str) -> str | None:
    """Read a runtime config key from Postgres."""
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM runtime_config WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else None

def register_stability_tools(mcp: FastMCP):

    @mcp.tool()
    def set_token_budget(value: int) -> str:
        """[Stability] Adjusts MAX_CONTEXT_TOKENS. Persisted to Postgres so
        router picks it up on next config reload. Range: 512–200000."""
        if not (512 <= value <= 200000):
            return f"Value {value} out of range. Must be 512–200000."
        _set_config("MAX_CONTEXT_TOKENS", str(value))
        log.info(f"Operator action: SET_TOKEN_BUDGET value={value}")
        return (
            f"Token budget set to {value} in Postgres runtime_config.\n"
            f"Router will apply on next reload (restart or config poll interval)."
        )

    @mcp.tool()
    def force_mode(mode: str) -> str:
        """[Stability] Overrides mode classification for all subsequent requests.
        Set to 'off' to remove the override."""
        if mode != "off" and mode not in VALID_MODES:
            return f"Invalid mode '{mode}'. Must be one of: {VALID_MODES | {'off'}}"
        value = "" if mode == "off" else mode
        _set_config("FORCE_MODE", value)
        log.info(f"Operator action: FORCE_MODE mode={mode}")
        if mode == "off":
            return "Mode override cleared. Steward will classify normally."
        return f"Mode override set to '{mode}' in Postgres runtime_config."

    @mcp.tool()
    def configure_hysteresis(window: int) -> str:
        """[Stability] Set hysteresis window (number of turns before mode transition).
        Higher = more stable, slower to adapt. Range: 1–50."""
        if not (1 <= window <= 50):
            return f"Window {window} out of range. Must be 1–50."
        _set_config("HYSTERESIS_WINDOW", str(window))
        log.info(f"Operator action: SET_HYSTERESIS window={window}")
        return f"Hysteresis window set to {window} in Postgres runtime_config."

    @mcp.tool()
    def get_stability_config() -> str:
        """[Stability] Show current stability configuration from Postgres."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("SELECT key, value, updated_at FROM runtime_config ORDER BY key")
                rows = cur.fetchall()
        except Exception as e:
            return f"DB error: {e}"

        if not rows:
            return "No runtime_config entries. Using environment variable defaults."

        lines = ["## Runtime Config (Postgres)"]
        for key, value, updated_at in rows:
            lines.append(f"- **{key}**: `{value}` (updated {updated_at.strftime('%Y-%m-%d %H:%M')})")
        return "\n".join(lines)
