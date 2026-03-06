# stability_plane.py
"""
Stability Plane: token budget, force mode, hysteresis controls.
Refactored to FastMCP tools to satisfy the Glass Pane specification.
"""

import os
import logging
from fastmcp import FastMCP

log = logging.getLogger("memory-steward-mcp.stability")

def register_stability_tools(mcp: FastMCP):

    @mcp.tool()
    def set_token_budget(value: int) -> str:
        """[Stability Plane] Adjusts context_budget_max dynamically."""
        os.environ["MAX_CONTEXT_TOKENS"] = str(value)
        log.info(f"Operator action: SET_TOKEN_BUDGET value={value}")
        return f"Token budget updated to {value}."

    @mcp.tool()
    def force_mode(mode: str) -> str:
        """[Stability Plane] Overrides the Steward's intent classifier."""
        valid_modes = {"engineering", "implementation", "brainstorming", "formal_spec", "casual"}
        if mode not in valid_modes:
            return f"Invalid mode. Must be one of: {valid_modes}"
            
        os.environ["FORCE_MODE"] = mode
        log.info(f"Operator action: FORCE_MODE mode={mode}")
        return f"Mode override set to '{mode}'."

    @mcp.tool()
    def configure_hysteresis(window: int) -> str:
        """[Stability Plane] Update hysteresis window for stability plane (anti-jitter control)."""
        os.environ["HYSTERESIS_WINDOW"] = str(window)
        log.info(f"Operator action: SET_HYSTERESIS window={window}")
        return f"Hysteresis window set to {window}."
