import os

os.environ.update({
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_COLLECTION": "test_memory",
    "EMBEDDINGS_URL": "http://localhost:8000",
    "POSTGRES_DSN": "postgresql://test:test@localhost/test",
    "MEMORY_ROUTER_URL": "http://memory-router:8080",
    "STEWARD_URL": "http://memory-steward:8090",
})
