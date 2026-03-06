# content_plane.py
"""
Content Plane: memory ingestion, update, purge, inspect, cache control.
All operator mutating actions are logged.
"""

import time
import hashlib
import logging
from typing import Optional

import psycopg
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, Filter, FieldCondition, MatchValue
from fastmcp import FastMCP

from memory_steward_mcp.config import QDRANT_COLLECTION, POSTGRES_DSN
from memory_steward_mcp.cache import StaticMemoryCacheManager

log = logging.getLogger("memory-steward-mcp.content")

def register_content_tools(mcp: FastMCP, qdrant: QdrantClient, embed_fn: callable):

    @mcp.tool()
    def ingest_reference(
        product: str,
        version: str,
        scope: str,
        content: str,
        source_url: str = "manual-mcp"
    ) -> str:
        """[Content Plane] Ingests a new Reference Memory chunk."""
        point_id = f"ref:{product}:{version}:{int(time.time()*1e6)}"
        vector = embed_fn(content)

        payload = {
            "memory_type": "reference_memory",
            "product": product,
            "version": version,
            "scope": scope,
            "content": content,
            "source": source_url,
            "ingested_at": time.time()
        }

        qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(id=point_id, vector={"dense": vector}, payload=payload)]
        )
        log.info(f"Operator action: INGEST_REFERENCE id={point_id}")
        return f"Successfully ingested reference memory ID {point_id}."

    @mcp.tool()
    def inspect_memory(
        memory_type: str = "reference_memory",
        limit: int = 5,
        project_id: Optional[str] = None
    ) -> str:
        """[Content Plane] Debug tool to inspect raw vectors."""
        must = [FieldCondition(key="memory_type", match=MatchValue(value=memory_type))]
        if project_id:
            must.append(FieldCondition(key="project_id", match=MatchValue(value=project_id)))

        res = qdrant.scroll(
            collection_name=QDRANT_COLLECTION,
            scroll_filter=Filter(must=must),
            limit=limit
        )
        return str([p.payload for p in res[0]])

    @mcp.tool()
    def create_static(content: str, mode: str = "global") -> str:
        """[Content Plane] Inserts a new static memory rule."""
        with psycopg.connect(POSTGRES_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO static_memory (content, mode)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (content, mode),
                )
                new_id = cur.fetchone()[0]
            
        log.info(f"Operator action: CREATE_STATIC id={new_id} mode={mode}")
        return f"Static memory rule created. ID: {new_id}"

    @mcp.tool()
    def update_static(rule_id: str, content: str, mode: str = "global") -> str:
        """[Content Plane] Overwrites an existing static rule by its UUID."""
        with psycopg.connect(POSTGRES_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE static_memory 
                    SET content=%s, mode=%s, updated_at=now()
                    WHERE id=%s
                    """,
                    (content, mode, rule_id),
                )
            
        log.info(f"Operator action: UPDATE_STATIC id={rule_id} mode={mode}")
        return f"Static memory rule {rule_id} updated."

    @mcp.tool()
    def list_static() -> str:
        """[Content Plane] Lists all static memory rules."""
        with psycopg.connect(POSTGRES_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, mode, is_active, content FROM static_memory ORDER BY created_at ASC")
                rows = cur.fetchall()
                
        if not rows:
            return "No static memory rules found."
            
        lines = ["### Static Memory Rules"]
        for r_id, mode, is_active, content in rows:
            snippet = content.replace('\n', ' ')
            lines.append(f"- ID: {r_id} | Mode: {mode} | Active: {is_active} | Content: {snippet}")
        return "\n".join(lines)

    @mcp.tool()
    def purge_reference(chunk_id: Optional[str] = None, namespace: Optional[str] = None) -> str:
        """[Content Plane] Destructive removal of reference memory by chunk or namespace."""
        if chunk_id:
            qdrant.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=[int(chunk_id)] if chunk_id.isdigit() else [chunk_id]
            )
            log.warning(f"Operator action: PURGE_REFERENCE chunk_id={chunk_id}")
            return f"Purged chunk {chunk_id}."

        if namespace:
            qdrant.delete(
                collection_name=QDRANT_COLLECTION,
                points_selector=Filter(
                    must=[
                        FieldCondition(key="memory_type", match=MatchValue(value="reference_memory")),
                        FieldCondition(key="product", match=MatchValue(value=namespace))
                    ]
                )
            )
            log.warning(f"Operator action: PURGE_REFERENCE namespace={namespace}")
            return f"Purged all references for namespace: {namespace}."

        raise ValueError("Must specify chunk_id or namespace.")

    @mcp.tool()
    def control_cache(action: str) -> str:
        """[Content Plane] Cache management. Action must be 'refresh' or 'evict'."""
        if action == "refresh":
            StaticMemoryCacheManager.refresh()
            log.info("Operator action: CACHE_REFRESH")
            return "Static memory cache refreshed."
        elif action == "evict":
            StaticMemoryCacheManager.evict_cache()
            log.info("Operator action: CACHE_EVICT")
            return "Static memory cache evicted."
        else:
            raise ValueError("Action must be 'refresh' or 'evict'.")
