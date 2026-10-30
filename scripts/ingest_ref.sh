#!/usr/bin/env bash
#set -Eeuo pipefail

# Memory Steward Reference Memory ingest.
#
# PROJECTS row format:
#   id|label|connection|project|product|version|path|ref|file_extension
#
# Connection management / discovery:
#   ./scripts/ingest_ref.sh --connections
#   ./scripts/ingest_ref.sh --urls
#   ./scripts/ingest_ref.sh --repos CONNECTION [SEARCH]
#   ./scripts/ingest_ref.sh --test-connection CONNECTION
#   REPO_TOKEN='...' ./scripts/ingest_ref.sh --add-connection NAME PROVIDER BASE_URL [ACCESS_LEVEL]
#
# PROVIDER is one of: gitlab, github, bitbucket.
# ACCESS_LEVEL defaults to read. GitLab read-only connections may omit a token
# when the target GitLab permits anonymous access. Tokens are read from REPO_TOKEN
# first, then provider-specific variables (GITLAB_TOKEN, GITHUB_TOKEN/GH_TOKEN,
# BITBUCKET_TOKEN). GitHub also falls back to `gh auth token` when available.
#
# Ingestion:
#   ./scripts/ingest_ref.sh --list
#   ./scripts/ingest_ref.sh SOURCE_ID [SOURCE_ID ...]
#   ./scripts/ingest_ref.sh                 # ingest all configured sources
#
# Software-book PDF corpus:
#   BOOKS_PROJECT='group/repo' BOOKS_REF='<commit-or-tag>' ./scripts/ingest_ref.sh software-books
# Optional overrides:
#   BOOKS_CONNECTION=msrw
#   BOOKS_VERSION=<reference-memory-version>   # defaults to BOOKS_REF
#
# The software-books source ingests every *.pdf under books/ through the existing
# Git plane. PDF extraction happens inside the Memory Steward MCP image.

readonly REF_SCOPE="${REF_SCOPE:-reference}"
readonly BOOKS_CONNECTION="${BOOKS_CONNECTION:-srv100}"
readonly BOOKS_PROJECT="${BOOKS_PROJECT:-homel-dev/reference-memory}"
readonly BOOKS_REF="${BOOKS_REF:-main}"
readonly BOOKS_VERSION="${BOOKS_VERSION:-${BOOKS_REF}}"

readonly -a PROJECTS=(
  # Base Kubernetes / Crossplane / kro reference sources.
 # 'kubernetes|Kubernetes 1.37 reference|github-public|kubernetes/website|kubernetes|1.37|content/en/docs/reference|7a1c866f252e2d62a0bcdd3ea23a0052e6674679|.md'
 # 'crossplane|Crossplane 2.4 documentation|github-public|crossplane/docs|crossplane|2.4|content/v2.4|d1c9eb7fd1548d0d61ab3901781919a5b4aaf69d|.md'
 # 'kro|Kro 0.10.0|github-public|kubernetes-sigs/kro|kro|0.10.0|website/versioned_docs/version-0.10.0-rc.0|0e8582fd9307bcdba6fe5d6b34becd3f41f4590a|.md'

  # UNICOP product documentation.
#  'netbox|NetBox 4.7.2|github-public|netbox-community/netbox|netbox|4.7.2|docs|v4.7.2|.md'
#  'kafka|Apache Kafka 4.2.2|github-public|apache/kafka|kafka|4.2.2|docs|4.2.2|.md'
#  'awx|AWX 24.6.1|github-public|ansible/awx|awx|24.6.1|docs|24.6.1|.md'
#  'eda|Ansible EDA server snapshot 2026-10-01|github-public|ansible/eda-server|eda-server|main-2026-10-01|docs|1ca0232000b39bf5f9e2ed1ece3703f10ae2b7ec|.md'
#  'bind9|BIND 9.20.29 ARM including DLZ|github-public|isc-projects/bind9|bind9|9.20.29|doc/arm|v9.20.29|.rst'
  # Kubernetes deployment/operator documentation used by the platform.
#  'strimzi|Strimzi Kafka Operator 1.2.0|github-public|strimzi/strimzi-kafka-operator|strimzi|1.2.0|documentation|1.2.0|.adoc'
#  'awx-operator|AWX Operator 2.19.1|github-public|ansible/awx-operator|awx-operator|2.19.1|docs|2.19.1|.md'
#  'eda-operator|Ansible EDA Server Operator snapshot 2026-10-01|github-public|ansible/eda-server-operator|eda-server-operator|main-2026-10-01|docs|a95bbf59c162f9b4dc0133e566a35b954d71d15d|.md'
#  'vault|HashiCorp Vault 2.1.1|github-public|hashicorp/web-unified-docs|vault|2.1.1|content/vault/v2.x/content|4a2f1e91c61b169d2e882ab19b0c50491250b970|.mdx'
#  'terraform|HashiCorp Terraform 1.16.4|github-public|hashicorp/web-unified-docs|terraform|1.16.4|content/terraform/v1.16.x/docs|4a2f1e91c61b169d2e882ab19b0c50491250b970|.mdx'
#  'homel-standards|Homel organization standards|github-public|homel-dev/.github|homel-standards|73dd3a1722cdc116e6c16f76e42ff07375c39b48|docs|73dd3a1722cdc116e6c16f76e42ff07375c39b48|.md'

  # Local GitLab software-engineering book corpus. Set BOOKS_PROJECT to group/repo.
  "software-books|Software engineering reference books|${BOOKS_CONNECTION}|${BOOKS_PROJECT}|software-engineering-books|${BOOKS_VERSION}|books|${BOOKS_REF}|.pdf"

#  'keycloak|Keycloak 26.8.0|github-public|keycloak/keycloak.github.io|keycloak|26.8.0|docs/26.8.0|5c19aed52054ed7c6424a88330a51cb589f251b0|.html'
)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

