# memory_router/server.py
"""
homel-memory-router
High-Grade Engineering Edition: MMR + Semantic Stitching
"""

import os
import json
import hashlib
import threading
import time
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

import psycopg
import requests
import tiktoken
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from memory_router.telemetry import TelemetryWriter
from memory_router.mcp_bridge import handle_glap

# ------------------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------------------

def _req(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _opt(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _svc_url(host_env: str, port_env: str, scheme: str = "http") -> str:
    host = _req(host_env)
    port = _req(port_env)
    return f"{scheme}://{host}:{port}"


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
    BUILDER_BASE_URL = _svc_url("VLLM_BUILDER_SERVICE_HOST", "VLLM_BUILDER_SERVICE_PORT")
BUILDER_API_KEY = _opt("BUILDER_API_KEY", "local-token")

STEWARD_URL = _svc_url("MEMORY_STEWARD_SERVICE_HOST", "MEMORY_STEWARD_SERVICE_PORT")
BUILDER_MODEL = _req("BUILDER_MODEL")

MAX_CONTEXT_TOKENS = int(_opt("MAX_CONTEXT_TOKENS", "8192"))
MAX_TOTAL_TOKENS = int(_opt("MAX_TOTAL_TOKENS", "16384"))
RECENCY_HALF_LIFE_SECONDS = int(_opt("RECENCY_HALF_LIFE_SECONDS", str(7 * 24 * 3600)))
DENSE_PREFETCH = int(_opt("DENSE_PREFETCH", "25"))
TOP_K = int(_opt("TOP_K", "8"))

MMR_LAMBDA = float(_opt("MMR_LAMBDA", "0.5"))  # 0.5 = Balance between Relevance and Diversity

# Avoid raw print() in request path
DEBUG_PROMPTS = _opt("DEBUG_PROMPTS", "0").strip() in ("1", "true", "TRUE", "yes", "YES")

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("uvicorn.error")

# ------------------------------------------------------------------------------
# Telemetry
# ------------------------------------------------------------------------------

telemetry = TelemetryWriter(POSTGRES_DSN)

# ------------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------------

app = FastAPI(
    title="homel-memory-router",
    version="0.3",
    description="Memory-augmenting OpenAI-compatible chat router (MMR + Stitching)",
)

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = None
    stream: Optional[bool] = False
    mode: Optional[str] = None


class StaticUpsert(BaseModel):
    project_id: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    mode: str = "global"
    is_active: bool = True
    priority: int = 0


@dataclass
class Candidate:
    id: str
    content: str
    vector: List[float]
    metadata: Dict[str, Any]
    token_count: int = 0


# ------------------------------------------------------------------------------
# Utilities
# ------------------------------------------------------------------------------

def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _pg():
    return psycopg.connect(POSTGRES_DSN)


def _origin_base(req: Request) -> Optional[str]:
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


def _project_id(req: Request) -> str:
    pid = req.headers.get("x-project-id")
    if pid:
        log.info("project_id.source=header value=%s", pid)
        return pid

    origin = req.headers.get("origin")
    referer = req.headers.get("referer")
    if origin or referer:
        base = origin or referer
        pid = _sha256_hex(base)[:16]
        log.info("project_id.source=origin value=%s", pid)
        return pid

    auth = req.headers.get("authorization")
    if auth:
        pid = _sha256_hex(auth)[:16]
        log.info("project_id.source=auth value=%s", pid)
        return pid

    log.warning("project_id.source=fallback")
    return "backend-default"


def _glap_stream_generator(content: str):
    chunk_id = f"chatcmpl-glap-{uuid.uuid4().hex[:8]}"
    ts = int(time.time())

    yield "data: " + json.dumps({
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": ts,
        "model": "glap-mcp-bridge",
        "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]
    }) + "\n\n"

    yield "data: " + json.dumps({
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": ts,
        "model": "glap-mcp-bridge",
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
    }) + "\n\n"

    yield "data: [DONE]\n\n"

# ------------------------------------------------------------------------------
# Token Counting
# ------------------------------------------------------------------------------

_tokenizer_cache: Dict[str, tiktoken.Encoding] = {}

def _get_tokenizer(model: str) -> tiktoken.Encoding:
    if model not in _tokenizer_cache:
        try:
            _tokenizer_cache[model] = tiktoken.encoding_for_model(model)
        except KeyError:
            _tokenizer_cache[model] = tiktoken.get_encoding("cl100k_base")
    return _tokenizer_cache[model]


def _count_tokens(model: str, text: str) -> int:
    enc = _get_tokenizer(model)
    return len(enc.encode(text))


# ------------------------------------------------------------------------------
# Static Memory (Postgres)
# ------------------------------------------------------------------------------

def _pg_static_load(mode: Optional[str] = None) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, content, mode
            FROM static_memory
            WHERE is_active = true
              AND (mode = 'global' OR mode = %s)
            ORDER BY
              CASE WHEN mode = 'global' THEN 1 ELSE 2 END ASC,
              created_at ASC
            """,
            (mode,),
        )
        for r_id, content, row_mode in cur.fetchall():
            if content:
                rows.append((str(r_id), str(content), str(row_mode)))
    return rows

def _extract_static_rules(static_rows: List[Tuple[str, str, str]]) -> Dict[str, List[str]]:
    rules = {"global": [], "mode": []}
    for _, content, row_mode in static_rows:
        clean_content = content.replace("\n", " ").strip()
        if row_mode == 'global':
            rules["global"].append(clean_content)
        else:
            rules["mode"].append(clean_content)
    return rules

# ------------------------------------------------------------------------------
# Memory Retrieval & Logic (UPGRADED)
# ------------------------------------------------------------------------------

def _embed_one(text: str) -> List[float]:
    r = requests.post(
        f"{EMBEDDINGS_URL}/embed",
        json={"texts": [text], "normalize": True},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["vectors"][0]


def _qdrant_dense(project_id: str, vec: List[float], limit: int) -> List[Candidate]:
    payload = {
        "vector": {"name": "dense", "vector": vec},
        "limit": limit,
        "with_payload": True,
        "with_vector": True,
        "filter": {
            "must": [
                {"key": "project_id", "match": {"value": project_id}},
            ]
        },
    }
    try:
        r = requests.post(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("result", []) or []

        candidates: List[Candidate] = []
        for res in results:
            content = (res.get("payload") or {}).get("content")
            if not content:
                continue

            vector = res.get("vector")
            if isinstance(vector, dict):
                vector = vector.get("dense") or vector.get("vector")

            if not vector:
                continue

            candidates.append(
                Candidate(
                    id=str(res.get("id")),
                    content=str(content),
                    vector=list(vector),
                    metadata=res.get("payload") or {},
                    token_count=0,
                )
            )

        return candidates

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            log.warning("Qdrant collection missing, skipping dense recall")
            return []
        raise


def _maximal_marginal_relevance(
    query_vec: List[float],
    candidates: List[Candidate],
    top_k: int,
    lambda_mult: float,
) -> List[Candidate]:
    if not candidates:
        return []

    query_np = np.array(query_vec, dtype=np.float32).reshape(1, -1)
    cand_np = np.array([c.vector for c in candidates], dtype=np.float32)

    sim_to_query = cosine_similarity(query_np, cand_np)[0]

    selected_indices: List[int] = []
    candidate_indices = list(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_score = -np.inf
        best_idx = -1

        for idx in candidate_indices:
            relevance = float(sim_to_query[idx])

            if selected_indices:
                sim_to_selected = cosine_similarity(
                    cand_np[idx].reshape(1, -1),
                    cand_np[selected_indices],
                )
                redundancy = float(np.max(sim_to_selected))
            else:
                redundancy = 0.0

            score = (lambda_mult * relevance) - ((1.0 - lambda_mult) * redundancy)

            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx != -1:
            selected_indices.append(best_idx)
            candidate_indices.remove(best_idx)

    return [candidates[i] for i in selected_indices]


def _stitch_context_structured(
    candidates: List[Candidate],
    max_tokens: int,
    model: str,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], int, int, int, int]:
    if not candidates:
        return {}, {}, 0, 0, 0, 0

    ontology_grouped: Dict[str, List[str]] = {}
    context_grouped: Dict[str, List[str]] = {}
    used_tokens = 0
    used_items = 0
    dropped_budget = 0
    dropped_no_content = 0

    for c in candidates:
        if not c.content or not c.content.strip():
            dropped_no_content += 1
            continue

        if c.token_count == 0:
            c.token_count = _count_tokens(model, c.content)

        cost = c.token_count + 5

        if used_tokens + cost > max_tokens:
            dropped_budget += 1
            continue

        metadata_source = str(c.metadata.get("source", "GENERAL_CONTEXT")).upper()
        namespace = str(c.metadata.get("namespace", metadata_source)).lower()
        group_key = metadata_source.replace("_", " ")
        clean_content = c.content.replace("\n", " ").strip()

        if "reference" in namespace or "doc" in namespace or "spec" in namespace:
            ontology_grouped.setdefault(group_key, []).append(clean_content)
        else:
            context_grouped.setdefault(group_key, []).append(clean_content)

        used_tokens += cost
        used_items += 1

    return ontology_grouped, context_grouped, used_items, used_tokens, dropped_budget, dropped_no_content


def _assemble_context(
    request_id: str,
    project_id: str,
    query: str,
    model: str,
    recent_messages: List[ChatMessage],
    mode: Optional[str] = None,
) -> Tuple[str, int, int, int, int, int, int, int]:
    # 1) Embed
    with telemetry.step(request_id=request_id, project_id=project_id, name="embed"):
        query_vec = _embed_one(query)

    # 2) Static memory
    with telemetry.step(request_id=request_id, project_id=project_id, name="pg_static"):
        static_rows = _pg_static_load(mode=mode)
        static_rules = _extract_static_rules(static_rows)
        static_tokens_est = 200

    # 3) Dense retrieval
    with telemetry.step(request_id=request_id, project_id=project_id, name="qdrant_search"):
        raw_candidates = _qdrant_dense(project_id, query_vec, DENSE_PREFETCH)

    # 4) Rerank (MMR)
    reranked = _maximal_marginal_relevance(
        query_vec=query_vec,
        candidates=raw_candidates,
        top_k=TOP_K,
        lambda_mult=MMR_LAMBDA,
    )

    # 5) Stitch (budget: MAX_CONTEXT_TOKENS - static_tokens_est)
    dense_budget = max(0, MAX_CONTEXT_TOKENS - static_tokens_est)
    (
        ontology_dict,
        context_dict,
        selected_count,
        dynamic_tokens_est,
        dropped_budget,
        dropped_no_content,
    ) = _stitch_context_structured(
        candidates=reranked,
        max_tokens=dense_budget,
        model=model,
    )

    # Extract Last N turns
    dialogue_history = [
        {"role": m.role, "content": m.content} 
        for m in recent_messages[-4:]
    ]

    # 6) Construct Canonical Envelope
    envelope = {
        "policy_layer": static_rules,
        "enforcement_protocol": {
            "steps": [
                "1. Parse the entire canonical envelope before generating output.",
                "2. Treat policy_layer as non-overridable behavioral and stylistic authority.",
                "3. Ground factual claims first in system_ontology and retrieval_context.",
                "4. If retrieved context is insufficient for general engineering or scientific queries, synthesize using established parametric knowledge.",
                "5. Never allow parametric knowledge to silently override or contradict system_ontology or policy_layer.",
                "6. Use dialogue_state only for continuity, not authority.",
                "7. Interpret current_objective precisely without expanding its scope.",
                "8. Before finalizing output, verify structural and policy compliance.",
                "9. If any constraint is violated, correct internally before emitting output."
            ]
        },
        "system_ontology": ontology_dict,
        "retrieval_context": context_dict,
        "dialogue_state": {
            "recent_turns": dialogue_history
        },
        "current_objective": {
            "instruction": query
        },
        "final_reminder": (
            "Final validation required: output must strictly comply with policy_layer, "
            "follow enforcement_protocol, and remain within current_objective scope. "
            "Distinguish clearly between retrieved architectural facts and general parametric knowledge. "
            "Non-compliant output is invalid."
        )
    }

    final_text = json.dumps(envelope, indent=2)
    context_tokens_est = static_tokens_est + dynamic_tokens_est

    log.info(
        "context.assembly_complete request_id=%s static_tokens_est=%d dynamic_tokens_est=%d context_tokens_est=%d",
        request_id, static_tokens_est, dynamic_tokens_est, context_tokens_est
    )

    if DEBUG_PROMPTS:
        log.info("debug.context_assembly request_id=%s final_text=\n%s", request_id, final_text)

    return (
        final_text,
        len(raw_candidates),
        selected_count,
        context_tokens_est,
        static_tokens_est,
        dynamic_tokens_est,
        dropped_budget,
        dropped_no_content,
    )


# ------------------------------------------------------------------------------
# Builder Helpers
# ------------------------------------------------------------------------------

_default_model_cache: Optional[str] = None

def _normalize_builder_base(url: str) -> str:
    u = url.rstrip("/")
    if u.endswith("/v1"):
        return u[:-3]
    return u

def _builder_openai_url(path: str) -> str:
    base = _normalize_builder_base(BUILDER_BASE_URL)
    return f"{base}/v1{path}"

def _get_builder_default_model() -> str:
    global _default_model_cache
    if BUILDER_MODEL:
        return BUILDER_MODEL
    if _default_model_cache:
        return _default_model_cache

    r = requests.get(_builder_openai_url("/models"), timeout=15)
    r.raise_for_status()
    data = r.json().get("data") or []
    if not data or not data[0].get("id"):
        raise RuntimeError("builder /v1/models invalid; set BUILDER_MODEL")
    _default_model_cache = data[0]["id"]
    return _default_model_cache


# ------------------------------------------------------------------------------
# Steward
# ------------------------------------------------------------------------------

def _async_admit(request_id: str, project_id: str, messages: List[Dict[str, str]]):
    if not STEWARD_URL:
        return

    def run():
        h = telemetry.step_begin(request_id=request_id, project_id=project_id, name="steward_async_call")
        try:
            r = requests.post(
                f"{STEWARD_URL}/admit",
                json={"request_id": request_id, "project_id": project_id, "messages": messages},
                timeout=20,
            )
            telemetry.step_end(
                handle=h,
                ok=r.ok,
                http_status=r.status_code,
                error_detail=None if r.ok else (r.text or "")[:500],
            )
        except Exception as e:
            telemetry.step_end(handle=h, ok=False, error_detail=str(e))

    threading.Thread(target=run, daemon=True).start()


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": BUILDER_MODEL or "homel-model",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "memory-router",
            }
        ]
    }

@app.post("/v1/chat/completions")
def chat(req: ChatCompletionRequest, http_req: Request):
    request_id = uuid.uuid4().hex
    pid = _project_id(http_req)
    origin = _origin_base(http_req)
    model_requested = (req.model or "").strip() or None

    try:
        user_text = next(m.content for m in reversed(req.messages) if m.role == "user")
    except StopIteration:
        return {"choices": [{"message": {"role": "assistant", "content": "Ready."}}]}

    # ------------------------------------------------------------------
    # GLAP INTERCEPT (Control Plane Path)
    # ------------------------------------------------------------------
    if user_text.strip().lower().startswith("/glap"):
        http_status, response = handle_glap(user_text, pid)

        if req.stream:
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            return StreamingResponse(_glap_stream_generator(content), media_type="text/event-stream")

        return JSONResponse(status_code=http_status, content=response)

    telemetry.request_begin(
        request_id=request_id,
        project_id=pid,
        origin=origin,
        origin_hash=None,
        model_requested=model_requested,
        decided_mode=req.mode,
        context_budget_max=MAX_CONTEXT_TOKENS,
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
        model = BUILDER_MODEL or _get_builder_default_model()
        model_sent = model

        # ------------------------------------------------------------------
        # GLOBAL TOKEN BUDGET ENFORCEMENT
        # ------------------------------------------------------------------
        user_text_tokens = _count_tokens(model, user_text)
        history_msgs = req.messages[:-1]
        
        # Reserve budget for RAG + Canonical Envelope + Final Message + Buffer
        allowed_history_tokens = MAX_TOTAL_TOKENS - MAX_CONTEXT_TOKENS - user_text_tokens - 200 
        
        pruned_history = []
        current_hist_tokens = 0
        
        # Slide window backwards to keep most recent context
        for m in reversed(history_msgs):
            m_tok = _count_tokens(model, m.content)
            if current_hist_tokens + m_tok > allowed_history_tokens:
                break
            pruned_history.insert(0, m)
            current_hist_tokens += m_tok
            
        builder_messages = pruned_history + [req.messages[-1]]

        # ------------------------------------------------------------------
        # CONTEXT ASSEMBLY
        # ------------------------------------------------------------------

        (
            system_ctx,
            dense_candidates,
            selected_topk,
            context_tokens_est,
            static_tokens_est,
            dynamic_tokens_est,
            dropped_budget,
            dropped_no_content,
        ) = _assemble_context(
            request_id=request_id,
            project_id=pid,
            query=user_text,
            model=model,
            recent_messages=pruned_history,
            mode=req.mode,
        )

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

        upstream_msgs: List[Dict[str, str]] = []
        if system_ctx.strip():
            upstream_msgs.append({"role": "system", "content": system_ctx})
        upstream_msgs.extend([m.model_dump() for m in req.messages])

        if DEBUG_PROMPTS:
            log.info("debug.prompt request_id=%s upstream_msgs=%s", request_id, json.dumps(upstream_msgs, indent=2))

        prompt_tokens = sum(_count_tokens(model, m["content"]) for m in upstream_msgs)
        log.info("prompt.tokens=%d model=%s request_id=%s", prompt_tokens, model, request_id)

        payload = {
            "model": model,
            "messages": upstream_msgs,
            "temperature": req.temperature,
            "stream": False,
        }

        resp: Dict[str, Any] = {}
        assistant = ""

        for attempt in (1, 2):
            step_name = "builder_chat" if attempt == 1 else "builder_chat_retry_empty"
            with telemetry.step(request_id=request_id, project_id=pid, name=step_name):
                r = requests.post(
                    _builder_openai_url("/chat/completions"),
                    headers={"Authorization": f"Bearer {BUILDER_API_KEY}"},
                    json=payload,
                    timeout=180,
                )
                http_status = r.status_code

                if not r.ok:
                    error_kind = "builder_error"
                    error_detail = (r.text or "")[:1000]
                    log.error(
                        "builder.error status=%s body=%s request_id=%s",
                        r.status_code,
                        r.text,
                        request_id,
                    )
                    r.raise_for_status()

                resp = r.json()
                assistant = (((resp.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""

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
                (json.dumps(resp)[:2000] if resp else ""),
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
            messages=[
                {"role": "user", "content": user_text},
            ],
        )

        log.info(
            "admit.request_id=%s project_id=%s user_text=%s",
            request_id, pid, user_text,
        )

        if req.stream:
            def sse():
                ts = int(time.time())
                chunk_id = f"chat-{ts}"

                yield (
                    "data: "
                    + json.dumps(
                        {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {
                                        "role": "assistant",
                                        "content": assistant,
                                    },
                                    "finish_reason": None,
                                }
                            ],
                        }
                    )
                    + "\n\n"
                )

                yield (
                    "data: "
                    + json.dumps(
                        {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": ts,
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": "stop",
                                }
                            ],
                        }
                    )
                    + "\n\n"
                )

                yield "data: [DONE]\n\n"

            return StreamingResponse(sse(), media_type="text/event-stream")

        return resp

    except Exception as e:
        if http_status is None:
            http_status = 500
        if error_kind is None:
            error_kind = "router_exception"
            error_detail = str(e)
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
            total_tokens=((prompt_tokens or 0) + (completion_tokens or 0)) if (prompt_tokens is not None or completion_tokens is not None) else None,
            context_budget_max=MAX_CONTEXT_TOKENS,
            static_tokens_est=static_tokens_est if 'static_tokens_est' in locals() else None,
            dynamic_tokens_est=dynamic_tokens_est if 'dynamic_tokens_est' in locals() else None,
        )
