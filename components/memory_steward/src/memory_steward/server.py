from __future__ import annotations

import os
import json
import hashlib
import re
import logging
import uuid
from typing import Any, Dict, List, Literal, Optional
from collections import Counter

import psycopg
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from memory_steward.telemetry import StewardTelemetryWriter

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
POSTGRES_APPNAME = _opt("POSTGRES_APPLICATION_NAME", "memory-steward")

POSTGRES_DSN = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    f"?sslmode={POSTGRES_SSLMODE}&application_name={POSTGRES_APPNAME}"
)

QDRANT_URL = _svc_url("QDRANT_SERVICE_HOST", "QDRANT_SERVICE_PORT")
EMBEDDINGS_URL = _svc_url("EMBEDDINGS_SERVICE_HOST", "EMBEDDINGS_SERVICE_PORT")
QDRANT_COLLECTION = _req("QDRANT_COLLECTION")

STEWARD_LLM_BASE_URL = _req("STEWARD_LLM_BASE_URL").rstrip("/")
STEWARD_LLM_API_KEY = _opt("STEWARD_LLM_API_KEY", "local-token")
STEWARD_MODEL = _opt("STEWARD_MODEL", "").strip()

SPECULATIVE_RE = re.compile(
    r"\b(i think|probably|might|may|seems|guess|possibly|unclear)\b",
    re.IGNORECASE,
)

# ------------------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("uvicorn.error")

telemetry = StewardTelemetryWriter(POSTGRES_DSN)

app = FastAPI(title="homel-memory-steward", version="0.2")

# ------------------------------------------------------------------------------
# API Models
# ------------------------------------------------------------------------------

class AdmitTurnRequest(BaseModel):
    """Incoming ordinary-chat admission request from Memory Router."""

    request_id: str = Field(..., min_length=1)
    project_id: str = Field(..., min_length=1)
    scope: Optional[str] = None
    messages: List[Dict[str, str]]
    evidence_type: Optional[str] = None
    evidence_ref: Optional[str] = None
    max_fragments: int = Field(default=12, ge=1, le=64)


class AgentArtifact(BaseModel):
    artifact_type: str = Field(..., min_length=1, max_length=128)
    schema_version: str = Field(..., min_length=1, max_length=64)
    producer_type: Literal["agent", "analyzer", "tool"]
    producer_version: str = Field(..., min_length=1, max_length=128)
    content_hash: str = Field(..., min_length=64, max_length=64)
    payload: Any
    repository: Optional[str] = Field(default=None, max_length=1024)
    revision: Optional[str] = Field(default=None, max_length=256)
    producer_name: Optional[str] = Field(default=None, max_length=256)
    provenance: List[Any] = Field(default_factory=list)


class AgentOutcomeRequest(BaseModel):
    outcome_id: str = Field(..., min_length=1, max_length=256)
    project_id: str = Field(..., min_length=1, max_length=256)
    task_id: Optional[str] = Field(default=None, max_length=256)
    session_id: Optional[str] = Field(default=None, max_length=256)
    context_request_id: Optional[str] = Field(default=None, max_length=256)
    objective: str = Field(..., min_length=1)
    result: Any
    decisions: List[Any] = Field(default_factory=list)
    findings: List[Any] = Field(default_factory=list)
    verification: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[AgentArtifact] = Field(default_factory=list)
    repository_state: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[Any] = Field(default_factory=list)
    scope: Optional[str] = None
    admit_knowledge: bool = True
    max_fragments: int = Field(default=12, ge=1, le=64)


class ContextFeedbackRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=256)
    context_request_id: str = Field(..., min_length=1, max_length=256)
    feedback_id: Optional[str] = Field(default=None, max_length=256)
    task_id: Optional[str] = Field(default=None, max_length=256)
    session_id: Optional[str] = Field(default=None, max_length=256)
    used_memory_ids: List[str] = Field(default_factory=list)
    irrelevant_memory_ids: List[str] = Field(default_factory=list)
    missing_context: Optional[str] = Field(default=None, max_length=4000)


@app.get("/healthz")
def healthz():
    return {"ok": True}

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

def _pg():
    return psycopg.connect(POSTGRES_DSN)


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _point_uuid(project_id: str, content: str) -> str:
    # Qdrant point id MUST be UUID or integer; keep deterministic/stable.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{project_id}\n{content}"))


