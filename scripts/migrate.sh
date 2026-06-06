#!/usr/bin/env bash
# scripts/migrate.sh
#
# Minimal forward-only migration runner for the memory-store Postgres.
# - Tracks applied files in a schema_migrations table (version = filename).
# - Applies ONLY files not yet recorded, each in its own transaction.
# - Safe to run after a restore: the dump already contains schema_migrations,
#   so this applies only what postdates the dump.
#
# It executes psql *inside* the postgres pod via kubectl exec, matching the
# pattern the Taskfile already uses (db:shell / verify:flow).
#
# Assumptions:
#   - Migration files live in sql/migrations/*.sql and sort lexically (000_, 010_, ...).
#   - Files contain plain DDL. Any whole-line `BEGIN;` / `COMMIT;` is stripped so
#     the runner can own one transaction per migration (file + bookkeeping = atomic).
#     => Do not rely on a file opening multiple independent transactions.
#
# Usage:
#   bash scripts/migrate.sh up       # apply pending migrations
#   bash scripts/migrate.sh status   # show applied vs pending
#   bash scripts/migrate.sh verify   # warn if an applied file changed on disk

set -euo pipefail

NAMESPACE="${NAMESPACE:-ms}"
PG_USER="${PG_USER:-homel}"
PG_DB="${PG_DB:-homel}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-sql/migrations}"

POD="$(kubectl get pod -n "$NAMESPACE" -l app=postgres \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
[ -n "$POD" ] || { echo "ERROR: no postgres pod found in namespace '$NAMESPACE'" >&2; exit 1; }
[ -d "$MIGRATIONS_DIR" ] || { echo "ERROR: migrations dir not found: $MIGRATIONS_DIR" >&2; exit 1; }

# Run psql in the pod. Extra args are passed through.
psql_exec() {
  kubectl exec -i -n "$NAMESPACE" "$POD" -- \
    psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 "$@"
}

ensure_table() {
  psql_exec -q -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version    TEXT PRIMARY KEY,
      checksum   TEXT NOT NULL,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );" >/dev/null
}

applied_versions() {
  psql_exec -t -A -c "SELECT version FROM schema_migrations ORDER BY version;"
}

# Remove standalone BEGIN;/COMMIT; lines (case-insensitive) so the runner owns the txn.
strip_txn() {
  sed -E '/^[[:space:]]*(BEGIN|COMMIT)[[:space:]]*;[[:space:]]*$/Id' "$1"
}

cmd_status() {
  ensure_table
  local applied; applied="$(applied_versions)"
  printf "%-38s %s\n" "MIGRATION" "STATE"
  printf "%-38s %s\n" "--------------------------------------" "-------"
  local f v
  for f in "$MIGRATIONS_DIR"/*.sql; do
    [ -e "$f" ] || continue
    v="$(basename "$f")"
    if printf '%s\n' "$applied" | grep -qxF "$v"; then
      printf "%-38s %s\n" "$v" "applied"
    else
      printf "%-38s %s\n" "$v" "PENDING"
    fi
  done
}

cmd_up() {
  ensure_table
  local applied; applied="$(applied_versions)"
  local ran=0 f v sum
  for f in "$MIGRATIONS_DIR"/*.sql; do
    [ -e "$f" ] || continue
    v="$(basename "$f")"
    if printf '%s\n' "$applied" | grep -qxF "$v"; then
      continue
    fi
    sum="$(sha256sum "$f" | awk '{print $1}')"
    echo ">> applying $v"
    {
      echo "BEGIN;"
      strip_txn "$f"
      echo ""
      echo "INSERT INTO schema_migrations (version, checksum) VALUES ('$v', '$sum');"
      echo "COMMIT;"
    } | psql_exec >/dev/null
    ran=$((ran + 1))
  done
  if [ "$ran" -eq 0 ]; then
    echo "OK: already up to date"
  else
    echo "OK: applied $ran migration(s)"
  fi
}

cmd_verify() {
  ensure_table
  local f v sum rec drift=0
  for f in "$MIGRATIONS_DIR"/*.sql; do
    [ -e "$f" ] || continue
    v="$(basename "$f")"
    sum="$(sha256sum "$f" | awk '{print $1}')"
    rec="$(psql_exec -t -A -c "SELECT checksum FROM schema_migrations WHERE version='$v';")"
    if [ -n "$rec" ] && [ "$rec" != "$sum" ]; then
      echo "WARN drift: $v changed on disk after apply (db=$rec disk=$sum)"
      drift=1
    fi
  done
  [ "$drift" -eq 0 ] && echo "OK: no drift"
}

case "${1:-up}" in
  up)     cmd_up ;;
  status) cmd_status ;;
  verify) cmd_verify ;;
  *) echo "usage: $0 {up|status|verify}" >&2; exit 2 ;;
esac
