from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import Request

log = logging.getLogger("uvicorn.error")


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def origin_base(req: Request) -> Optional[str]:
    origin = req.headers.get("origin")
    if origin:
        return origin.strip()
    referer = req.headers.get("referer")
    if referer and "://" in referer:
        scheme, rest = referer.split("://", 1)
        host = rest.split("/", 1)[0]
        return f"{scheme}://{host}"
    if referer:
        return referer.strip()
    return None


def project_id(req: Request) -> str:
    explicit = req.headers.get("x-project-id")
    if explicit:
        log.info("project_id.source=header value=%s", explicit)
        return explicit

    origin = req.headers.get("origin")
    referer = req.headers.get("referer")
    if origin or referer:
        value = sha256_hex(origin or referer)[:16]
        log.info("project_id.source=origin value=%s", value)
        return value

    auth = req.headers.get("authorization")
    if auth:
        value = sha256_hex(auth)[:16]
        log.info("project_id.source=auth value=%s", value)
        return value

    log.warning("project_id.source=fallback")
    return "backend-default"


def glap_stream_generator(content: str):
    chunk_id = f"chatcmpl-glap-{uuid.uuid4().hex[:8]}"
    created = int(time.time())
    yield "data: " + json.dumps(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "glap-mcp-bridge",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": None,
                }
            ],
        }
    ) + "\n\n"
    yield "data: " + json.dumps(
        {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": "glap-mcp-bridge",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    ) + "\n\n"
    yield "data: [DONE]\n\n"
