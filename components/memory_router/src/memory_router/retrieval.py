from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import requests
import tiktoken
from sklearn.metrics.pairwise import cosine_similarity

from memory_router import config
from memory_router.schemas import REFERENCE_FILTER_FIELDS, ArtifactSelector, Candidate, ChatMessage
from memory_router.state import telemetry

log = logging.getLogger("uvicorn.error")
_tokenizer_cache: Dict[str, tiktoken.Encoding] = {}


def count_tokens(model: str, text: str) -> int:
    if model not in _tokenizer_cache:
        try:
            _tokenizer_cache[model] = tiktoken.encoding_for_model(model)
        except KeyError:
            _tokenizer_cache[model] = tiktoken.get_encoding("cl100k_base")
    return len(_tokenizer_cache[model].encode(text))


def pg_static_load(mode: Optional[str] = None) -> List[Tuple[str, str, str]]:
    rows: List[Tuple[str, str, str]] = []
    with config.pg_connect() as conn, conn.cursor() as cur:
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
        for row_id, content, row_mode in cur.fetchall():
            if content:
                rows.append((str(row_id), str(content), str(row_mode)))
    return rows


def extract_static_rules(static_rows: List[Tuple[str, str, str]]) -> Dict[str, List[str]]:
    rules = {"global": [], "mode": []}
    for _, content, row_mode in static_rows:
        clean_content = content.replace("\n", " ").strip()
        if row_mode == "global":
            rules["global"].append(clean_content)
        else:
            rules["mode"].append(clean_content)
    return rules


def pg_agent_reference_load(
    project_id: str, selectors: List[ArtifactSelector]
) -> List[Dict[str, Any]]:
    artifacts: List[Dict[str, Any]] = []
    if not selectors:
        return artifacts

    with config.pg_connect() as conn, conn.cursor() as cur:
        for selector in selectors:
            where = ["project_id = %s", "artifact_type = %s"]
            params: List[Any] = [project_id, selector.artifact_type]
            for column, value in (
                ("repository", selector.repository),
                ("revision", selector.revision),
                ("schema_version", selector.schema_version),
                ("producer_type", selector.producer_type),
                ("content_hash", selector.content_hash),
            ):
                if value is not None:
                    where.append(f"{column} = %s")
                    params.append(value)
            cur.execute(
                f"""
                SELECT id, repository, revision, artifact_type, schema_version,
                       producer_type, producer_name, producer_version, content_hash,
                       payload, provenance, source_outcome_id, created_at
                FROM agent_reference
                WHERE {' AND '.join(where)}
                ORDER BY created_at DESC
                LIMIT 1
                """,
                params,
            )
            row = cur.fetchone()
            if not row:
                continue
            payload = row[9]
            provenance = row[10]
            if isinstance(payload, str):
                payload = json.loads(payload)
            if isinstance(provenance, str):
                provenance = json.loads(provenance)
            artifacts.append(
                {
                    "id": str(row[0]),
                    "repository": row[1],
                    "revision": row[2],
                    "artifact_type": row[3],
                    "schema_version": row[4],
                    "producer_type": row[5],
                    "producer_name": row[6],
                    "producer_version": row[7],
                    "content_hash": row[8],
                    "payload": payload,
                    "provenance": provenance,
                    "source_outcome_id": row[11],
                    "created_at": row[12].isoformat()
                    if hasattr(row[12], "isoformat")
                    else str(row[12]),
                }
            )
    return artifacts


