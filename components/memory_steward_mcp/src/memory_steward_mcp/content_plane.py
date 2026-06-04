# content_plane.py
"""
Content Plane: reference memory ingestion (URL + text), static memory CRUD,
content inspection, cache control, and provenance tracking.

Key invariants (Doc 03):
- Reference memory is always versioned, scoped, and attributed.
- Ingestion is idempotent: same content + product + version = same chunk_id.
- Provenance is recorded in Postgres reference_ingestion table.
- embed_fn calls POST /embed with {"texts": [...]} (not bare /embed with {"text": ...}).
"""

import re
import time
import hashlib
import logging
import requests
from typing import Optional

import psycopg
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue
from fastmcp import FastMCP

from memory_steward_mcp.config import QDRANT_COLLECTION, POSTGRES_DSN, EMBEDDINGS_URL

log = logging.getLogger("memory-steward-mcp.content")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _embed(texts: list[str]) -> list[list[float]]:
    """Call the embeddings service. Correct path and payload shape."""
    r = requests.post(
        f"{EMBEDDINGS_URL}/embed",
        json={"texts": texts, "normalize": True},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["vectors"]


def _chunk_id(product: str, version: str, content: str) -> str:
    """Deterministic, stable chunk ID. Same content always maps to the same ID.
    This makes ingestion fully idempotent."""
    fingerprint = hashlib.sha256(
        f"{product}:{version}:{content}".encode()
    ).hexdigest()[:32]
    return f"ref:{product}:{version}:{fingerprint}"


def _chunk_markdown(text: str, max_chars: int = 1500) -> list[dict]:
    """
    Split markdown into semantic chunks by H2 section.
    Each chunk carries its section title for metadata.
    Falls back to sliding window if a section exceeds max_chars.
    """
    # Split on H2 headers
    sections = re.split(r'\n(?=## )', text.strip())
    chunks = []

    for section in sections:
        if not section.strip():
            continue

        # Extract section title
        lines = section.strip().splitlines()
        title = lines[0].lstrip('#').strip() if lines else "General"
        body = "\n".join(lines[1:]).strip() if len(lines) > 1 else section.strip()

        if not body:
            body = section.strip()

        # If section fits, emit as one chunk
        if len(body) <= max_chars:
            chunks.append({"section": title, "content": body})
            continue

        # Otherwise slide through it in overlapping windows
        words = body.split()
        window, overlap = 250, 50
        i = 0
        part = 0
        while i < len(words):
            chunk_text = " ".join(words[i: i + window])
            chunks.append({"section": f"{title} (part {part + 1})", "content": chunk_text})
            i += window - overlap
            part += 1

    return chunks


def _fetch_url(url: str) -> str:
    """Fetch raw text from a URL. Strips HTML tags for non-markdown sources."""
    r = requests.get(url, timeout=30, headers={"User-Agent": "memory-steward-mcp/1.0"})
    r.raise_for_status()
    content_type = r.headers.get("content-type", "")
    text = r.text
    if "html" in content_type:
        # Very basic HTML strip — good enough for docs pages
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def _record_provenance(
    product: str, version: str, scope: str, source_url: str,
    chunk_count: int, upserted: int
) -> None:
    """Record ingestion event in Postgres for auditability (Doc 03 §5)."""
    with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO reference_ingestion
                (product, version, scope, source_url, chunk_count, upserted_count, ingested_at)
            VALUES (%s, %s, %s, %s, %s, %s, now())
        """, (product, version, scope, source_url, chunk_count, upserted))


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_content_tools(mcp: FastMCP, qdrant: QdrantClient, _unused_embed_fn=None):
    # Note: _unused_embed_fn kept for signature compatibility but we use _embed() directly.

    # -----------------------------------------------------------------------
    # REFERENCE MEMORY: URL INGESTION
    # -----------------------------------------------------------------------

    @mcp.tool()
    def ingest_reference_url(
        url: str,
        product: str,
        version: str,
        scope: str = "general",
    ) -> str:
        """[Content Plane] Fetch a URL and ingest it as chunked reference memory.
        Chunks deterministically by H2 section. Idempotent — safe to re-run.

        Examples:
          product=memory-steward  version=1.0  scope=architecture
          product=terraform       version=1.6  scope=implementation
          product=kubernetes      version=1.29 scope=operations
        """
        try:
            raw_text = _fetch_url(url)
        except Exception as e:
            return f"Failed to fetch {url}: {e}"

        return _ingest_text_internal(
            text=raw_text,
            product=product,
            version=version,
            scope=scope,
            source_url=url,
        )

    @mcp.tool()
    def ingest_reference_text(
        content: str,
        product: str,
        version: str,
        scope: str = "general",
        source_url: str = "manual",
    ) -> str:
        """[Content Plane] Ingest raw markdown/text as chunked reference memory.
        Use this when you have the documentation text directly (e.g. pasted content,
        file contents, or the Memory Steward docs themselves).

        Idempotent — re-ingesting the same content produces the same chunk IDs.
        """
        return _ingest_text_internal(
            text=content,
            product=product,
            version=version,
            scope=scope,
            source_url=source_url,
        )

    def _ingest_text_internal(
        text: str,
        product: str,
        version: str,
        scope: str,
        source_url: str,
    ) -> str:
        chunks = _chunk_markdown(text)
        if not chunks:
            return "No content extracted — check the source text."

        texts = [c["content"] for c in chunks]
        try:
            vectors = _embed(texts)
        except Exception as e:
            return f"Embedding failed: {e}"

        points = []
        for i, (chunk, vec) in enumerate(zip(chunks, vectors)):
            cid = _chunk_id(product, version, chunk["content"])
            points.append(PointStruct(
                id=cid,
                vector={"dense": vec},
                payload={
                    "memory_type": "reference_memory",
                    "product": product,
                    "version": version,
                    "scope": scope,
                    "doc_section": chunk["section"],
                    "content": chunk["content"],
                    "source": source_url,
                    "chunk_index": i,
                    "ingested_at": time.time(),
                }
            ))

        try:
            qdrant.upsert(collection_name=QDRANT_COLLECTION, points=points)
        except Exception as e:
            return f"Qdrant upsert failed after embedding {len(points)} chunks: {e}"

        try:
            _record_provenance(product, version, scope, source_url, len(chunks), len(points))
        except Exception as e:
            log.warning(f"Provenance record failed (non-fatal): {e}")

        log.info(f"Operator action: INGEST_REFERENCE product={product} version={version} chunks={len(points)}")
        return (
            f"✅ Ingested **{len(points)} chunks** for `{product}@{version}` ({scope}).\n"
            f"Source: {source_url}\n"
            f"Sections: {', '.join(set(c['section'] for c in chunks[:8]))}"
            + (" ..." if len(chunks) > 8 else "")
        )

    # -----------------------------------------------------------------------
    # REFERENCE MEMORY: INSPECTION & MANAGEMENT
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_reference_namespaces() -> str:
        """[Content Plane] List all ingested reference memory namespaces
        (product + version combinations) with chunk counts and ingestion dates."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT product, version, scope, source_url,
                           chunk_count, upserted_count, ingested_at
                    FROM reference_ingestion
                    ORDER BY ingested_at DESC
                """)
                rows = cur.fetchall()
        except Exception as e:
            return f"DB error: {e}"

        if not rows:
            return "No reference memory ingested yet."

        lines = ["## Reference Memory Namespaces"]
        for product, version, scope, source, chunks, upserted, ingested_at in rows:
            lines.append(
                f"- **{product}@{version}** ({scope})  "
                f"chunks={chunks}  upserted={upserted}  "
                f"ingested={ingested_at.strftime('%Y-%m-%d %H:%M')}  "
                f"source={source}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def inspect_reference(
        product: str,
        version: str,
        limit: int = 10,
        section_filter: str = None,
    ) -> str:
        """[Content Plane] Inspect stored chunks for a specific product/version.
        Optionally filter by section name substring."""
        try:
            from qdrant_client.http.models import Filter, FieldCondition, MatchValue
            must = [
                FieldCondition(key="memory_type", match=MatchValue(value="reference_memory")),
                FieldCondition(key="product", match=MatchValue(value=product)),
                FieldCondition(key="version", match=MatchValue(value=version)),
            ]
            res = qdrant.scroll(
                collection_name=QDRANT_COLLECTION,
                scroll_filter=Filter(must=must),
                limit=min(limit, 50),
                with_payload=True,
            )
            points = res[0]
        except Exception as e:
            return f"Qdrant error: {e}"

        if not points:
            return f"No reference chunks found for {product}@{version}."

        if section_filter:
            points = [
                p for p in points
                if section_filter.lower() in (p.payload.get("doc_section") or "").lower()
            ]

        lines = [f"## Reference Chunks: `{product}@{version}` ({len(points)} shown)"]
        for p in points:
            section = p.payload.get("doc_section", "?")
            content = p.payload.get("content", "")[:200]
            lines.append(f"\n### {section}\n{content}...")

        return "\n".join(lines)

    @mcp.tool()
    def purge_reference(
        product: str,
        version: str,
    ) -> str:
        """[Content Plane] Remove all reference memory chunks for a product/version.
        This is destructive and irreversible. Re-ingest to restore."""
        try:
            result = qdrant.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=Filter(must=[
                    FieldCondition(key="memory_type", match=MatchValue(value="reference_memory")),
                    FieldCondition(key="product", match=MatchValue(value=product)),
                    FieldCondition(key="version", match=MatchValue(value=version)),
                ])
            )
            log.warning(f"Operator action: PURGE_REFERENCE product={product} version={version}")
            return f"✅ Purged all reference chunks for `{product}@{version}`."
        except Exception as e:
            return f"Purge failed: {e}"

    # -----------------------------------------------------------------------
    # STATIC MEMORY CRUD
    # -----------------------------------------------------------------------

    @mcp.tool()
    def list_static() -> str:
        """[Content Plane] List all static memory rules with IDs and active status."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("""
                    SELECT id, mode, is_active, created_at, content
                    FROM static_memory ORDER BY created_at ASC
                """)
                rows = cur.fetchall()
        except Exception as e:
            return f"DB error: {e}"

        if not rows:
            return "No static memory rules found."

        lines = ["## Static Memory Rules"]
        for r_id, mode, is_active, created_at, content in rows:
            icon = "✅" if is_active else "⏸️"
            snippet = content.replace('\n', ' ')[:120]
            lines.append(
                f"{icon} `{r_id}`  mode={mode}  "
                f"created={created_at.strftime('%Y-%m-%d')}  \n"
                f"   {snippet}"
            )
        return "\n".join(lines)

    @mcp.tool()
    def create_static(content: str, mode: str = "global") -> str:
        """[Content Plane] Add a new static memory rule.
        mode: 'global' (always injected) or one of the canonical mode names."""
        valid = {"global", "engineering", "implementation", "brainstorming", "formal_spec", "casual"}
        if mode not in valid:
            return f"Invalid mode '{mode}'. Must be one of: {valid}"
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO static_memory (content, mode) VALUES (%s, %s) RETURNING id",
                    (content, mode),
                )
                new_id = cur.fetchone()[0]
        except Exception as e:
            return f"DB error: {e}"
        log.info(f"Operator action: CREATE_STATIC id={new_id} mode={mode}")
        return f"✅ Static rule created: `{new_id}` (mode={mode})"

    @mcp.tool()
    def update_static(rule_id: str, content: str, mode: str = "global") -> str:
        """[Content Plane] Update content and/or mode of an existing static rule."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("""
                    UPDATE static_memory SET content=%s, mode=%s, updated_at=now()
                    WHERE id=%s RETURNING id
                """, (content, mode, rule_id))
                if not cur.fetchone():
                    return f"Rule `{rule_id}` not found."
        except Exception as e:
            return f"DB error: {e}"
        log.info(f"Operator action: UPDATE_STATIC id={rule_id}")
        return f"✅ Rule `{rule_id}` updated."

    @mcp.tool()
    def toggle_static(rule_id: str, active: bool) -> str:
        """[Content Plane] Activate or deactivate a static rule without deleting it.
        Deactivated rules are not injected into prompts."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("""
                    UPDATE static_memory SET is_active=%s, updated_at=now()
                    WHERE id=%s RETURNING id
                """, (active, rule_id))
                if not cur.fetchone():
                    return f"Rule `{rule_id}` not found."
        except Exception as e:
            return f"DB error: {e}"
        state = "activated" if active else "deactivated"
        log.info(f"Operator action: TOGGLE_STATIC id={rule_id} active={active}")
        return f"✅ Rule `{rule_id}` {state}."

    @mcp.tool()
    def delete_static(rule_id: str) -> str:
        """[Content Plane] Permanently delete a static rule. Use toggle_static to
        temporarily deactivate instead."""
        try:
            with psycopg.connect(POSTGRES_DSN) as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM static_memory WHERE id=%s RETURNING id", (rule_id,))
                if not cur.fetchone():
                    return f"Rule `{rule_id}` not found."
        except Exception as e:
            return f"DB error: {e}"
        log.warning(f"Operator action: DELETE_STATIC id={rule_id}")
        return f"✅ Rule `{rule_id}` deleted permanently."

    # -----------------------------------------------------------------------
    # CACHE CONTROL
    # -----------------------------------------------------------------------

    @mcp.tool()
    def control_cache(action: str) -> str:
        """[Content Plane] Manage the static memory cache.
        action: 'refresh' (reload from Qdrant) or 'evict' (clear, force next-request reload)."""
        from memory_steward_mcp.cache import StaticMemoryCacheManager
        if action == "refresh":
            StaticMemoryCacheManager.refresh()
            log.info("Operator action: CACHE_REFRESH")
            return "✅ Static memory cache refreshed."
        elif action == "evict":
            StaticMemoryCacheManager.evict_cache()
            log.info("Operator action: CACHE_EVICT")
            return "✅ Cache evicted — will reload on next request."
        return f"Unknown action '{action}'. Must be 'refresh' or 'evict'."
