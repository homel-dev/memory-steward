# components/memory_steward/tests/test_steward_unit.py
"""
Unit tests for memory_steward/server.py

Covers:
- _hash determinism and uniqueness
- _point_uuid stability
- _sparse_vector structure and token frequency
- _tokenize_lexical
- SPECULATIVE_RE matching
- _extract response parsing (mocked LLM)
"""
import sys
import types
import uuid
import pytest
import importlib
from unittest.mock import MagicMock, patch

# Stub heavy imports
def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod

_stub("psycopg", connect=MagicMock())
_stub("memory_steward.telemetry", StewardTelemetryWriter=MagicMock())

steward = importlib.import_module("memory_steward.server")


# ---------------------------------------------------------------------------
# _hash
# ---------------------------------------------------------------------------

class TestHash:

    def test_deterministic(self):
        assert steward._hash("hello") == steward._hash("hello")

    def test_unique(self):
        assert steward._hash("a") != steward._hash("b")

    def test_length(self):
        assert len(steward._hash("test")) == 64

    def test_project_scoped_collision_resistance(self):
        # Same content, different project → different hash
        h1 = steward._hash("proj_a" + "user name is Bob")
        h2 = steward._hash("proj_b" + "user name is Bob")
        assert h1 != h2


# ---------------------------------------------------------------------------
# _point_uuid
# ---------------------------------------------------------------------------

class TestPointUuid:

    def test_is_valid_uuid(self):
        result = steward._point_uuid("proj1", "some content")
        uuid.UUID(result)  # raises if invalid

    def test_deterministic(self):
        a = steward._point_uuid("proj1", "content")
        b = steward._point_uuid("proj1", "content")
        assert a == b

    def test_different_project_different_uuid(self):
        a = steward._point_uuid("proj1", "content")
        b = steward._point_uuid("proj2", "content")
        assert a != b

    def test_different_content_different_uuid(self):
        a = steward._point_uuid("proj1", "content_a")
        b = steward._point_uuid("proj1", "content_b")
        assert a != b


# ---------------------------------------------------------------------------
# _tokenize_lexical
# ---------------------------------------------------------------------------

class TestTokenizeLexical:

    def test_basic(self):
        tokens = steward._tokenize_lexical("Hello World")
        assert tokens == ["hello", "world"]

    def test_strips_punctuation(self):
        tokens = steward._tokenize_lexical("hello, world!")
        assert "hello" in tokens
        assert "world" in tokens

    def test_empty_string(self):
        assert steward._tokenize_lexical("") == []

    def test_numbers_included(self):
        tokens = steward._tokenize_lexical("project 994")
        assert "994" in tokens

    def test_lowercase(self):
        tokens = steward._tokenize_lexical("PROJECT")
        assert "project" in tokens


# ---------------------------------------------------------------------------
# _sparse_vector
# ---------------------------------------------------------------------------

class TestSparseVector:

    def setup_method(self):
        # Reset the global vocab before each test
        steward._sparse_vocab.clear()

    def test_returns_indices_and_values(self):
        result = steward._sparse_vector("hello world")
        assert "indices" in result
        assert "values" in result

    def test_indices_and_values_same_length(self):
        result = steward._sparse_vector("hello world hello")
        assert len(result["indices"]) == len(result["values"])

    def test_term_frequency_reflected(self):
        # "hello" appears twice, "world" once
        result = steward._sparse_vector("hello world hello")
        # Find index of "hello" in vocab
        hello_idx = steward._sparse_vocab.get("hello")
        assert hello_idx is not None
        pos = result["indices"].index(hello_idx)
        assert result["values"][pos] == 2.0

    def test_empty_string(self):
        result = steward._sparse_vector("")
        assert result["indices"] == []
        assert result["values"] == []

    def test_vocab_grows(self):
        before = len(steward._sparse_vocab)
        steward._sparse_vector("completely new words here")
        assert len(steward._sparse_vocab) > before


# ---------------------------------------------------------------------------
# SPECULATIVE_RE
# ---------------------------------------------------------------------------

class TestSpeculativeRe:

    def test_detects_i_think(self):
        assert steward.SPECULATIVE_RE.search("I think the answer is 42")

    def test_detects_probably(self):
        assert steward.SPECULATIVE_RE.search("probably worth checking")

    def test_detects_might(self):
        assert steward.SPECULATIVE_RE.search("this might be correct")

    def test_detects_seems(self):
        assert steward.SPECULATIVE_RE.search("it seems like a good idea")

    def test_detects_guess(self):
        assert steward.SPECULATIVE_RE.search("I guess we should try")

    def test_does_not_flag_confident_statement(self):
        assert not steward.SPECULATIVE_RE.search("The project code is 994")

    def test_does_not_flag_empty(self):
        assert not steward.SPECULATIVE_RE.search("")

    def test_case_insensitive(self):
        assert steward.SPECULATIVE_RE.search("PROBABLY the best approach")


# ---------------------------------------------------------------------------
# _extract (mocked LLM response)
# ---------------------------------------------------------------------------

class TestExtract:

    def _mock_llm_response(self, fragments):
        import json
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "choices": [{
                "message": {
                    "content": json.dumps({"fragments": fragments})
                }
            }]
        }
        return response

    def test_extracts_fragments(self):
        messages = [{"role": "user", "content": "My project code is 994"}]
        mock_resp = self._mock_llm_response(["Project code is 994"])

        with patch("memory_steward.server.requests.post", return_value=mock_resp):
            result = steward._extract(messages, limit=10)

        assert result == ["Project code is 994"]

    def test_respects_limit(self):
        fragments = [f"fact {i}" for i in range(20)]
        messages = [{"role": "user", "content": "many facts"}]
        mock_resp = self._mock_llm_response(fragments)

        with patch("memory_steward.server.requests.post", return_value=mock_resp):
            result = steward._extract(messages, limit=5)

        assert len(result) <= 5

    def test_empty_fragments_returned_as_empty_list(self):
        messages = [{"role": "user", "content": "hello there"}]
        mock_resp = self._mock_llm_response([])

        with patch("memory_steward.server.requests.post", return_value=mock_resp):
            result = steward._extract(messages, limit=10)

        assert result == []

    def test_only_user_messages_included(self):
        """Assistant messages must not be sent as facts to extract."""
        messages = [
            {"role": "user", "content": "my name is Alice"},
            {"role": "assistant", "content": "nice to meet you"},
        ]
        mock_resp = self._mock_llm_response(["User's name is Alice"])

        with patch("memory_steward.server.requests.post", return_value=mock_resp) as mock_post:
            steward._extract(messages, limit=10)
            call_args = mock_post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
            # The system prompt should contain only user content
            system_content = payload["messages"][0]["content"]
            assert "nice to meet you" not in system_content
            assert "my name is Alice" in system_content
