#!/usr/bin/env bash
# scripts/restore.sh
#
# In-cluster restore from artifacts on the backups PVC.
#   DUMP_FILE      basename under /backups/pg        (optional; skip PG if unset)
#   SNAPSHOT_FILE  basename under /backups/qdrant    (optional; skip Qdrant if unset)
# Postgres via libpq env; Qdrant via QDRANT_URL. No kubectl, no host.
# Order: Postgres first (so migrate can run after), then Qdrant.

set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-homel_memory}"

if [ -n "${DUMP_FILE:-}" ]; then
  SRC="/backups/pg/$DUMP_FILE"
  [ -f "$SRC" ] || { echo "no such dump: $SRC"; exit 1; }
  echo "[pg] restoring $SRC ..."
  pg_restore --no-owner --clean --if-exists -d "${PGDATABASE:-homel}" "$SRC"
  echo "[pg] done (schema_migrations now reflects the dump)"
else
  echo "[pg] DUMP_FILE unset, skipping Postgres restore"
fi

if [ -n "${SNAPSHOT_FILE:-}" ]; then
  SRC="/backups/qdrant/$SNAPSHOT_FILE"
  [ -f "$SRC" ] || { echo "no such snapshot: $SRC"; exit 1; }
  echo "[qdrant] uploading $SRC ..."
  curl -fsS -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/upload?priority=snapshot" \
    -F "snapshot=@$SRC"
  echo ""
  echo "[qdrant] done"
else
  echo "[qdrant] SNAPSHOT_FILE unset, skipping Qdrant restore"
fi
echo "restore complete"
