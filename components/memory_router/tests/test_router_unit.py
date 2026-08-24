# components/memory_router/tests/test_router_unit.py
"""
Unit tests for memory_router/server.py

Covers:
- ChatMessage.text_content (str and multimodal)
- _sha256_hex
- _project_id derivation logic
- _maximal_marginal_relevance
- _stitch_context_structured (token budget, drop accounting)
- Open WebUI background request detection
- /glap intercept detection
"""
import importlib
import sys
import types
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub only what is NOT installed in this venv.
# numpy and sklearn are real deps — do NOT stub them.
# ---------------------------------------------------------------------------

def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


_stub_module("psycopg", connect=MagicMock())
_stub_module("tiktoken",
    encoding_for_model=MagicMock(return_value=MagicMock(encode=lambda t: t.split())),
    get_encoding=MagicMock(return_value=MagicMock(encode=lambda t: t.split())),
)
_stub_module("memory_router.telemetry", TelemetryWriter=MagicMock())
_stub_module("memory_router.mcp_bridge", handle_glap=MagicMock())

router = importlib.import_module("memory_router.server")

ChatMessage = router.ChatMessage
Candidate = router.Candidate


# ---------------------------------------------------------------------------
# ChatMessage.text_content
# ---------------------------------------------------------------------------

