#!/usr/bin/env bash
# Forward-only migration runner. Runs inside the tooling image and connects
# directly to Postgres through libpq environment variables.
set -euo pipefail

MIGRATIONS_DIR="${MIGRATIONS_DIR:-/opt/tooling/migrations}"
[ -d "$MIGRATIONS_DIR" ] || { echo "ERROR: migrations dir not found: $MIGRATIONS_DIR" >&2; exit 1; }

psql_x() { psql -v ON_ERROR_STOP=1 "$@"; }

ensure_table() {
  psql_x -q -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version    TEXT PRIMARY KEY,
      checksum   TEXT NOT NULL,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );" >/dev/null
}

normalize_legacy_versions() {
  # Releases before the repository cleanup accidentally committed migration
  # filenames 010..050 with a leading space. schema_migrations stores the
  # filename verbatim, so normalizing the repository filenames without this
  # compatibility step would make already-applied migrations appear pending.
  psql_x -q -c "
    WITH legacy AS (
      SELECT version, ltrim(version) AS canonical
      FROM schema_migrations
      WHERE version <> ltrim(version)
    )
    UPDATE schema_migrations AS current
       SET version = legacy.canonical
      FROM legacy
     WHERE current.version = legacy.version
       AND NOT EXISTS (
         SELECT 1
           FROM schema_migrations AS canonical
          WHERE canonical.version = legacy.canonical
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
  normalize_legacy_versions

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
      echo
      printf "INSERT INTO schema_migrations (version, checksum) VALUES ('%s', '%s');\n" "$v" "$sum"
      echo "COMMIT;"
    } | psql_x >/dev/null
    ran=$((ran + 1))
    applied="${applied}${applied:+$'\n'}${v}"
  done

  if [ "$ran" -eq 0 ]; then
    echo "OK: already up to date"
  else
    echo "OK: applied $ran migration(s)"
  fi
}

cmd_status() {
  ensure_table
  normalize_legacy_versions

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
  up) cmd_up ;;
  status) cmd_status ;;
  *) echo "usage: $0 {up|status}" >&2; exit 2 ;;
esac
