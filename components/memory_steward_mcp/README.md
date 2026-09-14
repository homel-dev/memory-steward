# Memory Steward MCP

Memory Steward MCP is the internal operator and agent tool surface for Memory Steward.

It exposes FastMCP tools for Reference Memory ingestion/inspection, static-memory management, diagnostics, runtime configuration, Git ingestion, and AMP adapters. Agent-facing tools delegate retrieval to Memory Router and admission/feedback to Memory Steward rather than implementing a second policy engine.

The Kubernetes service is ClusterIP-only. Operators can use the repository Task targets (`task ops:mcp:tools`, `task ops:mcp:call`, and `task ops:reference:*`) or a loopback-only port-forward instead of exposing MCP publicly.