log() {
  printf '\n==> %s\n' "$*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

resolve_repo_root() {
  local candidate="${MEMORY_STEWARD_DIR:-$PWD}"

  if [[ -f "$candidate/Taskfile.yml" && -f "$candidate/taskfiles/ops.yml" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  if command -v git >/dev/null 2>&1; then
    local root
    root="$(git -C "$candidate" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -n "$root" && -f "$root/Taskfile.yml" && -f "$root/taskfiles/ops.yml" ]]; then
      printf '%s\n' "$root"
      return 0
    fi
  fi

  fail "cannot find memory-steward repository root; run from the repo root or set MEMORY_STEWARD_DIR"
}

enter_repo() {
  local repo_root
  require_cmd task
  repo_root="$(resolve_repo_root)"
  cd "$repo_root"
}

resolve_provider_token() {
  local provider="$1"
  local token="${REPO_TOKEN:-}"

  if [[ -z "$token" ]]; then
    case "$provider" in
      gitlab)
        token="${GITLAB_TOKEN:-}"
        ;;
      github)
        token="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
        if [[ -z "$token" ]] && command -v gh >/dev/null 2>&1; then
          token="$(gh auth token 2>/dev/null || true)"
        fi
        ;;
      bitbucket)
        token="${BITBUCKET_TOKEN:-}"
        ;;
    esac
  fi

  printf '%s\n' "$token"
}

mcp_call() {
  task ops:mcp:call -- "$@"
}

assert_output_ok() {
  local label="$1"
  local output="$2"

  if grep -Eq '(^|[[:space:]])❌|Repo tree fetch failed:|No [^ ]+ files found|DB error:|Qdrant error:|Connection .* failed:|Reference ingestion failed:|errors: [1-9][0-9]*' <<<"$output"; then
    printf '%s\n' "$output" >&2
    fail "$label failed"
  fi
}

