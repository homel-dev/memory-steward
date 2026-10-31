kubectl -n ms exec -i deployment/memory-steward-mcp -c mcp -- python - < scripts/backfill_reference_descriptor_embeddings.py
