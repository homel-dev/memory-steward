# Memory Steward Embeddings

This component is the local embedding service used by Memory Router, Memory Steward, and MCP reference ingestion.

Implemented endpoints:

- `GET /healthz`
- `POST /embed` with JSON `{ "texts": ["..."], "normalize": true }`

The default model is `BAAI/bge-small-en-v1.5` and can be overridden with `MODEL_NAME`. CPU inference is deliberately bounded: the default ONNX thread count is 4, internal FastEmbed batch size is 16, and requests larger than 64 texts are rejected. Kubernetes also caps the Pod at 4 CPU.

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


## Resource bounds

The runtime knobs are `EMBEDDING_THREADS`, `EMBEDDING_BATCH_SIZE`, `EMBEDDING_MAX_TEXTS`, and `EMBEDDING_CONCURRENCY`. The checked-in Deployment also constrains common native/tokenizer thread pools (`OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `NUMEXPR_NUM_THREADS`, `TOKENIZERS_PARALLELISM`) so a large ingestion request cannot fan out across every host CPU.
