#!/usr/bin/env bash
# scripts/init_qdrant.sh
# Manage the Qdrant collection from the tooling image. In-cluster; no kubectl.
#   ensure  create the collection + payload indexes only if missing (non-destructive)
#   delete  drop the collection
#   reset   delete then ensure
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
COL="${QDRANT_COLLECTION:-homel_memory}"
BASE="$QDRANT_URL/collections/$COL"

idx() {
  curl -fsS -X PUT "$BASE/index?wait=true" -H "Content-Type: application/json" \
    -d "{\"field_name\":\"$1\",\"field_schema\":\"$2\"}" >/dev/null
  echo "  indexed $1 ($2)"
}

create() {
  curl -fsS -X PUT "$BASE" -H "Content-Type: application/json" -d '{
    "vectors": {"dense": {"size": 384, "distance": "Cosine"}},
    "sparse_vectors": {"lexical": {"modifier": "idf"}},
    "on_disk_payload": true
  }' >/dev/null
  echo "collection $COL created"
  idx project_id  keyword
  idx memory_type keyword
  idx scope       keyword
  idx source      keyword
  idx product     keyword
  idx version     keyword
  idx chunk_id    keyword
  idx origin_hash keyword
  idx confidence  float
  idx ingested_at datetime
}

ensure() {
  if curl -fsS "$BASE" >/dev/null 2>&1; then
    echo "collection $COL exists, skipping"
  else
    create
  fi
}

delete() {
  curl -fsS -X DELETE "$BASE" >/dev/null 2>&1 || true
  echo "collection $COL deleted"
}

case "${1:-ensure}" in
  ensure) ensure ;;
  delete) delete ;;
  reset)  delete; ensure ;;
  *) echo "usage: $0 {ensure|delete|reset}" >&2; exit 2 ;;
esac
