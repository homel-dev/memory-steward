from __future__ import annotations

import threading
from typing import Dict, List, Optional

import requests

from memory_router import config
from memory_router.state import telemetry

_default_model_cache: Optional[str] = None


def normalize_builder_base(url: str) -> str:
    value = url.rstrip("/")
    if value.endswith("/v1"):
        return value[:-3]
    return value


def builder_openai_url(path: str) -> str:
    return f"{normalize_builder_base(config.effective_builder_base_url())}/v1{path}"


def get_builder_default_model() -> str:
    global _default_model_cache
    configured = config.effective_builder_model()
    if configured:
        return configured
    if _default_model_cache:
        return _default_model_cache

    response = requests.get(builder_openai_url("/models"), timeout=15)
    response.raise_for_status()
    data = response.json().get("data") or []
    if not data or not data[0].get("id"):
        raise RuntimeError("builder /v1/models invalid; set BUILDER_MODEL")
    _default_model_cache = data[0]["id"]
    return _default_model_cache


def async_admit(request_id: str, project_id: str, messages: List[Dict[str, str]]) -> None:
    if not config.STEWARD_URL:
        return

    def run() -> None:
        handle = telemetry.step_begin(
            request_id=request_id,
            project_id=project_id,
            name="steward_async_call",
        )
        try:
            response = requests.post(
                f"{config.STEWARD_URL}/admit",
                json={
                    "request_id": request_id,
                    "project_id": project_id,
                    "messages": messages,
                },
                timeout=20,
            )
            telemetry.step_end(
                handle=handle,
                ok=response.ok,
                http_status=response.status_code,
                error_detail=None if response.ok else (response.text or "")[:500],
            )
        except Exception as exc:
            telemetry.step_end(handle=handle, ok=False, error_detail=str(exc))

    threading.Thread(target=run, daemon=True).start()
