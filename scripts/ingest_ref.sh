#!/usr/bin/env bash
#set -Eeuo pipefail

# Memory Steward Reference Memory ingest.
#
# Add one row to PROJECTS for every documentation source:
#   id|label|github_project|product|version|path|ref|file_extension
#
# Usage:
#   ./ingest_example.sh            # ingest all configured projects
#   ./ingest_example.sh netbox     # ingest selected project(s)
#   ./ingest_example.sh netbox vault bind9
#   ./ingest_example.sh --list     # print configured projects only
#
# GitHub provider in current Memory Steward requires an authenticated token.
# Token lookup order: GITHUB_TOKEN -> GH_TOKEN -> `gh auth token`.

readonly CONNECTION_NAME="${CONNECTION_NAME:-github-public}"
readonly GITHUB_API_URL="https://api.github.com"
readonly REF_SCOPE="${REF_SCOPE:-reference}"

readonly -a PROJECTS=(
  # Base Kubernetes / Crossplane / kro reference sources.
 # 'kubernetes|Kubernetes 1.37 reference|kubernetes/website|kubernetes|1.37|content/en/docs/reference|7a1c866f252e2d62a0bcdd3ea23a0052e6674679|.md'
 # 'crossplane|Crossplane 2.4 documentation|crossplane/docs|crossplane|2.4|content/v2.4|d1c9eb7fd1548d0d61ab3901781919a5b4aaf69d|.md'
 # 'kro|Kro 0.10.0|kubernetes-sigs/kro|kro|0.10.0|website/versioned_docs/version-0.10.0-rc.0|0e8582fd9307bcdba6fe5d6b34becd3f41f4590a|.md'

  # UNICOP product documentation.
#  'netbox|NetBox 4.7.2|netbox-community/netbox|netbox|4.7.2|docs|v4.7.2|.md'
#  'kafka|Apache Kafka 4.2.2|apache/kafka|kafka|4.2.2|docs|4.2.2|.md'
#  'awx|AWX 24.6.1|ansible/awx|awx|24.6.1|docs|24.6.1|.md'
#  'eda|Ansible EDA server snapshot 2026-10-01|ansible/eda-server|eda-server|main-2026-10-01|docs|1ca0232000b39bf5f9e2ed1ece3703f10ae2b7ec|.md'
  'bind9|BIND 9.20.29 ARM including DLZ|isc-projects/bind9|bind9|9.20.29|doc/arm|v9.20.29|.rst'
  # Kubernetes deployment/operator documentation used by the platform.
  'strimzi|Strimzi Kafka Operator 1.2.0|strimzi/strimzi-kafka-operator|strimzi|1.2.0|documentation|1.2.0|.adoc'
  'awx-operator|AWX Operator 2.19.1|ansible/awx-operator|awx-operator|2.19.1|docs|2.19.1|.md'
  'eda-operator|Ansible EDA Server Operator snapshot 2026-10-01|ansible/eda-server-operator|eda-server-operator|main-2026-10-01|docs|a95bbf59c162f9b4dc0133e566a35b954d71d15d|.md'
  'vault|HashiCorp Vault 2.1.1|hashicorp/web-unified-docs|vault|2.1.1|content/vault/v2.x/content|4a2f1e91c61b169d2e882ab19b0c50491250b970|.mdx'
  'terraform|HashiCorp Terraform 1.16.4|hashicorp/web-unified-docs|terraform|1.16.4|content/terraform/v1.16.x/docs|4a2f1e91c61b169d2e882ab19b0c50491250b970|.mdx'
  'keycloak|Keycloak 26.8.0|keycloak/keycloak.github.io|keycloak|26.8.0|docs/26.8.0|5c19aed52054ed7c6424a88330a51cb589f251b0|.html'
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

resolve_github_token() {
  local token="${GITHUB_TOKEN:-${GH_TOKEN:-}}"

  if [[ -z "$token" ]] && command -v gh >/dev/null 2>&1; then
    token="$(gh auth token 2>/dev/null || true)"
  fi

  [[ -n "$token" ]] || fail "GitHub token not found; export GITHUB_TOKEN or GH_TOKEN, or authenticate with 'gh auth login'"
  printf '%s\n' "$token"
}

mcp_call() {
  task ops:mcp:call -- "$@"
}

assert_output_ok() {
  local label="$1"
  local output="$2"

  if grep -Eq '(^|[[:space:]])❌|Repo tree fetch failed:|No [^ ]+ files found|DB error:|Qdrant error:|Connection .* failed:|errors: [1-9][0-9]*' <<<"$output"; then
    printf '%s\n' "$output" >&2
    fail "$label failed"
  fi
}

list_projects() {
  local row id label project product version path ref extension

  printf '%-14s %-24s %-16s %-8s %s\n' 'ID' 'GITHUB PROJECT' 'PRODUCT' 'EXT' 'VERSION / REF'
  printf '%-14s %-24s %-16s %-8s %s\n' '--' '--------------' '-------' '---' '-------------'

  for row in "${PROJECTS[@]}"; do
    IFS='|' read -r id label project product version path ref extension <<<"$row"
    printf '%-14s %-24s %-16s %-8s %s / %s\n' \
      "$id" "$project" "$product" "$extension" "$version" "$ref"
  done
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

  local requested row id label project product version path ref extension found
  for requested in "$@"; do
    found=0
    for row in "${PROJECTS[@]}"; do
      IFS='|' read -r id label project product version path ref extension <<<"$row"
      if [[ "$requested" == "$id" ]]; then
        found=1
        break
      fi
    done
    (( found == 1 )) || fail "unknown project id: $requested (use --list)"
  done
}

ingest_repo() {
  local label="$1"
  local project="$2"
  local product="$3"
  local version="$4"
  local path="$5"
  local ref="$6"
  local file_extension="$7"
  local output

  log "Ingesting ${label}: ${project}/${path} @ ${ref} (${file_extension})"
  output="$(mcp_call git_ingest_repo \
    "connection=${CONNECTION_NAME}" \
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
  if [[ "${1:-}" == '--list' ]]; then
    (( $# == 1 )) || fail "--list does not accept project ids"
    list_projects
    return 0
  fi

  validate_requested_projects "$@"
  require_cmd task

  local repo_root github_token output
  local row id label project product version path ref extension
  local ingested=0

  repo_root="$(resolve_repo_root)"
  github_token="$(resolve_github_token)"
  cd "$repo_root"

  log "Memory Steward repository: $repo_root"

  log "Checking live Memory Steward MCP"
  output="$(mcp_call diag_health)"
  printf '%s\n' "$output"
  assert_output_ok "Memory Steward MCP health check" "$output"

  log "Registering GitHub read-only connection: ${CONNECTION_NAME}"
  output="$(mcp_call repo_add \
    "name=${CONNECTION_NAME}" \
    "provider=github" \
    "base_url=${GITHUB_API_URL}" \
    "token=${github_token}" \
    "access_level=read")"
  printf '%s\n' "$output"
  assert_output_ok "GitHub connection registration" "$output"

  log "Testing GitHub connection"
  output="$(mcp_call repo_test "name=${CONNECTION_NAME}")"
  printf '%s\n' "$output"
  assert_output_ok "GitHub connection test" "$output"
  grep -Fq "Connection '${CONNECTION_NAME}' is working." <<<"$output" \
    || fail "GitHub connection test did not report a working connection"

  for row in "${PROJECTS[@]}"; do
    IFS='|' read -r id label project product version path ref extension <<<"$row"
    project_selected "$id" "$@" || continue

    ingest_repo \
      "$label" \
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

