# DEPLOYMENT
## Installation and Runtime Entry Points (Minikube + Kubernetes Manifests)
### Repository Root Guide (Non-Canonical)
*Namespace: memory-steward • Owner: architecture-team*

---

## 0. Status, Scope, and Authority

**Status:** OPERATIONAL
**Audience:** Users, operators, contributors
**Change policy:**
- Append-only
- No silent edits

This document defines the operational entry points required to install and run Memory Steward from this repository using Minikube and the `k8s/` manifests.

---

## 1. Quick Start (Local Kubernetes via Minikube)

### 1.1 Prerequisites
You MUST have the following installed:
- `git`
- `kubectl`
- `minikube`

---

## 2. Install (Recommended)

The installer MUST be executed from the repository root:

~~bash
bash install/install.sh install
~~

This command:
- Starts Minikube (profile: `homel`)
- Enables the Minikube ingress addon
- Applies the Kubernetes manifests under `./k8s`
- Waits for core workloads to become Ready
- Initializes the Postgres schema from `./sql`

---

## 3. Access URLs (Ingress)

### 3.1 Cluster Access
Ingress is enabled by default during installation. The concrete URL depends on your local networking.

You MAY use Minikube IP to reach the ingress controller:

~~bash
minikube -p homel ip
~~

> **Warning:** If `k8s/ingress.yaml` uses host-based routing (e.g., `homel.dev`), you MUST map that hostname to the chosen IP (e.g., via `/etc/hosts`) or use a DNS solution that resolves it.

### 3.2 Canonical Hostname (Optional)
If you choose to use a canonical hostname such as:

~~text
https://homel.dev/
~~

You MUST:
- Ensure `homel.dev` resolves to your Minikube ingress endpoint
- Ensure TLS expectations match your `k8s/ingress.yaml` configuration (self-signed vs trusted certificate)

---

## 4. Operational Commands

### 4.1 Apply Manifests
~~bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -n homel -f k8s/
~~

### 4.2 Check Status
~~bash
kubectl get pods -n homel
kubectl get svc -n homel
~~

### 4.3 Logs
~~bash
kubectl logs -n homel -l app=memory-router -f
kubectl logs -n homel -l app=memory-steward -f
~~

---

## 5. Container Images (GHCR)

This repository publishes component images to GitHub Container Registry (GHCR).

Image namespace:
~~text
ghcr.io/homel-dev/memory-steward/<component>:<version>
~~

Components include:
- `embeddings`
- `memory-router`
- `memory-steward`
- `memory-steward-mcp`
- `memory-steward-list`

> **Hard Invariant:** Kubernetes manifests in `k8s/` MUST reference pinned image versions for reproducible deployments.

---

## 6. Closing Statement

This file defines the minimal, user-facing deployment entry points: installer invocation, Kubernetes application, and access patterns. Canonical architecture and system invariants remain in `./docs/`.

---

**END OF DEPLOYMENT**

