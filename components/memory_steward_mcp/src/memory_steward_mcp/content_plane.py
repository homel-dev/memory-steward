# components/memory_steward_mcp/src/memory_steward_mcp/content_plane.py
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

import hashlib
import logging
import re
import time
import uuid

import psycopg
import requests
from bs4 import BeautifulSoup, NavigableString
from fastmcp import FastMCP
from qdrant_client import QdrantClient
from qdrant_client.http.models import FieldCondition, Filter, MatchValue, PointStruct

from memory_steward_mcp.config import EMBEDDINGS_URL, POSTGRES_DSN, QDRANT_COLLECTION

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


def _ref_key(product: str, version: str, content: str) -> str:
    """Human-readable, stable reference key. Stored in the payload for debugging
    and provenance; NOT used as the Qdrant point ID."""
    fingerprint = hashlib.sha256(
        f"{product}:{version}:{content}".encode()
    ).hexdigest()[:32]
    return f"ref:{product}:{version}:{fingerprint}"


def _chunk_id(product: str, version: str, content: str) -> str:
    """Deterministic, stable Qdrant point ID.

    Qdrant only accepts unsigned-int or UUID point IDs; a string like
    'ref:product:version:hash' is rejected at upsert. We derive a UUIDv5 from
    the human-readable ref key so the ID is valid AND idempotent (same content
    always maps to the same UUID)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, _ref_key(product, version, content)))


_DOCUMENT_HEADING_RE = re.compile(
    r"^(?P<marks>#{2,4}|={2,4})\s+(?P<title>.+?)\s*$"
)


def _append_chunk(
    chunks: list[dict],
    *,
    title: str,
    body: str,
    max_chars: int,
) -> None:
    """Append one semantic section, splitting only oversized sections."""
    body = body.strip()
    if not body:
        return

    if len(body) <= max_chars:
        chunks.append({"section": title, "content": body})
        return

    words = body.split()
    window, overlap = 250, 50
    i = 0
    part = 1
    while i < len(words):
        chunk_text = " ".join(words[i:i + window])
        chunks.append({"section": f"{title} (part {part})", "content": chunk_text})
        if i + window >= len(words):
            break
        i += window - overlap
        part += 1


def _chunk_markdown(text: str, max_chars: int = 1500) -> list[dict]:
    """Split Markdown or AsciiDoc into heading-aware semantic chunks.

    Markdown H2-H4 and AsciiDoc level-2 through level-4 headings are section
    boundaries. Child headings retain their parent path in ``doc_section``.
    """
    chunks: list[dict] = []
    heading_stack: dict[int, str] = {}
    section_title = "General"
    section_lines: list[str] = []

    def flush() -> None:
        _append_chunk(
            chunks,
            title=section_title,
            body="\n".join(section_lines),
            max_chars=max_chars,
        )

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        match = _DOCUMENT_HEADING_RE.match(line)
        if not match:
            section_lines.append(line)
            continue

        flush()
        section_lines = []

        level = len(match.group("marks"))
        heading_stack[level] = match.group("title").strip()
        for deeper_level in [depth for depth in heading_stack if depth > level]:
            del heading_stack[deeper_level]

        section_title = " > ".join(
            heading_stack[depth]
            for depth in sorted(heading_stack)
            if depth <= level
        )

    flush()
    return chunks


def _extract_html_document(raw_html: str) -> str:
    """Extract semantic documentation text from server-rendered HTML."""
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup.find_all(
        ["script", "style", "noscript", "svg", "template", "form", "button", "iframe"]
    ):
        tag.decompose()

    root = None
    for selector in ("#content", "article", "main", '[role="main"]'):
        root = soup.select_one(selector)
        if root is not None:
            break
    if root is None:
        root = soup.body or soup

    for selector in ("#toc", ".toc", ".toc2", '[role="navigation"]'):
        for tag in root.select(selector):
            tag.decompose()

    for tag in root.find_all(["nav", "header", "footer", "aside"]):
        tag.decompose()

    for tag in root.find_all(["h1", "h2", "h3", "h4"]):
        heading = tag.get_text(" ", strip=True)
        if not heading:
            tag.decompose()
            continue
        level = int(tag.name[1])
        tag.replace_with(NavigableString(f"\n{'#' * level} {heading}\n"))

    for tag in root.find_all("pre"):
        code = tag.get_text("\n", strip=False).strip()
        replacement = f"\n```\n{code}\n```\n" if code else "\n"
        tag.replace_with(NavigableString(replacement))

    for row in root.find_all("tr"):
        cells = [
            cell.get_text(" ", strip=True)
            for cell in row.find_all(["th", "td"], recursive=False)
        ]
        row.replace_with(
            NavigableString("\n" + " | ".join(cells) + "\n" if cells else "\n")
        )

    for tag in root.find_all("li"):
        item = tag.get_text(" ", strip=True)
        tag.replace_with(NavigableString(f"\n- {item}\n" if item else "\n"))

    for tag in root.find_all("p"):
        paragraph = tag.get_text(" ", strip=True)
        tag.replace_with(
            NavigableString(f"\n{paragraph}\n" if paragraph else "\n")
        )

    for tag in root.find_all("br"):
        tag.replace_with(NavigableString("\n"))

    normalized: list[str] = []
    previous_blank = False
    for raw_line in root.get_text("\n").splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        if not line:
            if normalized and not previous_blank:
                normalized.append("")
            previous_blank = True
            continue
        normalized.append(line)
        previous_blank = False

    return "\n".join(normalized).strip()


def _fetch_url(url: str) -> str:
    """Fetch a reference URL and normalize HTML documentation for chunking."""
    r = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "memory-steward-mcp/1.0"},
    )
    r.raise_for_status()

    text = r.text
    media_type = r.headers.get("content-type", "").partition(";")[0].lower()
    looks_like_html = bool(
        re.search(
            r"<(?:!doctype\s+html|html|body|main|article|h[1-4])\b",
            text[:4096],
            re.I,
        )
    )

    if media_type in {"text/html", "application/xhtml+xml"} or looks_like_html:
        text = _extract_html_document(text)

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
# Shared ingestion (module scope so MCP tools AND the Git plane can import it)
# ---------------------------------------------------------------------------

def _ingest_text_internal(
    qdrant: QdrantClient,
    *,
    text: str,
    product: str,
    version: str,
    scope: str,
    source_url: str,
) -> str:
    """Chunk, embed, and upsert text as reference memory. Idempotent.

    Promoted to module scope (was previously nested inside
    register_content_tools, which made `from content_plane import
    _ingest_text_internal` fail and prevented the MCP server from starting).
    The Qdrant client is now passed explicitly instead of captured via closure.
    """
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
                "ref_key": _ref_key(product, version, chunk["content"]),
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


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_content_tools(mcp: FastMCP, qdrant: QdrantClient, _unused_embed_fn=None):
    # Note: _unused_embed_fn kept for signature compatibility but we use _embed() directly.

    # -----------------------------------------------------------------------
    # REFERENCE MEMORY: URL INGESTION
    # -----------------------------------------------------------------------

    @mcp.tool(name="ref_ingest_url")
    def ingest_reference_url(
        url: str,
        product: str,
        version: str,
        scope: str = "general",
    ) -> str:
        """[Reference] Fetch a URL and ingest it as chunked reference memory.
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
            qdrant,
            text=raw_text,
            product=product,
            version=version,
            scope=scope,
            source_url=url,
        )

    @mcp.tool(name="ref_ingest_text")
    def ingest_reference_text(
        content: str,
        product: str,
        version: str,
        scope: str = "general",
        source_url: str = "manual",
    ) -> str:
        """[Reference] Ingest raw markdown/text as chunked reference memory.
        Use this when you have the documentation text directly (e.g. pasted content,
        file contents, or the Memory Steward docs themselves).

        Idempotent — re-ingesting the same content produces the same chunk IDs.
        """
        return _ingest_text_internal(
            qdrant,
            text=content,
            product=product,
            version=version,
            scope=scope,
            source_url=source_url,
        )

    # -----------------------------------------------------------------------
    # REFERENCE MEMORY: INSPECTION & MANAGEMENT
    # -----------------------------------------------------------------------

    @mcp.tool(name="ref_list")
    def list_reference_namespaces() -> str:
        """[Reference] List reference namespaces currently stored in Qdrant.

        ``reference_ingestion`` is immutable provenance history; it is not the
        current-state inventory and therefore is intentionally not queried here.
        """
        namespaces: dict[tuple[str, str], dict] = {}
        offset = None

        try:
            while True:
                points, next_offset = qdrant.scroll(
                    collection_name=QDRANT_COLLECTION,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="memory_type",
                                match=MatchValue(value="reference_memory"),
                            )
                        ]
                    ),
                    limit=512,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                for point in points:
                    payload = point.payload or {}
                    product = payload.get("product")
                    version = payload.get("version")
                    if not product or not version:
                        continue

                    key = (str(product), str(version))
                    entry = namespaces.setdefault(
                        key,
                        {"chunks": 0, "scopes": set(), "sources": set()},
                    )
                    entry["chunks"] += 1

                    scope = payload.get("scope")
                    if scope:
                        entry["scopes"].add(str(scope))

                    source = payload.get("source")
                    if source:
                        entry["sources"].add(str(source))

                if next_offset is None:
                    break
                offset = next_offset
        except Exception as e:
            return f"Qdrant error: {e}"

        if not namespaces:
            return "No reference memory stored."

        lines = ["## Reference Memory Namespaces"]
        for (product, version), entry in sorted(namespaces.items()):
            scopes = ",".join(sorted(entry["scopes"])) or "?"
            sources = sorted(entry["sources"])
            if not sources:
                source = "?"
            elif len(sources) == 1:
                source = sources[0]
            else:
                source = f"{len(sources)} sources"

            lines.append(
                f"- **{product}@{version}**  scopes={scopes}  "
                f"chunks={entry['chunks']}  source={source}"
            )

        return "\n".join(lines)

    @mcp.tool(name="ref_inspect")
    def inspect_reference(
        product: str,
        version: str,
        limit: int = 10,
        section_filter: str = None,
    ) -> str:
        """[Reference] Inspect stored chunks for a specific product/version.
        Optionally filter by section name substring."""
        try:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue
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

    @mcp.tool(name="ref_purge")
    def purge_reference(
        product: str,
        version: str,
    ) -> str:
        """[Reference] Remove all reference memory chunks for a product/version.
        This is destructive and irreversible. Re-ingest to restore."""
        try:
            qdrant.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=Filter(must=[
                    FieldCondition(key="memory_type", match=MatchValue(value="reference_memory")),
                    FieldCondition(key="product", match=MatchValue(value=product)),
                    FieldCondition(key="version", match=MatchValue(value=version)),
                ]),
                wait=True,
            )
            log.warning(f"Operator action: PURGE_REFERENCE product={product} version={version}")
            return f"✅ Purged all reference chunks for `{product}@{version}`."
        except Exception as e:
            return f"Purge failed: {e}"

    # -----------------------------------------------------------------------
    # STATIC MEMORY CRUD
    # -----------------------------------------------------------------------

    @mcp.tool(name="static_list")
    def list_static() -> str:
        """[Static] List all static memory rules with IDs and active status."""
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

    @mcp.tool(name="static_create")
    def create_static(content: str, mode: str = "global") -> str:
        """[Static] Add a new static memory rule.
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

    @mcp.tool(name="static_update")
    def update_static(rule_id: str, content: str, mode: str = "global") -> str:
        """[Static] Update content and/or mode of an existing static rule."""
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

    @mcp.tool(name="static_toggle")
    def toggle_static(rule_id: str, active: bool) -> str:
        """[Static] Activate or deactivate a static rule without deleting it.
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

    @mcp.tool(name="static_delete")
    def delete_static(rule_id: str) -> str:
        """[Static] Permanently delete a static rule. Use toggle_static to
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

    @mcp.tool(name="cache_control")
    def control_cache(action: str) -> str:
        """[Cache] Manage the MCP process-local StaticMemoryCacheManager.

        This cache is not used by the Memory Router request path. `refresh`
        reloads the MCP-local cache from Qdrant; `evict` clears that local cache.
        """
        from memory_steward_mcp.cache import StaticMemoryCacheManager
        if action == "refresh":
            StaticMemoryCacheManager.refresh()
            log.info("Operator action: CACHE_REFRESH scope=mcp-local")
            return "✅ MCP-local static-memory cache refreshed. Router retrieval is unchanged."
        elif action == "evict":
            StaticMemoryCacheManager.evict_cache()
            log.info("Operator action: CACHE_EVICT scope=mcp-local")
            return "✅ MCP-local cache evicted. Router retrieval is unchanged."
        return f"Unknown action '{action}'. Must be 'refresh' or 'evict'."
