"""Canonical Reference document catalog and RR Reference preflight."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

import psycopg
import requests
from fastmcp import FastMCP
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from memory_steward_mcp.config import EMBEDDINGS_URL, POSTGRES_DSN

REFERENCE_PREFLIGHT_SELECTED_COUNT = int(
    os.environ.get("REFERENCE_PREFLIGHT_SELECTED_COUNT", "8")
)
if REFERENCE_PREFLIGHT_SELECTED_COUNT < 1:
    raise RuntimeError("REFERENCE_PREFLIGHT_SELECTED_COUNT must be >= 1")

_HEADING_RE = re.compile(r"^(?P<marks>#{1,4}|={1,4})\s+(?P<title>.+?)\s*$")
_SPACE_RE = re.compile(r"\s+")


def reference_document_id(product: str, version: str, source: str) -> str:
    """Stable document identity approved for the canonical Reference catalog."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, product + version + source))


def reference_chunk_id(document_id: str, chunk_index: int, content: str) -> str:
    """Stable chunk identity scoped by document, ordinal, and chunk content."""
    content_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            document_id + str(chunk_index) + content_digest,
        )
    )


def reference_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fallback_title(source: str, product: str, version: str) -> str:
    path = unquote(urlsplit(source).path.rstrip("/"))
    basename = path.rsplit("/", 1)[-1] if path else ""
    return basename or source.strip() or f"{product} {version}".strip() or "Reference document"


def extract_document_metadata(
    text: str,
    *,
    source: str,
    product: str,
    version: str,
) -> tuple[str, dict[str, Any]]:
    """Extract deterministic document-level metadata once per logical document."""
    headings: list[str] = []
    title: str | None = None
    paragraph_lines: list[str] = []
    summary: str | None = None
    in_fence = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        match = _HEADING_RE.match(line)
        if match:
            heading = _SPACE_RE.sub(" ", match.group("title")).strip()
            if heading:
                headings.append(heading)
                if title is None and len(match.group("marks")) == 1:
                    title = heading
            if paragraph_lines and summary is None:
                summary = _SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()
            paragraph_lines = []
            continue

        if not line:
            if paragraph_lines and summary is None:
                summary = _SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()
            paragraph_lines = []
            continue

        if summary is None:
            paragraph_lines.append(line)

    if paragraph_lines and summary is None:
        summary = _SPACE_RE.sub(" ", " ".join(paragraph_lines)).strip()

    resolved_title = title or (headings[0] if headings else None) or _fallback_title(source, product, version)
    metadata: dict[str, Any] = {}
    if summary:
        metadata["summary"] = summary[:1000]
    if headings:
        metadata["outline"] = headings
    return resolved_title, metadata


def upsert_reference_document(
    *,
    text: str,
    product: str,
    version: str,
    source: str,
) -> str:
    document_id = reference_document_id(product, version, source)
    title, metadata = extract_document_metadata(
        text,
        source=source,
        product=product,
        version=version,
    )
    content_hash = reference_content_hash(text)
    descriptor = _document_descriptor(
        {
            "title": title,
            "product": product,
            "version": version,
            "source": source,
            **metadata,
        }
    )
    descriptor_embedding = _embed_texts([descriptor])[0]
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO reference_documents
                (document_id, source, product, version, title, content_hash, metadata,
                 descriptor_embedding)
            VALUES (%s::uuid, %s, %s, %s, %s, %s, %s::jsonb, %s::double precision[])
            ON CONFLICT (document_id) DO UPDATE
            SET title = EXCLUDED.title,
                content_hash = EXCLUDED.content_hash,
                metadata = EXCLUDED.metadata,
                descriptor_embedding = EXCLUDED.descriptor_embedding,
                updated_at = now()
            """,
            (
                document_id,
                source,
                product,
                version,
                title,
                content_hash,
                json.dumps(metadata, ensure_ascii=False),
                descriptor_embedding,
            ),
        )
    return document_id


def _row_to_document(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    document = {
        "document_id": str(row["document_id"]),
        "source": str(row["source"]),
        "product": str(row["product"]),
        "version": str(row["version"]),
        "title": str(row["title"]),
        "content_hash": str(row["content_hash"]),
    }
    document.update(metadata)
    return document


def get_reference_document(document_id: str) -> dict[str, Any] | None:
    with psycopg.connect(POSTGRES_DSN, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, source, product, version, title, content_hash, metadata
            FROM reference_documents
            WHERE document_id = %s::uuid
            """,
            (document_id,),
        )
        row = cur.fetchone()
    return _row_to_document(dict(row)) if row else None


