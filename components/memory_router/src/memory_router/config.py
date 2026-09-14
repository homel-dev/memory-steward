from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict

import psycopg

log = logging.getLogger("uvicorn.error")


def _req(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _opt(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _svc_url(host_env: str, port_env: str, scheme: str = "http") -> str:
    return f"{scheme}://{_req(host_env)}:{_req(port_env)}"


POSTGRES_HOST = _req("POSTGRES_SERVICE_HOST")
POSTGRES_PORT = _req("POSTGRES_SERVICE_PORT")
POSTGRES_USER = _req("POSTGRES_USER")
POSTGRES_PASSWORD = _req("POSTGRES_PASSWORD")
POSTGRES_DB = _req("POSTGRES_DB")
POSTGRES_SSLMODE = _opt("POSTGRES_SSLMODE", "disable")
POSTGRES_APPNAME = _opt("POSTGRES_APPLICATION_NAME", "memory-router")

POSTGRES_DSN = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    f"?sslmode={POSTGRES_SSLMODE}&application_name={POSTGRES_APPNAME}"
)

QDRANT_URL = _svc_url("QDRANT_SERVICE_HOST", "QDRANT_SERVICE_PORT")
EMBEDDINGS_URL = _svc_url("EMBEDDINGS_SERVICE_HOST", "EMBEDDINGS_SERVICE_PORT")
QDRANT_COLLECTION = _req("QDRANT_COLLECTION")

BUILDER_BASE_URL = os.environ.get("BUILDER_BASE_URL")
if not BUILDER_BASE_URL:
    BUILDER_BASE_URL = _svc_url(
        "VLLM_BUILDER_SERVICE_HOST", "VLLM_BUILDER_SERVICE_PORT"
    )
BUILDER_API_KEY = _opt("BUILDER_API_KEY", "local-token")
BUILDER_MODEL = _req("BUILDER_MODEL")

STEWARD_URL = _svc_url("MEMORY_STEWARD_SERVICE_HOST", "MEMORY_STEWARD_SERVICE_PORT")

MAX_CONTEXT_TOKENS = int(_opt("MAX_CONTEXT_TOKENS", "8192"))
MAX_TOTAL_TOKENS = int(_opt("MAX_TOTAL_TOKENS", "16384"))
DENSE_PREFETCH = int(_opt("DENSE_PREFETCH", "25"))
TOP_K = int(_opt("TOP_K", "8"))
MMR_LAMBDA = float(_opt("MMR_LAMBDA", "0.5"))

DEBUG_PROMPTS = _opt("DEBUG_PROMPTS", "0").strip() in (
    "1",
    "true",
    "TRUE",
    "yes",
    "YES",
)

REFERENCE_RETRIEVAL_ENABLED = _opt("REFERENCE_RETRIEVAL_ENABLED", "1").strip() in (
    "1",
    "true",
    "TRUE",
    "yes",
    "YES",
)
REFERENCE_MODES = {"engineering", "implementation", "formal_spec"}

MAX_CONTEXT_TOKENS_DEFAULT = MAX_CONTEXT_TOKENS
_RUNTIME_CFG_TTL_SECONDS = float(_opt("RUNTIME_CONFIG_TTL_SECONDS", "5"))
_runtime_cfg_cache: Dict[str, str] = {}
_runtime_cfg_expiry = 0.0
_runtime_cfg_lock = threading.Lock()


def pg_connect():
    return psycopg.connect(POSTGRES_DSN)


def _runtime_config_snapshot() -> Dict[str, str]:
    """Read Router-owned live configuration with a short best-effort cache."""
    global _runtime_cfg_cache, _runtime_cfg_expiry
    now = time.monotonic()
    with _runtime_cfg_lock:
        if now < _runtime_cfg_expiry:
            return _runtime_cfg_cache

    try:
        with pg_connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT key, value FROM runtime_config")
            snapshot = {key: value for key, value in cur.fetchall()}
    except Exception as exc:
        log.warning("runtime_config read failed (using cached/default values): %s", exc)
        snapshot = _runtime_cfg_cache

    with _runtime_cfg_lock:
        _runtime_cfg_cache = snapshot
        _runtime_cfg_expiry = time.monotonic() + _RUNTIME_CFG_TTL_SECONDS
    return snapshot


def _runtime_int(key: str, default: int) -> int:
    raw = _runtime_config_snapshot().get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        log.warning("runtime_config[%s]=%r is not an int; using default %d", key, raw, default)
        return default


def _runtime_str(key: str, default: str) -> str:
    raw = _runtime_config_snapshot().get(key)
    return raw if raw else default


def effective_max_context_tokens() -> int:
    return _runtime_int("MAX_CONTEXT_TOKENS", MAX_CONTEXT_TOKENS_DEFAULT)


def effective_builder_base_url() -> str:
    return _runtime_str("BUILDER_BASE_URL", BUILDER_BASE_URL)


def effective_builder_model() -> str:
    return _runtime_str("BUILDER_MODEL", BUILDER_MODEL)
