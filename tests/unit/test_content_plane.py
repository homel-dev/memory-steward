"""
Unit tests for memory_steward_mcp/content_plane.py

Covers:
- _chunk_id determinism and idempotency
- _chunk_markdown section splitting
- _chunk_markdown sliding window for large sections
- _chunk_markdown edge cases
"""
import sys
import types
import pytest
from unittest.mock import MagicMock

# Stub dependencies
for mod in ["psycopg", "qdrant_client", "qdrant_client.http",
            "qdrant_client.http.models", "fastmcp"]:
    m = types.ModuleType(mod)
    sys.modules[mod] = m

_config = types.ModuleType("memory_steward_mcp.config")
_config.POSTGRES_DSN = "postgresql://test"
_config.QDRANT_COLLECTION = "test"
_config.EMBEDDINGS_URL = "http://localhost:8000"
sys.modules["memory_steward_mcp"] = types.ModuleType("memory_steward_mcp")
sys.modules["memory_steward_mcp.config"] = _config

import importlib
cp = importlib.import_module("memory_steward_mcp.content_plane")


# ---------------------------------------------------------------------------
# _chunk_id
# ---------------------------------------------------------------------------

class TestChunkId:

    def test_deterministic(self):
        a = cp._chunk_id("terraform", "1.6", "some content here")
        b = cp._chunk_id("terraform", "1.6", "some content here")
        assert a == b

    def test_different_product_differs(self):
        a = cp._chunk_id("terraform", "1.6", "content")
        b = cp._chunk_id("kubernetes", "1.6", "content")
        assert a != b

    def test_different_version_differs(self):
        a = cp._chunk_id("terraform", "1.5", "content")
        b = cp._chunk_id("terraform", "1.6", "content")
        assert a != b

    def test_different_content_differs(self):
        a = cp._chunk_id("terraform", "1.6", "content_a")
        b = cp._chunk_id("terraform", "1.6", "content_b")
        assert a != b

    def test_format(self):
        cid = cp._chunk_id("terraform", "1.6", "content")
        assert cid.startswith("ref:terraform:1.6:")
        assert len(cid) == len("ref:terraform:1.6:") + 32


# ---------------------------------------------------------------------------
# _chunk_markdown
# ---------------------------------------------------------------------------

class TestChunkMarkdown:

    def test_splits_on_h2(self):
        text = """## Section One
Content of section one.

## Section Two
Content of section two.
"""
        chunks = cp._chunk_markdown(text)
        assert len(chunks) == 2
        assert chunks[0]["section"] == "Section One"
        assert chunks[1]["section"] == "Section Two"

    def test_section_title_extracted(self):
        text = "## My Section\nSome content here."
        chunks = cp._chunk_markdown(text)
        assert chunks[0]["section"] == "My Section"

    def test_content_populated(self):
        text = "## Section\nThis is the body text."
        chunks = cp._chunk_markdown(text)
        assert "body text" in chunks[0]["content"]

    def test_empty_text_returns_empty(self):
        chunks = cp._chunk_markdown("")
        assert chunks == []

    def test_whitespace_only_returns_empty(self):
        chunks = cp._chunk_markdown("   \n\n   ")
        assert chunks == []

    def test_no_h2_treated_as_single_chunk(self):
        text = "Just some plain text without any headers."
        chunks = cp._chunk_markdown(text)
        assert len(chunks) == 1

    def test_large_section_slides_into_parts(self):
        # Generate a section larger than max_chars=1500
        big_body = " ".join([f"word{i}" for i in range(500)])
        text = f"## Big Section\n{big_body}"
        chunks = cp._chunk_markdown(text, max_chars=100)
        assert len(chunks) > 1
        # All parts should reference the section
        assert all("Big Section" in c["section"] for c in chunks)

    def test_multiple_sections_correct_count(self):
        sections = "\n".join([f"## Section {i}\nContent {i}." for i in range(5)])
        chunks = cp._chunk_markdown(sections)
        assert len(chunks) == 5

    def test_section_content_not_empty(self):
        text = "## Section\nActual content here."
        chunks = cp._chunk_markdown(text)
        assert chunks[0]["content"].strip() != ""


# ---------------------------------------------------------------------------
# _embed (mocked)
# ---------------------------------------------------------------------------

class TestEmbed:

    def test_calls_correct_endpoint(self):
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"vectors": [[0.1, 0.2, 0.3]]}

        with patch("memory_steward_mcp.content_plane.requests.post", return_value=mock_resp) as mock_post:
            result = cp._embed(["hello world"])

        call_url = mock_post.call_args[0][0]
        assert call_url.endswith("/embed")

    def test_sends_texts_list(self):
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"vectors": [[0.1, 0.2]]}

        with patch("memory_steward_mcp.content_plane.requests.post", return_value=mock_resp) as mock_post:
            cp._embed(["text one", "text two"])

        payload = mock_post.call_args[1]["json"]
        assert "texts" in payload
        assert isinstance(payload["texts"], list)
        assert payload["normalize"] is True

    def test_returns_vectors(self):
        from unittest.mock import patch, MagicMock
        expected = [[0.1, 0.2], [0.3, 0.4]]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"vectors": expected}

        with patch("memory_steward_mcp.content_plane.requests.post", return_value=mock_resp):
            result = cp._embed(["a", "b"])

        assert result == expected