def list_reference_documents() -> list[dict[str, Any]]:
    with psycopg.connect(POSTGRES_DSN, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, source, product, version, title, content_hash, metadata
            FROM reference_documents
            ORDER BY product, version, title, document_id
            """
        )
        rows = cur.fetchall()
    return [_row_to_document(dict(row)) for row in rows]


def _embed_texts(texts: list[str]) -> list[list[float]]:
    batch_size = int(os.environ.get("REFERENCE_EMBED_BATCH_SIZE", "8"))
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = requests.post(
            f"{EMBEDDINGS_URL}/embed",
            json={"texts": batch, "normalize": True},
            timeout=60,
        )
        response.raise_for_status()
        batch_vectors = response.json()["vectors"]
        if len(batch_vectors) != len(batch):
            raise RuntimeError(
                f"embeddings returned {len(batch_vectors)} vectors for {len(batch)} texts"
            )
        vectors.extend(batch_vectors)
    return vectors


def _document_descriptor(document: dict[str, Any]) -> str:
    values: list[str] = [
        str(document.get("title") or ""),
        str(document.get("product") or ""),
        str(document.get("version") or ""),
        str(document.get("source") or ""),
        str(document.get("summary") or ""),
    ]
    for key in ("topics", "keywords", "outline"):
        value = document.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif isinstance(value, dict):
            values.append(json.dumps(value, ensure_ascii=False, sort_keys=True))
        elif isinstance(value, str):
            values.append(value)
    return "\n".join(value for value in values if value)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Invocation(_StrictModel):
    run_id: str = Field(min_length=1)
    invocation_id: str = Field(min_length=1)
    agent_role: str = Field(min_length=1)
    execution_stage: str = Field(min_length=1)
    step_name: str = Field(min_length=1)
    objective_id: str | None = None


class _Task(_StrictModel):
    instruction: str = Field(min_length=1)
    request: str
    input_artifacts: list[str]
    input_artifact_contents: dict[str, str]


class _ProjectContext(_StrictModel):
    execution_profile: str | None
    planning_provider: str | None
    repository_revision: str | None
    repository_path: str | None = Field(default=None, min_length=1)
    language: str | None
    platform: str | None
    technologies: list[str]
    constraints: list[str]


class _WorkspacePolicy(_StrictModel):
    writable_roots: list[str]
    read_only_roots: list[str]
    immutable_paths: list[str]


class _RequiredToolCall(_StrictModel):
    anyOf: list[str] = Field(min_length=1)
    minCalls: int = Field(ge=1)


class _Capabilities(_StrictModel):
    available_tools: list[str]
    required_tool_calls: list[_RequiredToolCall]


class RrReferencePreflightRequest(_StrictModel):
    schemaVersion: Literal["rr-reference-preflight.v1"]
    project_id: str = Field(min_length=1)
    invocation: _Invocation
    task: _Task
    project_context: _ProjectContext
    workspace_policy: _WorkspacePolicy


def _preflight_query(request: RrReferencePreflightRequest) -> str:
    parts: list[str] = [
        request.invocation.agent_role,
        request.invocation.execution_stage,
        request.invocation.step_name,
        request.task.instruction,
        request.task.request,
        request.project_context.execution_profile or "",
        request.project_context.language or "",
        request.project_context.platform or "",
        *request.project_context.technologies,
        *request.project_context.constraints,
        *request.task.input_artifacts,
        *request.task.input_artifact_contents.values(),
    ]
    return "\n".join(part for part in parts if part)


def _dot(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise RuntimeError("embedding vector dimensions do not match")
    return sum(a * b for a, b in zip(left, right))


def run_reference_preflight(
    request: RrReferencePreflightRequest,
    *,
    selected_count: int = REFERENCE_PREFLIGHT_SELECTED_COUNT,
) -> dict[str, Any]:
    documents = list_reference_documents()
    if not documents:
        return {
            "schemaVersion": "rr-reference-preflight-result.v1",
            "selected_documents": [],
            "remaining_documents": [],
        }

    query = _preflight_query(request)
    descriptor_texts = [_document_descriptor(document) for document in documents]
    vectors = _embed_texts([query, *descriptor_texts])
    query_vector = vectors[0]
    ranked = sorted(
        zip(documents, vectors[1:]),
        key=lambda item: (-_dot(query_vector, item[1]), item[0]["document_id"]),
    )

    selected_count = max(1, min(selected_count, len(ranked)))
    selected = [document for document, _vector in ranked[:selected_count]]
    remaining = [
        {
            "document_id": document["document_id"],
            "title": document["title"],
            "product": document["product"],
            "version": document["version"],
        }
        for document, _vector in ranked[selected_count:]
    ]
    return {
        "schemaVersion": "rr-reference-preflight-result.v1",
        "selected_documents": selected,
        "remaining_documents": remaining,
    }


def register_reference_catalog_tools(mcp: FastMCP) -> None:
    @mcp.tool(name="memory.reference.catalog.get")
    def reference_catalog_get(document_id: str) -> str:
        """Return complete current catalog metadata for one Reference document."""
        document = get_reference_document(document_id)
        if document is None:
            raise ValueError(f"Reference catalog document not found: {document_id}")
        return json.dumps(document, ensure_ascii=False, indent=2)

    @mcp.tool(name="rr.reference.preflight")
    def rr_reference_preflight(
        schemaVersion: Literal["rr-reference-preflight.v1"],
        project_id: str,
        invocation: dict[str, Any],
        task: dict[str, Any],
        project_context: dict[str, Any],
        workspace_policy: dict[str, Any],
    ) -> str:
        """Select Reference catalog documents for one trusted RR worker invocation."""
        request = RrReferencePreflightRequest.model_validate(
            {
                "schemaVersion": schemaVersion,
                "project_id": project_id,
                "invocation": invocation,
                "task": task,
                "project_context": project_context,
                "workspace_policy": workspace_policy,
            }
        )
        return json.dumps(run_reference_preflight(request), ensure_ascii=False, indent=2)
