#!/usr/bin/env bash
# scripts/migrate.sh
#
# Forward-only migration runner. Runs INSIDE the tooling image as an ephemeral
# Job and connects DIRECTLY to Postgres via libpq env vars
# (PGHOST / PGPORT / PGUSER / PGPASSWORD / PGDATABASE). No kubectl, no host.
#
# Tracks applied files in schema_migrations (version = filename); applies only
# files not yet recorded, each in its own transaction. Safe after a restore:
# the dump already carries schema_migrations, so only newer files run.
#
# Migration files contain plain DDL. Whole-line BEGIN;/COMMIT; are stripped so
# the runner owns one transaction per migration (file + bookkeeping = atomic).
#
# Usage: migrate.sh {up|status}

set -euo pipefail

MIGRATIONS_DIR="${MIGRATIONS_DIR:-/opt/tooling/migrations}"
[ -d "$MIGRATIONS_DIR" ] || { echo "ERROR: migrations dir not found: $MIGRATIONS_DIR" >&2; exit 1; }

# libpq env supplies the connection. ON_ERROR_STOP makes any failure fatal.
psql_x() { psql -v ON_ERROR_STOP=1 "$@"; }

ensure_table() {
  psql_x -q -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version    TEXT PRIMARY KEY,
      checksum   TEXT NOT NULL,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );" >/dev/null
}

applied_versions() {
  psql_x -t -A -c "SELECT version FROM schema_migrations ORDER BY version;"
}

strip_txn() {
  sed -E '/^[[:space:]]*(BEGIN|COMMIT)[[:space:]]*;[[:space:]]*$/Id' "$1"
}

cmd_up() {
  ensure_table
  local applied ran=0 f v sum
  applied="$(applied_versions)"
  for f in "$MIGRATIONS_DIR"/*.sql; do
    [ -e "$f" ] || continue
    v="$(basename "$f")"
    printf '%s\n' "$applied" | grep -qxF "$v" && continue
    sum="$(sha256sum "$f" | awk '{print $1}')"
    echo ">> applying $v"
    {
      echo "BEGIN;"
      strip_txn "$f"
      echo ""
      echo "INSERT INTO schema_migrations (version, checksum) VALUES ('$v', '$sum');"
      echo "COMMIT;"
    } | psql_x >/dev/null
    ran=$((ran + 1))
  done
  if [ "$ran" -eq 0 ]; then echo "OK: already up to date"; else echo "OK: applied $ran migration(s)"; fi
}

cmd_status() {
  ensure_table
  local applied f v
  applied="$(applied_versions)"
  for f in "$MIGRATIONS_DIR"/*.sql; do
    [ -e "$f" ] || continue
    v="$(basename "$f")"
    if printf '%s\n' "$applied" | grep -qxF "$v"; then
      printf "applied  %s\n" "$v"
    else
      printf "PENDING  %s\n" "$v"
    fi
  done
}

case "${1:-up}" in
  up)     cmd_up ;;
  status) cmd_status ;;
  *) echo "usage: $0 {up|status}" >&2; exit 2 ;;
esac
