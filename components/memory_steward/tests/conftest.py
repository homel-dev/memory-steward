# components/memory_steward/tests/conftest.py
"""
Shared fixtures and environment setup for all tests.
All external dependencies (Postgres, Qdrant, embeddings, LLM) are mocked.
"""
import os
import pytest

# Patch all required env vars before any module import touches them
os.environ.update({
    "POSTGRES_SERVICE_HOST": "localhost",
    "POSTGRES_SERVICE_PORT": "5432",
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_DB": "test",
    "QDRANT_SERVICE_HOST": "localhost",
    "QDRANT_SERVICE_PORT": "6333",
    "EMBEDDINGS_SERVICE_HOST": "localhost",
    "EMBEDDINGS_SERVICE_PORT": "8000",
    "VLLM_STEWARD_SERVICE_HOST": "localhost",
    "VLLM_STEWARD_SERVICE_PORT": "8001",
    "VLLM_BUILDER_SERVICE_HOST": "localhost",
    "VLLM_BUILDER_SERVICE_PORT": "8002",
    "MEMORY_STEWARD_SERVICE_HOST": "localhost",
    "MEMORY_STEWARD_SERVICE_PORT": "8090",
    "QDRANT_COLLECTION": "test_memory",
    "BUILDER_MODEL": "gpt-test",
    "MCP_URL": "http://localhost:8081/mcp",
    "OPEN_WEBUI_URL": "http://localhost:8080",
    "OPEN_WEBUI_API_KEY": "test-key",
    "GITLAB_URL": "https://gitlab.test",
    "GITLAB_TOKEN": "test-token",
})