print_help() {
  cat <<'HELP'
Usage:
  ./scripts/ingest_ref.sh --list
  ./scripts/ingest_ref.sh --connections
  ./scripts/ingest_ref.sh --urls
  ./scripts/ingest_ref.sh --repos CONNECTION [SEARCH]
  ./scripts/ingest_ref.sh --test-connection CONNECTION
  REPO_TOKEN='...' ./scripts/ingest_ref.sh --add-connection NAME PROVIDER BASE_URL [ACCESS_LEVEL]
  ./scripts/ingest_ref.sh SOURCE_ID [SOURCE_ID ...]
  ./scripts/ingest_ref.sh

Connection discovery:
  --connections / --urls
      List registered Memory Steward Git connections, including provider and base URL.

  --repos CONNECTION [SEARCH]
      List repositories visible through a registered connection. SEARCH is optional.

Connection registration:
  --add-connection NAME PROVIDER BASE_URL [ACCESS_LEVEL]
      PROVIDER: gitlab | github | bitbucket
      ACCESS_LEVEL: read (default) | read-write
      Token lookup: REPO_TOKEN, then provider-specific environment variables.

Examples:
  ./scripts/ingest_ref.sh --connections
  ./scripts/ingest_ref.sh --repos msrw
  ./scripts/ingest_ref.sh --repos msrw books
  ./scripts/ingest_ref.sh --add-connection msrw gitlab http://srv100 read
  REPO_TOKEN="$GITLAB_TOKEN" ./scripts/ingest_ref.sh --add-connection msrw gitlab http://srv100 read
  ./scripts/ingest_ref.sh --test-connection msrw

Software-book corpus:
  BOOKS_PROJECT='group/repo' BOOKS_REF='<commit-or-tag>' ./scripts/ingest_ref.sh software-books

  The source uses connection BOOKS_CONNECTION (default: msrw), path books/,
  extension .pdf, product software-engineering-books, and version BOOKS_VERSION
  (default: BOOKS_REF).
HELP
}

list_projects() {
  local row id label connection project product version path ref extension

  printf '%-16s %-16s %-28s %-26s %-6s %s\n' 'ID' 'CONNECTION' 'PROJECT' 'PRODUCT' 'EXT' 'VERSION / REF'
  printf '%-16s %-16s %-28s %-26s %-6s %s\n' '--' '----------' '-------' '-------' '---' '-------------'

  for row in "${PROJECTS[@]}"; do
    IFS='|' read -r id label connection project product version path ref extension <<<"$row"
    printf '%-16s %-16s %-28s %-26s %-6s %s / %s\n' \
      "$id" "$connection" "$project" "$product" "$extension" "$version" "$ref"
  done
}

list_connections() {
  enter_repo
  mcp_call repo_list
}

list_repositories() {
  local connection="$1"
  local search="${2:-}"

  [[ -n "$connection" ]] || fail "--repos requires CONNECTION"
  enter_repo
  mcp_call git_list_repos \
    "connection=${connection}" \
    "search=${search}" \
    "owned=false"
}

add_connection() {
  local name="$1"
  local provider="$2"
  local base_url="$3"
  local access_level="${4:-read}"
  local token output

  [[ -n "$name" ]] || fail "--add-connection requires NAME"
  [[ "$provider" == 'gitlab' || "$provider" == 'github' || "$provider" == 'bitbucket' ]] \
    || fail "invalid provider '$provider'; expected gitlab, github, or bitbucket"
  [[ -n "$base_url" ]] || fail "--add-connection requires BASE_URL"
  [[ "$access_level" == 'read' || "$access_level" == 'read-write' ]] \
    || fail "invalid access level '$access_level'; expected read or read-write"

  enter_repo
  token="$(resolve_provider_token "$provider")"
  output="$(mcp_call repo_add \
    "name=${name}" \
    "provider=${provider}" \
    "base_url=${base_url}" \
    "token=${token}" \
    "access_level=${access_level}")"
  printf '%s\n' "$output"
  assert_output_ok "connection registration" "$output"
  grep -Fq "Connection '${name}' registered" <<<"$output" \
    || fail "connection '${name}' was not registered"

  log "Testing repository connection: ${name}"
  test_connection "$name"
}

test_connection() {
  local connection="$1"
  local output

  [[ -n "$connection" ]] || fail "connection name is required"
  output="$(mcp_call repo_test "name=${connection}")"
  printf '%s\n' "$output"

  if ! grep -Fq "Connection '${connection}' is working." <<<"$output"; then
    printf '\nRegistered connections / base URLs:\n' >&2
    mcp_call repo_list >&2 || true
    printf '\nAdd or replace a connection with:\n' >&2
    printf "  REPO_TOKEN='...' ./scripts/ingest_ref.sh --add-connection %q gitlab <base-url> read\n" "$connection" >&2
    fail "connection '${connection}' is not usable"
  fi
}

