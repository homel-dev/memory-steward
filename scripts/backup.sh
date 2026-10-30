#!/usr/bin/env bash
# scripts/backup.sh
#
# In-cluster backup. Runs in the tooling image; writes to the mounted backups
# PVC at /backups. Connects to Postgres via libpq env and Qdrant via QDRANT_URL.
# No kubectl, no port-forward, no host.

set -euo pipefail

TS="$(date +%Y%m%d-%H%M%S)"
RETAIN="${RETAIN:-14}"
QDRANT_URL="${QDRANT_URL:-http://qdrant:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-homel_memory}"

mkdir -p /backups/pg /backups/qdrant

echo "[pg] dumping ${PGDATABASE:-homel} ..."
pg_dump -Fc -f "/backups/pg/${PGDATABASE:-homel}-$TS.dump"
ls -1t /backups/pg/*.dump | tail -n +$((RETAIN + 1)) | xargs -r rm -f
echo "[pg] done"

echo "[qdrant] creating snapshot of $QDRANT_COLLECTION ..."
NAME="$(curl -fsS -X POST "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots" \
        | sed -n 's/.*"name":"\([^"]*\)".*/\1/p')"
[ -n "$NAME" ] || { echo "[qdrant] snapshot create failed"; exit 1; }
echo "[qdrant] downloading $NAME ..."
curl -fsS "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$NAME" -o "/backups/qdrant/$NAME"
curl -fsS -X DELETE "$QDRANT_URL/collections/$QDRANT_COLLECTION/snapshots/$NAME" >/dev/null || true
ls -1t /backups/qdrant/*.snapshot 2>/dev/null | tail -n +$((RETAIN + 1)) | xargs -r rm -f || true
echo "[qdrant] done"
echo "backup complete @ $TS"
