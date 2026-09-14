"""Runtime configuration tools exposed through MCP.

Only keys with a runtime consumer are described as active behavior. FORCE_MODE
and HYSTERESIS_WINDOW are retained as compatibility keys, but the current
Router/Steward do not consume them.
"""

import logging

import psycopg
from fastmcp import FastMCP

from memory_steward_mcp.config import POSTGRES_DSN

log = logging.getLogger("memory-steward-mcp.stability")

VALID_MODES = {"engineering", "implementation", "brainstorming", "formal_spec", "casual"}


def _set_config(key: str, value: str) -> None:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO runtime_config (key, value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE
            SET value = EXCLUDED.value, updated_at = now()
            """,
            (key, value),
        )


def _get_config(key: str) -> str | None:
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM runtime_config WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else None


def register_stability_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="config_set_budget")
    def set_token_budget(value: int) -> str:
        """Set MAX_CONTEXT_TOKENS. The current Router consumes this runtime key."""
        if not 512 <= value <= 200000:
            return f"Value {value} out of range. Must be 512–200000."
        _set_config("MAX_CONTEXT_TOKENS", str(value))
        log.info("Operator action: SET_TOKEN_BUDGET value=%s", value)
        return f"MAX_CONTEXT_TOKENS set to {value}; Router will apply it after its runtime-config cache refresh."

    @mcp.tool(name="config_force_mode")
    def force_mode(mode: str) -> str:
        """Persist legacy FORCE_MODE compatibility state.

        The current Router/Steward do not consume FORCE_MODE, so this operation
        does not change request behavior.
        """
        if mode != "off" and mode not in VALID_MODES:
            return f"Invalid mode '{mode}'. Must be one of: {VALID_MODES | {'off'}}"
        value = "" if mode == "off" else mode
        _set_config("FORCE_MODE", value)
        log.info("Operator action: STORE_FORCE_MODE mode=%s active_consumer=false", mode)
        return (
            f"FORCE_MODE compatibility value stored as {value!r}. "
            "No current Router/Steward consumer exists; runtime behavior is unchanged."
        )

    @mcp.tool(name="config_set_hysteresis")
    def configure_hysteresis(window: int) -> str:
        """Persist legacy HYSTERESIS_WINDOW compatibility state.

        The current Router/Steward do not implement mode hysteresis, so this
        operation does not change request behavior.
        """
        if not 1 <= window <= 50:
            return f"Window {window} out of range. Must be 1–50."
        _set_config("HYSTERESIS_WINDOW", str(window))
        log.info("Operator action: STORE_HYSTERESIS window=%s active_consumer=false", window)
        return (
            f"HYSTERESIS_WINDOW compatibility value stored as {window}. "
            "No current hysteresis engine consumes it; runtime behavior is unchanged."
        )

    @mcp.tool(name="config_show")
    def get_stability_config() -> str:
        """Show persisted runtime configuration and whether known keys are active."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("SELECT key, value, updated_at FROM runtime_config ORDER BY key")
                rows = cur.fetchall()
        except Exception as exc:
            return f"DB error: {exc}"

        if not rows:
            return "No runtime_config entries. Environment/default values apply."

        active = {"MAX_CONTEXT_TOKENS", "BUILDER_BASE_URL", "BUILDER_MODEL"}
        lines = ["## Runtime Config (Postgres)"]
        for key, value, updated_at in rows:
            consumer = "active-consumer" if key in active else "no-current-consumer"
            lines.append(
                f"- **{key}**: `{value}` ({consumer}; updated {updated_at.strftime('%Y-%m-%d %H:%M')})"
            )
        return "\n".join(lines)
