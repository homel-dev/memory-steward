# Memory Steward Embeddings

This component is the local embedding service used by Memory Router, Memory Steward, and MCP reference ingestion.

Implemented endpoints:

- `GET /healthz`
- `POST /embed` with JSON `{ "texts": ["..."], "normalize": true }`

The default model is `BAAI/bge-small-en-v1.5` and can be overridden with `MODEL_NAME`.
