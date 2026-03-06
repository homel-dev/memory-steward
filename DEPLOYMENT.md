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

This document defines the operational entry points required to install and run Memory Steward from this repository using Minikube and the `k8s/` manifests. It also defines the canonical bootstrap endpoint `sh.homel.dev`, which is intentionally proxied by Cloudflare and dispatches installer scripts via redirect.

---

## 1. Quick Start (Recommended Bootstrap)

### 1.1 Canonical Install Entry Point (Cloudflare Worker)
The canonical installation UX MUST use the `sh.homel.dev` bootstrap endpoint:

~~~bash
curl -fsSL https://sh.homel.dev/install-ms.sh | bash
~~~

**Behavior:**
- `sh.homel.dev` is intentionally proxied by Cloudflare.
- A Cloudflare Worker is bound to `sh.homel.dev` and handles specific install-script paths.
- For `install-ms.sh`, the Worker returns a redirect-only response:

~~~text
HTTP/2 302
Location: https://raw.githubusercontent.com/homel-dev/memory-steward/main/install/install.sh
Content-Length: 0
~~~

**Hard Invariant:** This Cloudflare Worker + redirect dispatcher pattern is intentional. It MUST NOT be treated as suspicious or “broken DNS”.

### 1.2 Why `curl | bash` Works Here
The bootstrap pattern works because:
- `curl -L` follows redirects.
- HTTPS is preserved end-to-end (Cloudflare terminates TLS and redirects to an HTTPS GitHub raw URL).

> **Warning:** If you omit `-L`, `curl` will not follow the redirect and the install will fail.

**Recommended hardened form:**
~~~bash
curl -fsSL -L https://sh.homel.dev/install-ms.sh | bash
~~~

[Back to top](#navigation)

---

## 2. Prerequisites (Local Kubernetes via Minikube)

You MUST have the following installed:
- `git`
- `kubectl`
- `minikube`

[Back to top](#navigation)

---

## 3. What the Installer Does

The installer script bootstraps a local environment by:
- Starting Minikube (profile: `homel`)
- Enabling the Minikube ingress addon
- Applying the Kubernetes manifests under `./k8s` into namespace `homel`
- Waiting for core workloads to become Ready
- Initializing the Postgres schema from `./sql`

[Back to top](#navigation)

---

## 4. Access URLs (Ingress)

Ingress is enabled by default during installation. The concrete URL depends on your local networking.

You MAY use Minikube IP to reach the ingress controller:

~~~bash
minikube -p homel ip
~~~

> **Warning:** If `k8s/ingress.yaml` uses host-based routing (e.g., `homel.dev`), you MUST map that hostname to the chosen IP (e.g., via `/etc/hosts`) or use a DNS solution that resolves it.

[Back to top](#navigation)

---

## 5. Operational Commands

### 5.1 Apply Manifests
~~~bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -n homel -f k8s/
~~~

### 5.2 Check Status
~~~bash
kubectl get pods -n homel
kubectl get svc -n homel
~~~

### 5.3 Logs
~~~bash
kubectl logs -n homel -l app=memory-router -f
kubectl logs -n homel -l app=memory-steward -f
~~~

[Back to top](#navigation)

---

## 6. Container Images (GHCR)

This repository publishes component images to GitHub Container Registry (GHCR).

Image namespace:
~~~text
ghcr.io/homel-dev/memory-steward/<component>:<version>
~~~

Components include:
- `embeddings`
- `memory-router`
- `memory-steward`
- `memory-steward-mcp`
- `memory-steward-list`

**Hard Invariant:** Kubernetes manifests in `k8s/` MUST reference pinned image versions for reproducible deployments.

[Back to top](#navigation)

---

## 7. Cloudflare Worker Notes (Optional Hardening)

The Cloudflare Worker currently returns a redirect-only `302`. This is correct and preferred for install dispatchers.

If you want additional hardening, the Worker MAY add:
- `Cache-Control: no-store`
- `Content-Type: text/plain; charset=utf-8` (even for redirects)
- Path allow-listing (serve only known `/install-*.sh` endpoints; return `404` for everything else)

These are optional and not required for correctness.

[Back to top](#navigation)

---

## 8. Closing Statement

This file defines the operational entry points for installation and local deployment. The `sh.homel.dev` Cloudflare Worker dispatcher is a deliberate, stable bootstrap mechanism that redirects to the canonical installer script hosted in GitHub.

---

**END OF DEPLOYMENT**