def _embed(texts: List[str]) -> List[List[float]]:
    """
    Embed extracted fragments using embeddings service.
    """
    r = requests.post(
        f"{EMBEDDINGS_URL}/embed",
        json={"texts": texts, "normalize": True},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["vectors"]


def _extract(messages: List[Dict[str, str]], limit: int) -> List[str]:
    """
    Ask Steward LLM to extract atomic factual fragments.
    Canonical Envelope mapping compliant with Doc 04, Section 10.3.
    """

    # Collect user content deterministically
    user_inputs = [
        m["content"]
        for m in messages
        if m.get("role") == "user" and m.get("content")
    ]

    conversation_text = "\n".join(user_inputs).strip()

    
    envelope = {
        "policy_layer": {
            "admission_rules": [
                "Extract atomic, high-signal facts only.",
                "Store only stable user-asserted facts.",
                "Reject transient or emotional language.",
                "Detect contradictions with existing memory.",
                "Ignore conversational noise and pleasantries.",
                "If at least one stable fact exists, you MUST extract it."
            ]
        },
        "enforcement_protocol": {
            "steps": [
                "1. Read policy_layer.",
                "2. Interpret current_objective.",
                "3. Analyze current_objective.new_input.",
                "4. Extract factual statements matching admission_rules.",
                "5. Produce strict JSON decision."
            ]
        },
        "system_ontology": {
            "project_name": "Memory Steward",
            "role": "Control Plane Governance"
        },
        "retrieval_context": {},
        "dialogue_state": {},
        "current_objective": {
            "task": "memory_admission",
            "new_input": conversation_text,
            "max_fragments_allowed": limit,
            "decision_required": [
                "extract_facts",
                "detect_updates",
                "ignore_noise"
            ]
        },
        "final_reminder": (
            'Output MUST be strict JSON matching schema: {"fragments": ["..."]}.'
            'Do not output explanations.'
        )
    }

    canonical_envelope_str = json.dumps(envelope, indent=2)


    payload = {
        "model": STEWARD_MODEL,
        "messages": [
            {
                "role": "system",
                "content": canonical_envelope_str,
            }
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    """
    payload = {
        "model": STEWARD_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the Control Plane Governance API. Execute the extraction task "
                    "defined in the following JSON configuration against the user's messages:\n\n"
                    f"{canonical_envelope_str}\n\n"
                    "EXAMPLE OUTPUT:\n"
                    "{\"fragments\": [\"User's primary programming language is Python.\"]}"
                ),
            }
        ] + messages,
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    """
    r = requests.post(
        f"{STEWARD_LLM_BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {STEWARD_LLM_API_KEY}"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()

    frags = json.loads(r.json()["choices"][0]["message"]["content"]).get("fragments", [])[:limit]

    log.info("payload=%s, fragments=%s", payload, frags)

    #return json.loads(
    #    r.json()["choices"][0]["message"]["content"]
    #).get("fragments", [])[:limit]
    return frags

def _extract_agent_outcome(req: AgentOutcomeRequest) -> List[str]:
    """Extract durable knowledge candidates from structured agent execution evidence."""
    outcome_view = {
        "objective": req.objective,
        "result": req.result,
        "decisions": req.decisions,
        "findings": req.findings,
        "verification": req.verification,
        "repository_state": req.repository_state,
        "evidence": req.evidence,
    }
    envelope = {
        "policy_layer": {
            "admission_rules": [
                "Extract only durable reusable claims, decisions, and verified findings.",
                "Do not promote transient execution progress, file lists, logs, or raw artifacts to learned facts.",
                "Prefer claims supported by verification or explicit evidence references.",
                "Do not treat an agent assertion as verified merely because it is structured.",
                "Keep each fragment atomic and independently understandable.",
            ]
        },
        "current_objective": {
            "task": "agent_outcome_memory_admission",
            "max_fragments_allowed": req.max_fragments,
            "outcome": outcome_view,
        },
        "final_reminder": 'Output strict JSON only: {"fragments": ["..."]}.',
    }
    payload = {
        "model": STEWARD_MODEL,
        "messages": [{"role": "system", "content": json.dumps(envelope, indent=2)}],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
    }
    r = requests.post(
        f"{STEWARD_LLM_BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {STEWARD_LLM_API_KEY}"},
        json=payload,
        timeout=120,
    )
    r.raise_for_status()
    decoded = json.loads(r.json()["choices"][0]["message"]["content"])
    fragments = decoded.get("fragments", [])
    if not isinstance(fragments, list):
        raise ValueError("agent outcome extractor returned non-list fragments")
    return [str(x).strip() for x in fragments if str(x).strip()][: req.max_fragments]


def _canonical_payload_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return _hash(encoded)


# ------------------------------------------------------------------------------
# Lexical Sparse Encoder (TF sparse vectors, minimal)
# ------------------------------------------------------------------------------

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

# Global in-memory vocab (MVP)
# TODO: persist in Postgres or external store
_sparse_vocab: Dict[str, int] = {}


def _tokenize_lexical(text: str) -> List[str]:
    return TOKEN_RE.findall(text.lower())


def _sparse_vector(text: str) -> Dict[str, List[float]]:
    """
    Build sparse vector {indices, values} using term frequency.
    """
    tokens = _tokenize_lexical(text)
    counts = Counter(tokens)

    indices: List[int] = []
    values: List[float] = []

    for token, tf in counts.items():
        if token not in _sparse_vocab:
            _sparse_vocab[token] = len(_sparse_vocab)

        indices.append(_sparse_vocab[token])
        values.append(float(tf))

    return {"indices": indices, "values": values}

# ------------------------------------------------------------------------------
# Shared admission persistence and AMP endpoints
# ------------------------------------------------------------------------------


def _persist_dynamic_fragments(
    *,
    project_id: str,
    scope: Optional[str],
    fragments: List[str],
    evidence_type: Optional[str],
    evidence_ref: Optional[str],
) -> tuple[int, int]:
    if not fragments:
        return 0, 0

    vecs = _embed(fragments)
    points: List[Dict[str, Any]] = []
    inserted = 0

    with _pg() as conn, conn.cursor() as cur:
        for i, content in enumerate(fragments):
            speculative = bool(SPECULATIVE_RE.search(content))
            high_conf = (not speculative) and bool(evidence_type)
            content_hash = _hash(project_id + content)
            point_id = _point_uuid(project_id, content)
            cur.execute(
                """
                INSERT INTO dynamic_memory
                  (project_id, scope, type, content, content_hash,
                   high_confidence, evidence_type, evidence_ref, qdrant_point_id)
                VALUES (%s,%s,'fact',%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (
                    project_id, scope, content, content_hash, high_conf,
                    evidence_type, evidence_ref, point_id,
                ),
            )
            inserted += cur.rowcount
            points.append(
                {
                    "id": point_id,
                    "vector": {"dense": vecs[i], "lexical": _sparse_vector(content)},
                    "payload": {
                        "memory_type": "dynamic_memory",
                        "project_id": project_id,
                        "content": content,
                        "content_hash": content_hash,
                        "high_confidence": high_conf,
                        "evidence_type": evidence_type,
                        "evidence_ref": evidence_ref,
                    },
                }
            )

    if points:
        r = requests.put(
            f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points?wait=true",
            json={"points": points},
            timeout=60,
        )
        if not r.ok:
            log.error(
                "qdrant.upsert_failed status=%s body=%s",
                r.status_code,
                (r.text or "")[:2000],
            )
        r.raise_for_status()
    return inserted, len(points)


def _repository_identity(artifact: AgentArtifact, state: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    repository = artifact.repository or state.get("repository") or state.get("repo")
    revision = (
        artifact.revision
        or state.get("revision")
        or state.get("tree_hash")
        or state.get("commit_sha")
        or state.get("commit")
    )
    return (str(repository) if repository else None, str(revision) if revision else None)


def _persist_agent_artifacts(req: AgentOutcomeRequest) -> tuple[int, List[str]]:
    inserted = 0
    artifact_ids: List[str] = []
    if not req.artifacts:
        return 0, artifact_ids

    with _pg() as conn, conn.cursor() as cur:
        for artifact in req.artifacts:
            actual_hash = _canonical_payload_hash(artifact.payload)
            if artifact.content_hash.lower() != actual_hash:
                raise HTTPException(
                    status_code=422,
                    detail=f"artifact content_hash mismatch for {artifact.artifact_type}",
                )
            repository, revision = _repository_identity(artifact, req.repository_state)
            identity = {
                "project_id": req.project_id,
                "repository": repository,
                "revision": revision,
                "artifact_type": artifact.artifact_type,
                "schema_version": artifact.schema_version,
                "producer_type": artifact.producer_type,
                "producer_name": artifact.producer_name,
                "producer_version": artifact.producer_version,
                "content_hash": actual_hash,
            }
            artifact_key = _canonical_payload_hash(identity)
            cur.execute(
                """
                INSERT INTO agent_reference (
                  project_id, artifact_key, repository, revision, artifact_type,
                  schema_version, producer_type, producer_name, producer_version,
                  content_hash, payload, provenance, source_outcome_id
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                ON CONFLICT (project_id, artifact_key) DO NOTHING
                RETURNING id
                """,
                (
                    req.project_id, artifact_key, repository, revision,
                    artifact.artifact_type, artifact.schema_version, artifact.producer_type,
                    artifact.producer_name, artifact.producer_version, actual_hash,
                    json.dumps(artifact.payload, ensure_ascii=False),
                    json.dumps(artifact.provenance, ensure_ascii=False),
                    req.outcome_id,
                ),
            )
            row = cur.fetchone()
            if row:
                inserted += 1
                artifact_ids.append(str(row[0]))
            else:
                cur.execute(
                    "SELECT id FROM agent_reference WHERE project_id=%s AND artifact_key=%s",
                    (req.project_id, artifact_key),
                )
                existing = cur.fetchone()
                if existing:
                    artifact_ids.append(str(existing[0]))
    return inserted, artifact_ids


def _prepare_outcome(req: AgentOutcomeRequest) -> Optional[Dict[str, Any]]:
    """Reserve idempotency identity or return the completed result for a replay.

    The row is locked while request identity is checked, so the same outcome_id
    cannot be reused with a different payload under concurrency.
    """
    request_payload = req.model_dump(mode="json")
    request_hash = _canonical_payload_hash(request_payload)
    payload_json = json.dumps(request_payload, ensure_ascii=False)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO agent_outcome_submission (
              project_id, outcome_id, task_id, session_id, context_request_id,
              objective, request_hash, request_payload, status, error_detail, updated_at
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'processing',NULL,now())
            ON CONFLICT (project_id, outcome_id) DO NOTHING
            """,
            (
                req.project_id, req.outcome_id, req.task_id, req.session_id,
                req.context_request_id, req.objective, request_hash, payload_json,
            ),
        )
        cur.execute(
            """
            SELECT status, request_hash, result_payload
            FROM agent_outcome_submission
            WHERE project_id=%s AND outcome_id=%s
            FOR UPDATE
            """,
            (req.project_id, req.outcome_id),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError("agent outcome idempotency row missing after insert")
        status, stored_hash, result_payload = row
        if stored_hash != request_hash:
            raise HTTPException(
                status_code=409,
                detail="outcome_id already exists with a different request payload",
            )
        if status == "complete" and result_payload is not None:
            if isinstance(result_payload, str):
                result_payload = json.loads(result_payload)
            return dict(result_payload)

        cur.execute(
            """
            UPDATE agent_outcome_submission
            SET task_id=%s, session_id=%s, context_request_id=%s, objective=%s,
                status='processing', error_detail=NULL, updated_at=now()
            WHERE project_id=%s AND outcome_id=%s
            """,
            (
                req.task_id, req.session_id, req.context_request_id, req.objective,
                req.project_id, req.outcome_id,
            ),
        )
    return None


def _mark_outcome_complete(req: AgentOutcomeRequest, result: Dict[str, Any]) -> None:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            UPDATE agent_outcome_submission
            SET status='complete', result_payload=%s::jsonb, error_detail=NULL, updated_at=now()
            WHERE project_id=%s AND outcome_id=%s
            """,
            (json.dumps(result, ensure_ascii=False), req.project_id, req.outcome_id),
        )


def _mark_outcome_failed(req: AgentOutcomeRequest, detail: str) -> None:
    try:
        with _pg() as conn, conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_outcome_submission
                SET status='failed', error_detail=%s, updated_at=now()
                WHERE project_id=%s AND outcome_id=%s AND status <> 'complete'
                """,
                (detail[:2000], req.project_id, req.outcome_id),
            )
    except Exception as exc:
        log.warning("failed to record agent outcome failure: %s", exc)


@app.post("/admit")
def admit(req: AdmitTurnRequest):
    fragments_extracted = 0
    fragments_inserted = 0
    qdrant_upserts = 0
    ok = True
    error_detail: Optional[str] = None
    try:
        fragments = _extract(req.messages, req.max_fragments)
        fragments_extracted = len(fragments)
        fragments_inserted, qdrant_upserts = _persist_dynamic_fragments(
            project_id=req.project_id,
            scope=req.scope,
            fragments=fragments,
            evidence_type=req.evidence_type,
            evidence_ref=req.evidence_ref,
        )
        return {"ok": True, "inserted": fragments_inserted}
    except Exception as exc:
        ok = False
        error_detail = str(exc)
        log.exception("memory-steward admission failed")
        raise HTTPException(status_code=500, detail="admission failed") from exc
    finally:
        telemetry.admission_write(
            request_id=req.request_id,
            project_id=req.project_id,
            fragments_extracted=fragments_extracted,
            fragments_inserted=fragments_inserted,
            qdrant_upserts=qdrant_upserts,
            ok=ok,
            error_detail=error_detail,
        )


@app.post("/v1/agent/outcomes")
def submit_agent_outcome(req: AgentOutcomeRequest):
    fragments_extracted = 0
    fragments_inserted = 0
    artifacts_inserted = 0
    qdrant_upserts = 0
    replay = False
    ok = True
    error_detail: Optional[str] = None

    try:
        completed = _prepare_outcome(req)
        if completed is not None:
            replay = True
            return {**completed, "idempotent_replay": True}

        # Reusable artifacts are a lower-authority evidence/reference lane. Persist
        # them independently of the Steward LLM so deterministic analyzer output
        # remains available even when durable-knowledge extraction is unavailable.
        artifacts_inserted, artifact_ids = _persist_agent_artifacts(req)

        if req.admit_knowledge:
            fragments = _extract_agent_outcome(req)
            fragments_extracted = len(fragments)
            evidence_type = "agent_outcome_verified" if (req.verification or req.evidence) else "agent_outcome"
            evidence_ref = req.context_request_id or req.outcome_id
            fragments_inserted, qdrant_upserts = _persist_dynamic_fragments(
                project_id=req.project_id,
                scope=req.scope,
                fragments=fragments,
                evidence_type=evidence_type,
                evidence_ref=evidence_ref,
            )

        response = {
            "ok": True,
            "outcome_id": req.outcome_id,
            "project_id": req.project_id,
            "context_request_id": req.context_request_id,
            "fragments_extracted": fragments_extracted,
            "fragments_inserted": fragments_inserted,
            "artifacts_received": len(req.artifacts),
            "artifacts_inserted": artifacts_inserted,
            "artifact_ids": artifact_ids,
            "knowledge_admission_requested": req.admit_knowledge,
            "idempotent_replay": False,
        }
        _mark_outcome_complete(req, response)
        return response
    except HTTPException as exc:
        ok = False
        error_detail = str(exc.detail)
        if exc.status_code != 409:
            _mark_outcome_failed(req, error_detail)
        raise
    except Exception as exc:
        ok = False
        error_detail = str(exc)
        _mark_outcome_failed(req, error_detail)
        log.exception("agent outcome admission failed outcome_id=%s", req.outcome_id)
        raise HTTPException(status_code=500, detail="agent outcome admission failed") from exc
    finally:
        telemetry.agent_outcome_write(
            outcome_id=req.outcome_id,
            project_id=req.project_id,
            context_request_id=req.context_request_id,
            fragments_extracted=fragments_extracted,
            fragments_inserted=fragments_inserted,
            artifacts_received=len(req.artifacts),
            artifacts_inserted=artifacts_inserted,
            qdrant_upserts=qdrant_upserts,
            idempotent_replay=replay,
            ok=ok,
            error_detail=error_detail,
        )


@app.post("/v1/context/feedback")
def submit_context_feedback(req: ContextFeedbackRequest):
    feedback_id = req.feedback_id or uuid.uuid4().hex
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO context_feedback (
              feedback_id, context_request_id, project_id, used_memory_ids,
              irrelevant_memory_ids, missing_context, task_id, session_id
            )
            VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)
            ON CONFLICT (feedback_id) DO NOTHING
            """,
            (
                feedback_id, req.context_request_id, req.project_id,
                json.dumps(req.used_memory_ids), json.dumps(req.irrelevant_memory_ids),
                req.missing_context, req.task_id, req.session_id,
            ),
        )
    telemetry.context_feedback_write(
        feedback_id=feedback_id,
        context_request_id=req.context_request_id,
        project_id=req.project_id,
        used_count=len(req.used_memory_ids),
        irrelevant_count=len(req.irrelevant_memory_ids),
        missing_context_reported=bool(req.missing_context),
    )
    return {"ok": True, "feedback_id": feedback_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("memory_steward.server:app", host="0.0.0.0", port=8090, reload=False)
