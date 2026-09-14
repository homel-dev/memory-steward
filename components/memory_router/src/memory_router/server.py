from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

import memory_router.request_context as request_context_core
import memory_router.retrieval as retrieval_core
import memory_router.schemas as schemas_core
import memory_router.upstream as upstream_core
from memory_router import config
from memory_router.mcp_bridge import handle_glap
from memory_router.request_context import (
    glap_stream_generator as _glap_stream_generator,
    origin_base as _origin_base,
    project_id as _project_id,
)
from memory_router.retrieval import (
    count_tokens as _count_tokens,
    embed_one as _embed_one,
    pg_agent_reference_load as _pg_agent_reference_load,
    pg_static_load as _pg_static_load,
    qdrant_dense as _qdrant_dense,
    qdrant_reference as _qdrant_reference,
    qdrant_reference_get as _qdrant_reference_get,
    reference_candidate_payload as _reference_candidate_payload,
    render_context_envelope as _render_context_envelope,
)
from memory_router.schemas import (
    ArtifactSelector,
    ChatCompletionRequest,
    ChatMessage,
    ContextRetrieveRequest,
    ReferenceSearchRequest,
)
from memory_router.state import telemetry
from memory_router.upstream import (
    async_admit as _async_admit,
    builder_openai_url as _builder_openai_url,
    get_builder_default_model as _get_builder_default_model,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("uvicorn.error")

# Compatibility exports for internal tests and existing imports. Runtime values
# themselves are owned by their focused modules.
_sha256_hex = request_context_core.sha256_hex
_extract_static_rules = retrieval_core.extract_static_rules
_maximal_marginal_relevance = retrieval_core.maximal_marginal_relevance
_normalize_builder_base = upstream_core.normalize_builder_base
Candidate = schemas_core.Candidate


def _stitch_context_structured(
    candidates, max_tokens: int, model: str
):
    """Compatibility wrapper that preserves the server-level token-count patch seam."""
    return retrieval_core.stitch_context_structured(
        candidates, max_tokens, model, count_fn=_count_tokens
    )


def _selected_candidate_refs(candidates, max_tokens: int, model: str):
    """Compatibility wrapper that preserves the server-level token-count patch seam."""
    return retrieval_core.selected_candidate_refs(
        candidates, max_tokens, model, count_fn=_count_tokens
    )

BUILDER_MODEL = config.BUILDER_MODEL
BUILDER_API_KEY = config.BUILDER_API_KEY
DENSE_PREFETCH = config.DENSE_PREFETCH
MAX_TOTAL_TOKENS = config.MAX_TOTAL_TOKENS
REFERENCE_MODES = config.REFERENCE_MODES
REFERENCE_RETRIEVAL_ENABLED = config.REFERENCE_RETRIEVAL_ENABLED

app = FastAPI(
    title="homel-memory-router",
    version="0.3",
    description="Memory-augmenting OpenAI-compatible chat router (MMR + Stitching)",
)


def _retrieve_context_structured(
    request_id: str,
    project_id: str,
    query: Optional[str],
    model: str,
    mode: Optional[str] = None,
    artifact_selectors: Optional[List[ArtifactSelector]] = None,
    reference_filters: dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Compatibility seam: orchestration lives in retrieval.py; dependencies remain patchable here."""
    return retrieval_core.retrieve_context_structured(
        request_id=request_id,
        project_id=project_id,
        query=query,
        model=model,
        mode=mode,
        artifact_selectors=artifact_selectors,
        reference_filters=reference_filters,
        pg_static_loader=_pg_static_load,
        pg_agent_reference_loader=_pg_agent_reference_load,
        embedder=_embed_one,
        dense_search=_qdrant_dense,
        reference_search=_qdrant_reference,
    )


def _assemble_context(
    request_id: str,
    project_id: str,
    query: str,
    model: str,
    recent_messages: List[ChatMessage],
    mode: Optional[str] = None,
):
    retrieval = _retrieve_context_structured(
        request_id=request_id,
        project_id=project_id,
        query=query,
        model=model,
        mode=mode,
    )
    final_text = _render_context_envelope(retrieval, query, recent_messages)
    accounting = retrieval["accounting"]
    return (
        final_text,
        accounting["dense_candidates"],
        accounting["selected_topk"],
        accounting["context_tokens_est"],
        accounting["static_tokens_est"],
        accounting["dynamic_tokens_est"],
        accounting["dropped_budget"],
        accounting["dropped_no_content"],
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": config.effective_builder_model() or "homel-model",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "memory-router",
            }
        ],
    }


@app.post("/v1/reference/search")
def reference_search(req: ReferenceSearchRequest, http_req: Request):
    pid = _project_id(http_req)
    query_vec = _embed_one(req.query)
    candidates = _qdrant_reference(
        query_vec,
        req.limit,
        reference_filters=req.reference_filters,
    )
    return {
        "project_id": pid,
        "query": req.query,
        "reference_filters": req.reference_filters or {},
        "items": [_reference_candidate_payload(candidate) for candidate in candidates],
    }


@app.get("/v1/reference/{chunk_id}")
def reference_get(chunk_id: str, http_req: Request):
    pid = _project_id(http_req)
    item = _qdrant_reference_get(chunk_id)
    if item is None:
        raise HTTPException(status_code=404, detail="reference chunk not found")
    return {"project_id": pid, **item}


@app.post("/v1/context/retrieve")
def retrieve_context(req: ContextRetrieveRequest, http_req: Request):
    if not req.query and not req.artifact_selectors:
        raise HTTPException(status_code=422, detail="query or artifact_selectors is required")

    context_request_id = uuid.uuid4().hex
    pid = _project_id(http_req)
    origin = _origin_base(http_req)
    model = (req.model or "").strip() or config.effective_builder_model() or _get_builder_default_model()

    telemetry.request_begin(
        request_id=context_request_id,
        project_id=pid,
        origin=origin,
        origin_hash=None,
        model_requested=req.model,
        decided_mode=req.mode,
        context_budget_max=config.effective_max_context_tokens(),
        static_tokens_est=None,
        dynamic_tokens_est=None,
    )
    try:
        retrieval = _retrieve_context_structured(
            request_id=context_request_id,
            project_id=pid,
            query=req.query,
            model=model,
            mode=req.mode,
            artifact_selectors=req.artifact_selectors,
            reference_filters=req.reference_filters,
        )
        accounting = retrieval["accounting"]
        telemetry.retrieval_write(
            request_id=context_request_id,
            project_id=pid,
            dense_candidates=accounting["dense_candidates"],
            selected_topk=accounting["selected_topk"],
            context_tokens_est=accounting["context_tokens_est"],
            dropped_budget=accounting["dropped_budget"],
            dropped_no_content=accounting["dropped_no_content"],
            dropped_other=0,
        )
        telemetry.request_end(
            request_id=context_request_id,
            http_status=200,
            context_budget_max=config.effective_max_context_tokens(),
            static_tokens_est=accounting["static_tokens_est"],
            dynamic_tokens_est=accounting["dynamic_tokens_est"],
        )
        return {
            "context_request_id": context_request_id,
            "project_id": pid,
            "mode": req.mode,
            "dialogue_state": {
                "recent_turns": [
                    message.model_dump(mode="json")
                    for message in req.recent_messages[-4:]
                ]
            },
            **retrieval,
        }
    except Exception as exc:
        telemetry.request_end(
            request_id=context_request_id,
            http_status=500,
            error_kind=type(exc).__name__,
            error_detail=str(exc),
        )
        log.exception("agent context retrieval failed request_id=%s", context_request_id)
        raise HTTPException(status_code=500, detail="context retrieval failed") from exc


@app.post("/v1/chat/completions")
def chat(req: ChatCompletionRequest, http_req: Request):
    request_id = uuid.uuid4().hex
    pid = _project_id(http_req)
    origin = _origin_base(http_req)
    model_requested = (req.model or "").strip() or None

    try:
        user_msg = next(message for message in reversed(req.messages) if message.role == "user")
        user_text = user_msg.text_content
    except StopIteration:
        return {"choices": [{"message": {"role": "assistant", "content": "Ready."}}]}

    if user_text.strip().lower().startswith("/glap"):
        http_status, response = handle_glap(user_text, pid)
        if req.stream:
            content = (
                response.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return StreamingResponse(
                _glap_stream_generator(content), media_type="text/event-stream"
            )
        return JSONResponse(status_code=http_status, content=response)

    telemetry.request_begin(
        request_id=request_id,
        project_id=pid,
        origin=origin,
        origin_hash=None,
        model_requested=model_requested,
        decided_mode=req.mode,
        context_budget_max=config.effective_max_context_tokens(),
        static_tokens_est=None,
        dynamic_tokens_est=None,
    )

    http_status: Optional[int] = None
    error_kind: Optional[str] = None
    error_detail: Optional[str] = None
    model_sent: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None

    try:
        model = config.effective_builder_model() or _get_builder_default_model()
        model_sent = model

        user_text_tokens = _count_tokens(model, user_text)
        history_messages = req.messages[:-1]
        allowed_history_tokens = (
            config.MAX_TOTAL_TOKENS
            - config.effective_max_context_tokens()
            - user_text_tokens
            - 200
        )

        pruned_history: List[ChatMessage] = []
        current_history_tokens = 0
        for message in reversed(history_messages):
            message_tokens = _count_tokens(model, message.text_content)
            if current_history_tokens + message_tokens > allowed_history_tokens:
                break
            pruned_history.insert(0, message)
            current_history_tokens += message_tokens

        builder_messages = pruned_history + [req.messages[-1]]
        retrieval = _retrieve_context_structured(
            request_id=request_id,
            project_id=pid,
            query=user_text,
            model=model,
            mode=req.mode,
        )
        system_ctx = _render_context_envelope(retrieval, user_text, pruned_history)
        accounting = retrieval["accounting"]
        dense_candidates = accounting["dense_candidates"]
        selected_topk = accounting["selected_topk"]
        context_tokens_est = accounting["context_tokens_est"]
        static_tokens_est = accounting["static_tokens_est"]
        dynamic_tokens_est = accounting["dynamic_tokens_est"]
        dropped_budget = accounting["dropped_budget"]
        dropped_no_content = accounting["dropped_no_content"]

        telemetry.retrieval_write(
            request_id=request_id,
            project_id=pid,
            dense_candidates=dense_candidates,
            selected_topk=selected_topk,
            context_tokens_est=context_tokens_est,
            dropped_budget=dropped_budget,
            dropped_no_content=dropped_no_content,
            dropped_other=0,
        )

        upstream_messages: List[Dict[str, Any]] = []
        if system_ctx.strip():
            upstream_messages.append({"role": "system", "content": system_ctx})
        # Important: use the pruned history calculated above. The previous code
        # rebuilt the payload from req.messages and accidentally bypassed its own
        # global history budget.
        upstream_messages.extend(message.model_dump() for message in builder_messages)

        if config.DEBUG_PROMPTS:
            log.info(
                "debug.prompt request_id=%s upstream_msgs=%s",
                request_id,
                json.dumps(upstream_messages, indent=2),
            )

        def _safe_count(content: Any) -> int:
            if isinstance(content, str):
                return _count_tokens(model, content)
            return _count_tokens(
                model,
                " ".join(
                    item.get("text", "")
                    for item in content
                    if item.get("type") == "text"
                ),
            )

        prompt_tokens = sum(_safe_count(message["content"]) for message in upstream_messages)
        log.info(
            "prompt.tokens=%d model=%s request_id=%s",
            prompt_tokens,
            model,
            request_id,
        )

        payload = {
            "model": model,
            "messages": upstream_messages,
            "temperature": req.temperature,
            "stream": False,
        }

        response_body: Dict[str, Any] = {}
        assistant = ""
        for attempt in (1, 2):
            step_name = "builder_chat" if attempt == 1 else "builder_chat_retry_empty"
            with telemetry.step(request_id=request_id, project_id=pid, name=step_name):
                response = requests.post(
                    _builder_openai_url("/chat/completions"),
                    headers={"Authorization": f"Bearer {config.BUILDER_API_KEY}"},
                    json=payload,
                    timeout=180,
                )
                http_status = response.status_code
                if not response.ok:
                    error_kind = "builder_error"
                    error_detail = (response.text or "")[:1000]
                    log.error(
                        "builder.error status=%s body=%s request_id=%s",
                        response.status_code,
                        response.text,
                        request_id,
                    )
                    response.raise_for_status()

                response_body = response.json()
                assistant = (
                    ((response_body.get("choices") or [{}])[0].get("message") or {}).get(
                        "content"
                    )
                ) or ""
                log.info(
                    "builder.reply request_id=%s attempt=%d assistant_len=%d",
                    request_id,
                    attempt,
                    len(assistant),
                )
                if assistant.strip():
                    break
                if attempt == 1:
                    time.sleep(0.25)

        if not assistant.strip():
            error_kind = "builder_empty_completion"
            error_detail = "builder returned empty completion after retry"
            log.error(
                "builder.empty_completion request_id=%s body=%s",
                request_id,
                json.dumps(response_body)[:2000] if response_body else "",
            )
            raise HTTPException(status_code=502, detail="builder returned empty completion")

        completion_tokens = _count_tokens(model, assistant)
        log.info(
            "completion.tokens=%d total.tokens=%d request_id=%s",
            completion_tokens,
            (prompt_tokens or 0) + completion_tokens,
            request_id,
        )

        _async_admit(
            request_id=request_id,
            project_id=pid,
            messages=[{"role": "user", "content": user_text}],
        )
        log.info(
            "admit.request_id=%s project_id=%s user_text=%s",
            request_id,
            pid,
            user_text,
        )

        if req.stream:
            def sse():
                created = int(time.time())
                chunk_id = f"chat-{created}"
                yield "data: " + json.dumps(
                    {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"role": "assistant", "content": assistant},
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
                        "model": model,
                        "choices": [
                            {"index": 0, "delta": {}, "finish_reason": "stop"}
                        ],
                    }
                ) + "\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(sse(), media_type="text/event-stream")

        return response_body

    except Exception as exc:
        if http_status is None:
            http_status = 500
        if error_kind is None:
            error_kind = "router_exception"
            error_detail = str(exc)
        raise
    finally:
        telemetry.request_end(
            request_id=request_id,
            http_status=http_status,
            error_kind=error_kind,
            error_detail=error_detail,
            model_sent_to_builder=model_sent,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=((prompt_tokens or 0) + (completion_tokens or 0))
            if (prompt_tokens is not None or completion_tokens is not None)
            else None,
            context_budget_max=config.effective_max_context_tokens(),
            static_tokens_est=static_tokens_est
            if "static_tokens_est" in locals()
            else None,
            dynamic_tokens_est=dynamic_tokens_est
            if "dynamic_tokens_est" in locals()
            else None,
        )
