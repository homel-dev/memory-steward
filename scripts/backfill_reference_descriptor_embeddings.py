#!/usr/bin/env python3
"""Backfill missing Reference document descriptor embeddings in PostgreSQL.

Run inside the memory-steward-mcp container after migration 151 is applied.
"""

from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

from memory_steward_mcp.config import POSTGRES_DSN
from memory_steward_mcp.reference_catalog import (
    _document_descriptor,
    _embed_texts,
    _row_to_document,
)


def main() -> None:
    batch_size = int(os.environ.get("REFERENCE_EMBED_BATCH_SIZE", "8"))

    with psycopg.connect(POSTGRES_DSN) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT document_id, source, product, version, title, content_hash, metadata
                FROM reference_documents
                WHERE descriptor_embedding IS NULL
                ORDER BY product, version, title, document_id
                """
            )
            documents = cur.fetchall()
        conn.commit()

        print(f"Reference documents missing descriptor embeddings: {len(documents)}", flush=True)
        updated = 0
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            descriptors = [_document_descriptor(_row_to_document(row)) for row in batch]
            vectors = _embed_texts(descriptors)

            with conn.cursor() as cur:
                cur.executemany(
                    """
                    UPDATE reference_documents
                    SET descriptor_embedding = %s::double precision[]
                    WHERE document_id = %s::uuid AND descriptor_embedding IS NULL
                    """,
                    [(vector, row["document_id"]) for row, vector in zip(batch, vectors)],
                )
                updated += cur.rowcount
            conn.commit()
            print(f"Processed {start + len(batch)}/{len(documents)}; updated {updated}", flush=True)

    print(f"Backfill complete: updated {updated} document(s).", flush=True)


if __name__ == "__main__":
    main()
