# MEMORY STEWARD
## A Deterministic Cognitive Control Plane for LLM Systems
### Foundational Engineering Specification (Root Document)
*Namespace: memory-steward • Owner: architecture-team*

---

## Navigation
**← [Prev: Contributing](CONTRIBUTING.md) | [Next: Architecture Cheat Sheet](ARCHITECTURE_CHEAT_SHEET.md) →**

- [0. Status, Scope, and Authority](#0-status-scope-and-authority)
- [1. What is this?](#1-what-is-this)
- [2. Documentation Index](#2-documentation-index)
- [3. Architecture & Standards](#3-architecture--standards)
- [4. Quick Start (Deployment)](#4-quick-start-deployment)
- [5. License](#5-license)
- [6. Closing Statement](#6-closing-statement)

---

## 0. Status, Scope, and Authority

**Status:** ACTIVE / CANONICAL
**Audience:** General Engineering Public
**Change policy:**
- Append-only
- No silent edits

**Documentation:** [docs/](docs/)

[Back to top](#navigation)

---

## 1. What is this?

Memory Steward is not a chatbot. It is a **Cognitive Control Plane** that enforces determinism, safety, and long-term memory coherence on top of probabilistic LLMs.

It separates **Reasoning** (The Model) from **Memory & Policy** (The Steward), ensuring that critical invariants—like safety rules, personality constraints, and authoritative facts—are never hallucinated or forgotten.

[Back to top](#navigation)

---

## 2. Documentation Index

The system is fully specified in the `docs/` directory.

### 2.1 For Architects (The "Why")
- **[01_overview.md](docs/01_overview.md):** System architecture, taxonomy, and core invariants.
- **[10_industry_landscape.md](docs/10_industry_landscape.md):** Why we built this (vs. RAG/LangChain).
- **[11_design_principles.md](docs/11_design_principles.md):** Async semantics and storage philosophy.

### 2.2 For Engineers (The "How")
- **[02_operational_mode.md](docs/02_operational_mode.md):** How the system decides "Engineering" vs "Casual".
- **[03_reference.md](docs/03_reference.md):** How to ingest documentation (Reference Memory).
- **[04_optimizations.md](docs/04_optimizations.md):** Caching, Speculation, and Latency tuning.
- **[05_stability.md](docs/05_stability.md):** Hysteresis loops to prevent mode jitter.

### 2.3 For Operators (The "Now")
- **[06_telemetry.md](docs/06_telemetry.md):** Metrics, Dashboards, and SQL schemas.
- **[07_glass_pane.md](docs/07_glass_pane.md):** The "Glass Pane" management interface (MCP).
- **[09_runtime_contract.md](docs/09_runtime_contract.md):** Env vars, Ports, and C4 Architecture.

### 2.4 For QA & Maintainers
- **[08_verification.md](docs/08_verification.md):** The "Definition of Done" and regression tests.
- **[00_style_guide.md](docs/00_style_guide.md):** Documentation standards.

[Back to top](#navigation)

---

## 3. Architecture & Standards

Memory Steward is not just a codebase; it is a reference implementation of the **Dual-Plane Memory Architecture**. We adhere to strict engineering standards to prevent "Probabilistic Drift" in production systems. For deep dives and architectural reasoning, please refer to our core documentation:

- **[Technical White Paper](./docs/WHITEPAPER.md):** *The "Engineering Manifesto." Explains the philosophy of Determinism, the "Alignment Tax" of memory, and why we split the system into Data and Control planes.*
- **[RFC Standard (Proposal)](./RFC_PROPOSAL.md):** *The formal specification for the Dual-Plane Architecture. Defines the strict separation of concerns, async admission contracts, and atomic storage requirements.*
- **[Architecture Cheat Sheet](./ARCHITECTURE_CHEAT_SHEET.md):** *A high-density one-pager for System Operators. Contains the C4 System Map, Env Variable Reference, and MCP Tool definitions for quick lookup.*

[Back to top](#navigation)

---

## 4. Quick Start (Deployment)

See **[DEPLOYMENT.md](DEPLOYMENT.md)** for Kubernetes/Docker Compose instructions.

[Back to top](#navigation)

---

## 5. License

Apache License 2.0

See [LICENSE](LICENSE-2.0.txt) file for details.

[Back to top](#navigation)

---

## 6. Closing Statement

This repository constitutes the definitive implementation of the Memory Steward, operating strictly within the invariants defined by the core engineering specifications.

---

**END OF DOCUMENT README**