def embed_one(text: str) -> List[float]:
    response = requests.post(
        f"{config.EMBEDDINGS_URL}/embed",
        json={"texts": [text], "normalize": True},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["vectors"][0]


def qdrant_dense(project_id: str, vec: List[float], limit: int) -> List[Candidate]:
    payload = {
        "vector": {"name": "dense", "vector": vec},
        "limit": limit,
        "with_payload": True,
        "with_vector": True,
        "filter": {
            "must": [
                {"key": "project_id", "match": {"value": project_id}},
                {"key": "memory_type", "match": {"value": "dynamic_memory"}},
            ]
        },
    }
    try:
        response = requests.post(
            f"{config.QDRANT_URL}/collections/{config.QDRANT_COLLECTION}/points/search",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("result", []) or []
        candidates: List[Candidate] = []
        for result in results:
            metadata = result.get("payload") or {}
            content = metadata.get("content")
            if not content:
                continue
            vector = result.get("vector")
            if isinstance(vector, dict):
                vector = vector.get("dense") or vector.get("vector")
            if not vector:
                continue
            candidates.append(
                Candidate(
                    id=str(result.get("id")),
                    content=str(content),
                    vector=list(vector),
                    metadata=metadata,
                )
            )
        return candidates
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            log.warning("Qdrant collection missing, skipping dense recall")
            return []
        raise


def qdrant_reference(
    vec: List[float],
    limit: int,
    reference_filters: dict[str, str] | None = None,
) -> List[Candidate]:
    must: List[Dict[str, Any]] = [
        {"key": "memory_type", "match": {"value": "reference_memory"}}
    ]
    filters = reference_filters or {}
    unknown = sorted(set(filters) - set(REFERENCE_FILTER_FIELDS))
    if unknown:
        raise ValueError(f"unsupported reference filter(s): {', '.join(unknown)}")
    for field, value in filters.items():
        must.append(
            {"key": REFERENCE_FILTER_FIELDS[field], "match": {"value": value}}
        )

    payload = {
        "vector": {"name": "dense", "vector": vec},
        "limit": limit,
        "with_payload": True,
        "with_vector": True,
        "filter": {"must": must},
    }
    try:
        response = requests.post(
            f"{config.QDRANT_URL}/collections/{config.QDRANT_COLLECTION}/points/search",
            json=payload,
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("result", []) or []
        candidates: List[Candidate] = []
        for result in results:
            metadata = result.get("payload") or {}
            content = metadata.get("content")
            if not content:
                continue
            vector = result.get("vector")
            if isinstance(vector, dict):
                vector = vector.get("dense") or vector.get("vector")
            if not vector:
                continue
            reference_source = metadata.get("source")
            metadata = {
                **metadata,
                "namespace": "reference",
                "reference_source": reference_source,
                "source": f'{metadata.get("product", "ref")}@{metadata.get("version", "?")}',
            }
            candidates.append(
                Candidate(
                    id=str(result.get("id")),
                    content=str(content),
                    vector=list(vector),
                    metadata=metadata,
                    score=result.get("score"),
                )
            )
        return candidates
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            log.warning("Qdrant collection missing, skipping reference recall")
            return []
        raise


def reference_candidate_payload(candidate: Candidate) -> Dict[str, Any]:
    metadata = candidate.metadata or {}
    return {
        "id": candidate.id,
        "score": candidate.score,
        "memory_type": metadata.get("memory_type"),
        "content": candidate.content,
        "product": metadata.get("product"),
        "version": metadata.get("version"),
        "scope": metadata.get("scope"),
        "provider": metadata.get("provider"),
        "source": metadata.get("reference_source", metadata.get("source")),
        "doc_section": metadata.get("doc_section"),
        "ref_key": metadata.get("ref_key"),
        "chunk_index": metadata.get("chunk_index"),
        "ingested_at": metadata.get("ingested_at"),
    }


def qdrant_reference_get(chunk_id: str) -> Optional[Dict[str, Any]]:
    response = requests.post(
        f"{config.QDRANT_URL}/collections/{config.QDRANT_COLLECTION}/points",
        json={"ids": [chunk_id], "with_payload": True, "with_vector": False},
        timeout=30,
    )
    response.raise_for_status()
    points = response.json().get("result", []) or []
    if not points:
        return None
    point = points[0]
    metadata = point.get("payload") or {}
    if metadata.get("memory_type") != "reference_memory":
        return None
    return {
        "id": str(point.get("id")),
        "memory_type": metadata.get("memory_type"),
        "content": metadata.get("content"),
        "product": metadata.get("product"),
        "version": metadata.get("version"),
        "scope": metadata.get("scope"),
        "provider": metadata.get("provider"),
        "source": metadata.get("source"),
        "doc_section": metadata.get("doc_section"),
        "ref_key": metadata.get("ref_key"),
        "chunk_index": metadata.get("chunk_index"),
        "ingested_at": metadata.get("ingested_at"),
    }


def maximal_marginal_relevance(
    query_vec: List[float],
    candidates: List[Candidate],
    top_k: int,
    lambda_mult: float,
) -> List[Candidate]:
    if not candidates:
        return []
    query_np = np.array(query_vec, dtype=np.float32).reshape(1, -1)
    candidate_np = np.array([candidate.vector for candidate in candidates], dtype=np.float32)
    similarity_to_query = cosine_similarity(query_np, candidate_np)[0]
    selected_indices: List[int] = []
    candidate_indices = list(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_score = -np.inf
        best_idx = -1
        for idx in candidate_indices:
            relevance = float(similarity_to_query[idx])
            if selected_indices:
                similarity_to_selected = cosine_similarity(
                    candidate_np[idx].reshape(1, -1), candidate_np[selected_indices]
                )
                redundancy = float(np.max(similarity_to_selected))
            else:
                redundancy = 0.0
            score = (lambda_mult * relevance) - ((1.0 - lambda_mult) * redundancy)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_idx != -1:
            selected_indices.append(best_idx)
            candidate_indices.remove(best_idx)
    return [candidates[idx] for idx in selected_indices]


def stitch_context_structured(
    candidates: List[Candidate],
    max_tokens: int,
    model: str,
    *,
    count_fn=None,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]], int, int, int, int]:
    if not candidates:
        return {}, {}, 0, 0, 0, 0

    count_fn = count_fn or count_tokens
    ontology_grouped: Dict[str, List[str]] = {}
    context_grouped: Dict[str, List[str]] = {}
    used_tokens = 0
    used_items = 0
    dropped_budget = 0
    dropped_no_content = 0

    for candidate in candidates:
        if not candidate.content or not candidate.content.strip():
            dropped_no_content += 1
            continue
        if candidate.token_count == 0:
            candidate.token_count = count_fn(model, candidate.content)
        cost = candidate.token_count + 5
        if used_tokens + cost > max_tokens:
            dropped_budget += 1
            continue

        metadata_source = str(candidate.metadata.get("source", "GENERAL_CONTEXT")).upper()
        namespace = str(candidate.metadata.get("namespace", metadata_source)).lower()
        group_key = metadata_source.replace("_", " ")
        clean_content = candidate.content.replace("\n", " ").strip()
        if "reference" in namespace or "doc" in namespace or "spec" in namespace:
            ontology_grouped.setdefault(group_key, []).append(clean_content)
        else:
            context_grouped.setdefault(group_key, []).append(clean_content)
        used_tokens += cost
        used_items += 1

    return (
        ontology_grouped,
        context_grouped,
        used_items,
        used_tokens,
        dropped_budget,
        dropped_no_content,
    )


def selected_candidate_refs(
    candidates: List[Candidate],
    max_tokens: int,
    model: str,
    *,
    count_fn=None,
) -> List[Dict[str, Any]]:
    count_fn = count_fn or count_tokens
    refs: List[Dict[str, Any]] = []
    used_tokens = 0
    for candidate in candidates:
        if not candidate.content or not candidate.content.strip():
            continue
        if candidate.token_count == 0:
            candidate.token_count = count_fn(model, candidate.content)
        cost = candidate.token_count + 5
        if used_tokens + cost > max_tokens:
            continue
        metadata = candidate.metadata or {}
        refs.append(
            {
                "id": candidate.id,
                "memory_type": metadata.get("memory_type"),
                "source": metadata.get("source"),
                "namespace": metadata.get("namespace"),
                "product": metadata.get("product"),
                "version": metadata.get("version"),
                "scope": metadata.get("scope"),
                "evidence_ref": metadata.get("evidence_ref"),
                "content_hash": metadata.get("content_hash"),
            }
        )
        used_tokens += cost
    return refs


def retrieve_context_structured(
    request_id: str,
    project_id: str,
    query: Optional[str],
    model: str,
    mode: Optional[str] = None,
    artifact_selectors: Optional[List[ArtifactSelector]] = None,
    reference_filters: dict[str, str] | None = None,
    *,
    pg_static_loader=None,
    pg_agent_reference_loader=None,
    embedder=None,
    dense_search=None,
    reference_search=None,
) -> Dict[str, Any]:
    pg_static_loader = pg_static_loader or pg_static_load
    pg_agent_reference_loader = pg_agent_reference_loader or pg_agent_reference_load
    embedder = embedder or embed_one
    dense_search = dense_search or qdrant_dense
    reference_search = reference_search or qdrant_reference

    with telemetry.step(request_id=request_id, project_id=project_id, name="pg_static"):
        static_rows = pg_static_loader(mode=mode)
        static_rules = extract_static_rules(static_rows)
        static_tokens_est = 200

    with telemetry.step(
        request_id=request_id, project_id=project_id, name="pg_agent_reference"
    ):
        agent_artifacts = pg_agent_reference_loader(project_id, artifact_selectors or [])

    raw_candidates: List[Candidate] = []
    reranked: List[Candidate] = []
    ontology_dict: Dict[str, List[str]] = {}
    context_dict: Dict[str, List[str]] = {}
    selected_count = 0
    dynamic_tokens_est = 0
    dropped_budget = 0
    dropped_no_content = 0
    selected_items: List[Dict[str, Any]] = []

    if query:
        with telemetry.step(request_id=request_id, project_id=project_id, name="embed"):
            query_vec = embedder(query)
        with telemetry.step(
            request_id=request_id, project_id=project_id, name="qdrant_search"
        ):
            raw_candidates = dense_search(project_id, query_vec, config.DENSE_PREFETCH)

        if config.REFERENCE_RETRIEVAL_ENABLED and (mode or "engineering") in config.REFERENCE_MODES:
            with telemetry.step(
                request_id=request_id, project_id=project_id, name="qdrant_reference"
            ):
                reference_candidates = reference_search(
                    query_vec,
                    config.DENSE_PREFETCH,
                    reference_filters=reference_filters,
                )
            raw_candidates = reference_candidates + raw_candidates

        reranked = maximal_marginal_relevance(
            query_vec=query_vec,
            candidates=raw_candidates,
            top_k=config.TOP_K,
            lambda_mult=config.MMR_LAMBDA,
        )
        dense_budget = max(0, config.effective_max_context_tokens() - static_tokens_est)
        (
            ontology_dict,
            context_dict,
            selected_count,
            dynamic_tokens_est,
            dropped_budget,
            dropped_no_content,
        ) = stitch_context_structured(reranked, dense_budget, model)
        selected_items = selected_candidate_refs(reranked, dense_budget, model)

    context_tokens_est = static_tokens_est + dynamic_tokens_est
    log.info(
        "context.retrieval_complete request_id=%s static_tokens_est=%d dynamic_tokens_est=%d context_tokens_est=%d",
        request_id,
        static_tokens_est,
        dynamic_tokens_est,
        context_tokens_est,
    )
    return {
        "policy_layer": static_rules,
        "system_ontology": ontology_dict,
        "retrieval_context": context_dict,
        "agent_reference": agent_artifacts,
        "selected_items": selected_items,
        "accounting": {
            "dense_candidates": len(raw_candidates),
            "selected_topk": selected_count,
            "context_tokens_est": context_tokens_est,
            "static_tokens_est": static_tokens_est,
            "dynamic_tokens_est": dynamic_tokens_est,
            "dropped_budget": dropped_budget,
            "dropped_no_content": dropped_no_content,
        },
    }


def render_context_envelope(
    retrieval: Dict[str, Any], query: str, recent_messages: List[ChatMessage]
) -> str:
    dialogue_history = [
        {"role": message.role, "content": message.content}
        for message in recent_messages[-4:]
    ]
    envelope = {
        "policy_layer": retrieval["policy_layer"],
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
                "9. If any constraint is violated, correct internally before emitting output.",
                (
                    "10. Operator commands (text beginning with /glap) execute ONLY "
                    "when a human submits them. You cannot run them. Never state or "
                    "imply that a file was written, a repository changed, memory was "
                    "ingested, configuration was applied, or any other side effect "
                    "occurred as a result of your output. If an operation is needed, "
                    "emit the exact /glap command on its own line and instruct the "
                    "operator to run it; printing the command does not execute it."
                ),
            ]
        },
        "system_ontology": retrieval["system_ontology"],
        "retrieval_context": retrieval["retrieval_context"],
        "dialogue_state": {"recent_turns": dialogue_history},
        "current_objective": {"instruction": query},
        "final_reminder": (
            "Final validation required: output must strictly comply with policy_layer, "
            "follow enforcement_protocol, and remain within current_objective scope. "
            "Distinguish clearly between retrieved architectural facts and general parametric knowledge. "
            "Never claim that an operator command (/glap) executed or that any side effect occurred; "
            "you may only propose commands for the operator to run. Non-compliant output is invalid."
        ),
    }
    final_text = json.dumps(envelope, indent=2)
    if config.DEBUG_PROMPTS:
        log.info("debug.context_assembly final_text=\n%s", final_text)
    return final_text


def assemble_context(
    request_id: str,
    project_id: str,
    query: str,
    model: str,
    recent_messages: List[ChatMessage],
    mode: Optional[str] = None,
) -> Tuple[str, int, int, int, int, int, int, int]:
    retrieval = retrieve_context_structured(
        request_id=request_id,
        project_id=project_id,
        query=query,
        model=model,
        mode=mode,
    )
    final_text = render_context_envelope(retrieval, query, recent_messages)
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
