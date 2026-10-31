#!/usr/bin/env bash
# scripts/init_qdrant.sh
# Manage the Qdrant collection from the tooling image. In-cluster; no kubectl.
#   ensure  create the collection + payload indexes only if missing (non-destructive)
#   delete  drop the collection
#   reset   delete then recreate the collection and payload indexes
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
  local body status
  body="$(mktemp)"
  status="$(curl -sS -o "$body" -w '%{http_code}' -X DELETE "$BASE")" || {
    local rc=$?
    cat "$body" >&2 || true
    rm -f "$body"
    return "$rc"
  }

  case "$status" in
    2??)
      echo "collection $COL deleted"
      ;;
    404)
      echo "collection $COL does not exist"
      ;;
    *)
      echo "Qdrant DELETE $BASE failed with HTTP $status" >&2
      cat "$body" >&2 || true
      rm -f "$body"
      return 1
      ;;
  esac
  rm -f "$body"
}

reset() {
  delete
  create
  curl -fsS "$BASE" >/dev/null
  echo "collection $COL reset complete"
}

case "${1:-ensure}" in
  ensure) ensure ;;
  delete) delete ;;
  reset)  reset ;;
  *) echo "usage: $0 {ensure|delete|reset}" >&2; exit 2 ;;
esac
