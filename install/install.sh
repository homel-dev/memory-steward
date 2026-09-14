#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/homel-dev/memory-steward.git"
MINIKUBE_PROFILE="minikube"

die() { echo "[ERROR] $*" >&2; exit 1; }
info() { echo "[INFO] $*"; }
command_exists() { command -v "$1" >/dev/null 2>&1; }

check_prereqs() {
  for cmd in git kubectl minikube task; do
    command_exists "$cmd" || die "Missing required command: $cmd"
  done
}

clone_repo() {
  if [[ -d .git ]]; then
    return
  fi
  git clone "$REPO_URL"
  cd memory-steward
}

start_minikube() {
  if ! minikube status -p "$MINIKUBE_PROFILE" >/dev/null 2>&1; then
    minikube start -p "$MINIKUBE_PROFILE"
  fi
  minikube -p "$MINIKUBE_PROFILE" update-context
  minikube -p "$MINIKUBE_PROFILE" addons enable ingress
}

usage() {
  cat <<'EOF'
Memory Steward Installer

Usage: ./install.sh [install|up|wait|db-init|status|help]

  install   Start Minikube and run the repository's complete `task up` flow (default)
  up        Start Minikube and deploy through `task up`
  wait      Wait for every runtime workload through `task ops:service:wait`
  db-init   Run `task db:init`
  status    Run `task ops:service:status`
  help      Show this help
EOF
}

main() {
  local cmd="${1:-install}"
  case "$cmd" in
    install|up)
      check_prereqs
      clone_repo
      start_minikube
      task up
      ;;
    wait)
      check_prereqs
      task ops:service:wait
      ;;
    db-init)
      check_prereqs
      task db:init
      ;;
    status)
      check_prereqs
      task ops:service:status
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      die "Unknown command: $cmd"
      ;;
  esac
}

main "$@"
