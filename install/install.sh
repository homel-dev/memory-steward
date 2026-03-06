#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="memory-steward-installer"
REPO_URL="https://github.com/homel-dev/memory-steward.git"
DEFAULT_NAMESPACE="homel"
MINIKUBE_PROFILE="homel"

die() { echo "[ERROR] $*" >&2; exit 1; }
info() { echo "[INFO] $*"; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

check_prereqs() {
  info "Checking prerequisites..."
  for cmd in git kubectl minikube; do
    command_exists "$cmd" || die "Missing required command: $cmd"
  done
}

clone_repo() {
  if [[ -d ".git" ]]; then
    info "Running inside repository — skipping clone"
    return
  fi
  info "Cloning Memory Steward repository..."
  git clone "$REPO_URL"
  cd memory-steward
}

start_minikube() {
  info "Starting Minikube profile: $MINIKUBE_PROFILE"
  if minikube status -p "$MINIKUBE_PROFILE" >/dev/null 2>&1; then
    info "Minikube already running"
  else
    minikube start -p "$MINIKUBE_PROFILE"
  fi

  # Ensure kubectl points at this minikube profile
  minikube -p "$MINIKUBE_PROFILE" update-context
}

enable_ingress() {
  info "Enabling Minikube ingress addon..."
  minikube -p "$MINIKUBE_PROFILE" addons enable ingress
}

apply_manifests() {
  info "Applying Kubernetes manifests..."
  kubectl apply -f k8s/namespace.yaml

  # Apply everything canonical (keeps repo as source of truth)
  kubectl apply -n "$DEFAULT_NAMESPACE" -f k8s/
  kubectl apply -n "$DEFAULT_NAMESPACE" -f k8s/vector/ 2>/dev/null || true
  kubectl apply -n "$DEFAULT_NAMESPACE" -f k8s/grafana/ 2>/dev/null || true

  # Ingress routing (enabled by default per your decision)
  kubectl apply -n "$DEFAULT_NAMESPACE" -f k8s/ingress.yaml
}

wait_ready() {
  info "Waiting for core workloads to become ready..."

  # These names match your Taskfile; adjust if manifests differ.
  kubectl rollout status -n "$DEFAULT_NAMESPACE" statefulset/postgres --timeout=180s
  kubectl rollout status -n "$DEFAULT_NAMESPACE" statefulset/qdrant --timeout=180s

  kubectl rollout status -n "$DEFAULT_NAMESPACE" deployment/memory-router --timeout=180s
  kubectl rollout status -n "$DEFAULT_NAMESPACE" deployment/memory-steward --timeout=180s
}

init_db() {
  info "Initializing database schema..."

  local postgres_pod
  postgres_pod="$(kubectl get pod -n "$DEFAULT_NAMESPACE" -l app=postgres -o jsonpath='{.items[0].metadata.name}')"
  [[ -n "$postgres_pod" ]] || die "Could not find Postgres pod (label app=postgres) in namespace $DEFAULT_NAMESPACE"

  # Use the same approach as Taskfile: pipe local SQL into psql in the pod.
  cat sql/schema.sql sql/010_telemetry_schema.sql | \
    kubectl exec -i -n "$DEFAULT_NAMESPACE" "$postgres_pod" -- \
    psql -U homel -d homel -v ON_ERROR_STOP=1
}

usage() {
  cat <<EOF

Memory Steward Installer

Usage:
  ./install.sh [command]

Commands:
  install     Full installation (default)
  up          Start Minikube + enable ingress + apply manifests
  wait        Wait for workloads to be Ready
  db-init     Initialize Postgres schema only
  help        Show this help

Examples:
  ./install.sh
  ./install.sh up
  ./install.sh wait
  ./install.sh db-init

EOF
}

main() {
  local cmd="${1:-install}"

  case "$cmd" in
    install)
      check_prereqs
      clone_repo
      start_minikube
      enable_ingress
      apply_manifests
      wait_ready
      init_db
      ;;
    up)
      check_prereqs
      clone_repo
      start_minikube
      enable_ingress
      apply_manifests
      ;;
    wait)
      wait_ready
      ;;
    db-init)
      check_prereqs
      clone_repo
      start_minikube
      init_db
      ;;
    help|-h|--help)
      usage
      ;;
    *)
      die "Unknown command: $cmd"
      ;;
  esac

  info "Done."
}

main "$@"