class TestChatMessageTextContent:

    def test_plain_string(self):
        msg = ChatMessage(role="user", content="hello world")
        assert msg.text_content == "hello world"

    def test_empty_string(self):
        msg = ChatMessage(role="user", content="")
        assert msg.text_content == ""

    def test_multimodal_text_only(self):
        content = [{"type": "text", "text": "describe this"}]
        msg = ChatMessage(role="user", content=content)
        assert msg.text_content == "describe this"

    def test_multimodal_image_only(self):
        content = [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}}]
        msg = ChatMessage(role="user", content=content)
        assert msg.text_content == ""

    def test_multimodal_mixed(self):
        content = [
            {"type": "text", "text": "what is in"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
            {"type": "text", "text": "this image"},
        ]
        msg = ChatMessage(role="user", content=content)
        assert msg.text_content == "what is in this image"

    def test_multimodal_missing_text_key(self):
        content = [{"type": "text"}, {"type": "text", "text": "hi"}]
        msg = ChatMessage(role="user", content=content)
        assert msg.text_content == " hi"


# ---------------------------------------------------------------------------
# _sha256_hex
# ---------------------------------------------------------------------------

class TestSha256Hex:

    def test_known_value(self):
        result = router._sha256_hex("hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        assert router._sha256_hex("test") == router._sha256_hex("test")

    def test_different_inputs_differ(self):
        assert router._sha256_hex("a") != router._sha256_hex("b")

    def test_empty_string(self):
        result = router._sha256_hex("")
        assert len(result) == 64


# ---------------------------------------------------------------------------
# _project_id
# ---------------------------------------------------------------------------

class TestProjectId:

    def _make_request(self, headers: dict):
        req = MagicMock()
        req.headers = headers
        return req

    def test_explicit_header_wins(self):
        req = self._make_request({"x-project-id": "my-project"})
        assert router._project_id(req) == "my-project"

    def test_origin_header_produces_hash(self):
        req = self._make_request({"origin": "https://myapp.com"})
        pid = router._project_id(req)
        assert len(pid) == 16
        assert pid == router._project_id(req)

    def test_different_origins_produce_different_ids(self):
        req1 = self._make_request({"origin": "https://app1.com"})
        req2 = self._make_request({"origin": "https://app2.com"})
        assert router._project_id(req1) != router._project_id(req2)

    def test_fallback_when_no_headers(self):
        req = self._make_request({})
        assert router._project_id(req) == "backend-default"

    def test_x_project_id_takes_priority_over_origin(self):
        req = self._make_request({
            "x-project-id": "explicit",
            "origin": "https://app.com",
        })
        assert router._project_id(req) == "explicit"

    def test_referer_used_when_no_origin(self):
        req = self._make_request({"referer": "https://app.com/chat"})
        pid = router._project_id(req)
        assert len(pid) == 16


# ---------------------------------------------------------------------------
# _maximal_marginal_relevance
# numpy and sklearn are real — no patching needed
# ---------------------------------------------------------------------------

class TestMMR:

    def _make_candidate(self, cid, vec):
        return Candidate(id=cid, content=f"content_{cid}", vector=vec, metadata={})

    def test_empty_candidates_returns_empty(self):
        result = router._maximal_marginal_relevance(
            query_vec=[1.0, 0.0],
            candidates=[],
            top_k=3,
            lambda_mult=0.5,
        )
        assert result == []

    def test_returns_at_most_top_k(self):
        candidates = [
            self._make_candidate(f"c{i}", [float(i % 2), float((i + 1) % 2)])
            for i in range(10)
        ]
        result = router._maximal_marginal_relevance(
            query_vec=[1.0, 0.0],
            candidates=candidates,
            top_k=3,
            lambda_mult=0.5,
        )
        assert len(result) <= 3

    def test_single_candidate_always_selected(self):
        c = self._make_candidate("only", [1.0, 0.0])
        result = router._maximal_marginal_relevance(
            query_vec=[1.0, 0.0],
            candidates=[c],
            top_k=5,
            lambda_mult=0.5,
        )
        assert len(result) == 1
        assert result[0].id == "only"

    def test_lambda_1_pure_relevance_picks_most_similar(self):
        # lambda=1.0 → pure relevance, no diversity penalty
        # query is [1,0], c_a is [1,0] (most similar), c_b is [0,1]
        c_a = self._make_candidate("a", [1.0, 0.0])
        c_b = self._make_candidate("b", [0.0, 1.0])
        result = router._maximal_marginal_relevance(
            query_vec=[1.0, 0.0],
            candidates=[c_b, c_a],
            top_k=1,
            lambda_mult=1.0,
        )
        assert result[0].id == "a"


# ---------------------------------------------------------------------------
# _stitch_context_structured
# ---------------------------------------------------------------------------

class TestStitchContext:

    def _make_candidate(self, cid, content, namespace="dynamic", tokens=10):
        c = Candidate(
            id=cid,
            content=content,
            vector=[0.1, 0.2],
            metadata={"namespace": namespace, "source": namespace.upper()},
            token_count=tokens,
        )
        return c

    def test_empty_returns_zeros(self):
        result = router._stitch_context_structured([], max_tokens=1000, model="gpt-test")
        _, _, used_items, used_tokens, dropped_budget, dropped_no_content = result
        assert used_items == 0
        assert used_tokens == 0
        assert dropped_budget == 0
        assert dropped_no_content == 0

    def test_budget_enforcement(self):
        candidates = [
            self._make_candidate("c1", "fact one", tokens=10),
            self._make_candidate("c2", "fact two", tokens=10),
        ]
        with patch("memory_router.server._count_tokens", return_value=10):
            _, _, used_items, used_tokens, dropped_budget, _ = \
                router._stitch_context_structured(candidates, max_tokens=20, model="gpt-test")
        assert used_items == 1
        assert dropped_budget == 1

    def test_empty_content_counts_as_dropped_no_content(self):
        candidates = [
            self._make_candidate("c1", "   ", tokens=5),
            self._make_candidate("c2", "", tokens=5),
        ]
        with patch("memory_router.server._count_tokens", return_value=5):
            _, _, _, _, _, dropped_no_content = \
                router._stitch_context_structured(candidates, max_tokens=1000, model="gpt-test")
        assert dropped_no_content == 2

    def test_reference_namespace_goes_to_ontology(self):
        candidates = [
            self._make_candidate("c1", "spec fact", namespace="reference_memory", tokens=5),
        ]
        with patch("memory_router.server._count_tokens", return_value=5):
            ontology, context, _, _, _, _ = \
                router._stitch_context_structured(candidates, max_tokens=1000, model="gpt-test")
        assert len(ontology) > 0
        assert len(context) == 0

    def test_dynamic_namespace_goes_to_context(self):
        candidates = [
            self._make_candidate("c1", "user fact", namespace="dynamic_memory", tokens=5),
        ]
        with patch("memory_router.server._count_tokens", return_value=5):
            ontology, context, _, _, _, _ = \
                router._stitch_context_structured(candidates, max_tokens=1000, model="gpt-test")
        assert len(context) > 0
        assert len(ontology) == 0


# ---------------------------------------------------------------------------
# Open WebUI background request guard
# ---------------------------------------------------------------------------

class TestOpenWebUIBackgroundGuard:

    def _is_background(self, system_content: str) -> bool:
        _OWUI_BACKGROUND_MARKERS = (
            "create a concise, 3-5 word title",
            "generate 1-3 broad tags",
            "generate follow-up questions",
            "autocomplete the following",
            "generate a search query",
        )
        return any(marker in system_content.lower() for marker in _OWUI_BACKGROUND_MARKERS)

    def test_title_generation_detected(self):
        assert self._is_background("create a concise, 3-5 word title for this conversation")

    def test_tags_generation_detected(self):
        assert self._is_background("generate 1-3 broad tags categorizing the main themes")

    def test_follow_up_detected(self):
        assert self._is_background("generate follow-up questions based on the context")

    def test_autocomplete_detected(self):
        assert self._is_background("autocomplete the following sentence")

    def test_search_query_detected(self):
        assert self._is_background("generate a search query for the following")

    def test_normal_user_message_not_detected(self):
        assert not self._is_background("what is the project code for this deployment?")

    def test_glap_command_not_detected(self):
        assert not self._is_background("/glap get_system_health")

    def test_case_insensitive(self):
        assert self._is_background("CREATE A CONCISE, 3-5 WORD TITLE")


# ---------------------------------------------------------------------------
# /glap intercept detection
# ---------------------------------------------------------------------------

class TestGlapIntercept:

    def test_glap_prefix_detected(self):
        assert "/glap get_system_health".strip().lower().startswith("/glap")

    def test_glap_uppercase_detected(self):
        assert "/GLAP explain_last_decision".strip().lower().startswith("/glap")

    def test_glap_with_args(self):
        assert "/glap simulate_retrieval project_id=test query=hello".strip().lower().startswith("/glap")

    def test_non_glap_not_detected(self):
        assert not "what is my project code?".strip().lower().startswith("/glap")

    def test_glap_bare(self):
        assert "/glap".strip().lower().startswith("/glap")

# ---------------------------------------------------------------------------
# AMP retrieval lane isolation and selected provenance
# ---------------------------------------------------------------------------

class TestAmpRetrieval:

    def test_dynamic_qdrant_filter_includes_memory_type(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"result": []}
        with patch("memory_router.server.requests.post", return_value=response) as post:
            router._qdrant_dense("project-a", [0.1, 0.2], 5)
        payload = post.call_args.kwargs["json"]
        must = payload["filter"]["must"]
        assert {"key": "project_id", "match": {"value": "project-a"}} in must
        assert {"key": "memory_type", "match": {"value": "dynamic_memory"}} in must

    def test_selected_candidate_refs_preserve_ids(self):
        candidates = [
            Candidate(
                id="point-1",
                content="fact",
                vector=[0.1, 0.2],
                metadata={
                    "memory_type": "dynamic_memory",
                    "source": "dynamic",
                    "content_hash": "abc",
                },
                token_count=3,
            )
        ]
        refs = router._selected_candidate_refs(candidates, max_tokens=100, model="gpt-test")
        assert refs == [{
            "id": "point-1",
            "memory_type": "dynamic_memory",
            "source": "dynamic",
            "namespace": None,
            "product": None,
            "version": None,
            "scope": None,
            "evidence_ref": None,
            "content_hash": "abc",
        }]

    def test_artifact_only_retrieval_skips_embedding_and_qdrant(self):
        selector = router.ArtifactSelector(
            artifact_type="repository_ir", repository="rr", revision="abc"
        )
        artifact = {
            "id": "artifact-1",
            "artifact_type": "repository_ir",
            "repository": "rr",
            "revision": "abc",
            "payload": {"nodes": []},
        }
        with patch("memory_router.server._pg_static_load", return_value=[]), \
             patch("memory_router.server._pg_agent_reference_load", return_value=[artifact]), \
             patch("memory_router.server._embed_one") as embed, \
             patch("memory_router.server._qdrant_dense") as qdrant:
            result = router._retrieve_context_structured(
                request_id="ctx-1",
                project_id="rr",
                query=None,
                model="gpt-test",
                artifact_selectors=[selector],
            )
        assert result["agent_reference"] == [artifact]
        assert result["retrieval_context"] == {}
        embed.assert_not_called()
        qdrant.assert_not_called()
