# Memory Steward

Memory Steward is the durable-memory admission service.

It receives completed chat turns and structured agent outcomes, uses the configured Steward LLM to extract durable knowledge candidates, persists accepted dynamic-memory fragments to Postgres, and indexes their dense/lexical representations in Qdrant. It also persists reusable AMP agent-reference artifacts and retrieval feedback.

The service does not answer user chat requests and does not currently classify operational mode. See the repository root `README.md`, `docs/01_overview.md`, `docs/12_extensions.md`, and `docs/13_admission_control.md` for the implemented authority boundaries and known admission-control gaps.
