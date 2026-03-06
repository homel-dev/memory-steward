"""
Central config and canonical runtime contract.
Aligned with Document 09 (Runtime) and Document 06 (Telemetry).
"""

import os

def _env(name: str, default: str = None, required: bool = False) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

# Content Plane
QDRANT_URL          = _env("QDRANT_URL", required=True)
QDRANT_COLLECTION   = _env("QDRANT_COLLECTION", required=True)
EMBEDDINGS_URL      = _env("EMBEDDINGS_URL", required=True)

# Diagnostics Plane
POSTGRES_DSN        = _env("POSTGRES_DSN", required=True)
LOG_DIR             = _env("LOG_DIR", "/var/log/memory_steward_logs")

# Stability Plane
STATIC_MEMORY_REFRESH_SECONDS = int(_env("STATIC_MEMORY_REFRESH_SECONDS", "1800"))
MAX_CONTEXT_TOKENS  = int(_env("MAX_CONTEXT_TOKENS", "2000"))
HYSTERESIS_WINDOW   = int(_env("HYSTERESIS_WINDOW", "8"))
FORCE_MODE          = _env("FORCE_MODE", "")

APP_VERSION         = "memory-steward-mcp/2.0.0"
