# Memory Steward Embeddings

This component is the local embedding service used by Memory Router, Memory Steward, and MCP reference ingestion.

Implemented endpoints:

- `GET /healthz`
- `POST /embed` with JSON `{ "texts": ["..."], "normalize": true }`

The default model is `BAAI/bge-small-en-v1.5` and can be overridden with `MODEL_NAME`.

## Purpose

Shared dense embedding service for Router retrieval and Steward persistence.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /healthz | Embedding service liveness |
| POST | /embed | Dense embedding generation |

## Model

`MODEL_NAME` defaults to `BAAI/bge-small-en-v1.5` unless overridden.

## Operational role

Embedding failure affects semantic retrieval/admission but does not turn another lane into a semantic substitute. Health checks should be part of full-stack readiness.