project_selected() {
  local id="$1"
  shift

  (( $# == 0 )) && return 0

  local requested
  for requested in "$@"; do
    [[ "$requested" == "$id" ]] && return 0
  done

  return 1
}

validate_requested_projects() {
  (( $# == 0 )) && return 0

  local requested row id label connection project product version path ref extension found
  for requested in "$@"; do
    found=0
    for row in "${PROJECTS[@]}"; do
      IFS='|' read -r id label connection project product version path ref extension <<<"$row"
      if [[ "$requested" == "$id" ]]; then
        found=1
        break
      fi
    done
    (( found == 1 )) || fail "unknown source id: $requested (use --list)"
  done
}

validate_source_config() {
  local id="$1"
  local connection="$2"
  local project="$3"

  [[ -n "$connection" ]] || fail "source '$id' has no connection"
  [[ -n "$project" ]] || fail "source '$id' has no project"

  if [[ "$project" == '<set BOOKS_PROJECT>' ]]; then
    fail "source 'software-books' requires BOOKS_PROJECT='group/repo' (use --repos ${connection} to discover the project path)"
  fi
}

ingest_repo() {
  local label="$1"
  local connection="$2"
  local project="$3"
  local product="$4"
  local version="$5"
  local path="$6"
  local ref="$7"
  local file_extension="$8"
  local output

  log "Ingesting ${label}: ${project}/${path} @ ${ref} (${file_extension}) via ${connection}"
  output="$(mcp_call git_ingest_repo \
    "connection=${connection}" \
    "project=${project}" \
    "product=${product}" \
    "version=${version}" \
    "scope=${REF_SCOPE}" \
    "path=${path}" \
    "ref=${ref}" \
    "file_extension=${file_extension}")"
  printf '%s\n' "$output"
  assert_output_ok "$label ingest" "$output"
}

verify_reference() {
  local label="$1"
  local product="$2"
  local version="$3"
  local output

  log "Verifying ${label} Reference Memory namespace: ${product}@${version}"
  output="$(mcp_call ref_inspect "product=${product}" "version=${version}" "limit=5")"
  printf '%s\n' "$output"

  if grep -Fq "No reference chunks found for ${product}@${version}." <<<"$output"; then
    fail "$label verification found zero reference chunks"
  fi
  assert_output_ok "$label verification" "$output"
}

main() {
  case "${1:-}" in
    -h|--help)
      print_help
      return 0
      ;;
    --list)
      (( $# == 1 )) || fail "--list does not accept source ids"
      list_projects
      return 0
      ;;
    --connections|--urls)
      (( $# == 1 )) || fail "$1 does not accept arguments"
      list_connections
      return 0
      ;;
    --repos)
      (( $# == 2 || $# == 3 )) || fail "usage: --repos CONNECTION [SEARCH]"
      list_repositories "$2" "${3:-}"
      return 0
      ;;
    --add-connection)
      (( $# == 4 || $# == 5 )) || fail "usage: --add-connection NAME PROVIDER BASE_URL [ACCESS_LEVEL]"
      add_connection "$2" "$3" "$4" "${5:-read}"
      return 0
      ;;
    --test-connection)
      (( $# == 2 )) || fail "usage: --test-connection CONNECTION"
      enter_repo
      test_connection "$2"
      return 0
      ;;
  esac

  validate_requested_projects "$@"
  enter_repo

  local output row id label connection project product version path ref extension
  local ingested=0
  local tested_connections=' '

  log "Checking live Memory Steward MCP"
  output="$(mcp_call diag_health)"
  printf '%s\n' "$output"
  assert_output_ok "Memory Steward MCP health check" "$output"

  for row in "${PROJECTS[@]}"; do
    IFS='|' read -r id label connection project product version path ref extension <<<"$row"
    project_selected "$id" "$@" || continue

    if [[ "$project" == '<set BOOKS_PROJECT>' && $# == 0 ]]; then
      log "Skipping unconfigured source '${id}'; set BOOKS_PROJECT='group/repo' to enable it"
      continue
    fi

    validate_source_config "$id" "$connection" "$project"

    if [[ "$tested_connections" != *" ${connection} "* ]]; then
      log "Testing repository connection: ${connection}"
      test_connection "$connection"
      tested_connections+="${connection} "
    fi

    ingest_repo \
      "$label" \
      "$connection" \
      "$project" \
      "$product" \
      "$version" \
      "$path" \
      "$ref" \
      "$extension"

    verify_reference "$label" "$product" "$version"
    ((++ingested))
  done

  log "Reference namespaces"
  mcp_call ref_list

  printf '\nOK: %d Reference Memory source(s) ingested and verified.\n' "$ingested"
}

main "$@"

