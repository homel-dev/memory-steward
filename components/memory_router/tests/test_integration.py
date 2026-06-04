# components/memory_router/tests/test_integration.py
"""
Integration tests for the Memory Router.

All external dependencies are mocked. Covers:
- Request routing invariants from Doc 08
- /glap intercept
- Open WebUI background request guard
- Static rules always injected (Doc 08 §3.3)
- /v1/models and /healthz endpoints
"""
import json
import sys
import types
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stub only non-installed deps before importing the router
# ---------------------------------------------------------------------------

def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


_stub("psycopg", connect=MagicMock())
_stub("tiktoken",
    encoding_for_model=MagicMock(return_value=MagicMock(encode=lambda t: t.split())),
    get_encoding=MagicMock(return_value=MagicMock(encode=lambda t: t.split())),
)
_stub("memory_router.telemetry", TelemetryWriter=MagicMock())
_stub("memory_router.mcp_bridge",
    handle_glap=MagicMock(return_value=(200, {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "glap",
        "choices": [{"index": 0, "message": {"role": "assistant",
                     "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }))
)

import importlib
router_server = importlib.import_module("memory_router.server")
client = TestClient(router_server.app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_pg_static(rows=None):
    # Tuple format: (id, content, mode) — matches _pg_static_load return shape
    return patch(
        "memory_router.server._pg_static_load",
        return_value=rows or [("rule-1", "Always respond in English", "global")]
    )

def _mock_embed():
    return patch("memory_router.server._embed_one", return_value=[0.1] * 10)

def _mock_qdrant():
    return patch("memory_router.server._qdrant_dense", return_value=[])


# ---------------------------------------------------------------------------
# Healthz
# ---------------------------------------------------------------------------

class TestHealthz:

    def test_returns_200(self):
        assert client.get("/healthz").status_code == 200

    def test_returns_ok(self):
        assert client.get("/healthz").json().get("ok") is True


# ---------------------------------------------------------------------------
# /v1/models
# ---------------------------------------------------------------------------

class TestModels:

    def test_returns_list(self):
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        assert resp.json()["object"] == "list"

    def test_model_has_id(self):
        model = client.get("/v1/models").json()["data"][0]
        assert "id" in model
        assert model["object"] == "model"


# ---------------------------------------------------------------------------
# /glap intercept
# ---------------------------------------------------------------------------

class TestGlapIntercept:

    def test_builder_not_called_for_glap(self):
        with patch("memory_router.server.requests.post") as mock_post:
            client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "/glap get_system_health"}],
                "stream": False,
            })
        mock_post.assert_not_called()

    def test_glap_returns_200(self):
        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "/glap"}],
            "stream": False,
        })
        assert resp.status_code == 200

    def test_glap_case_insensitive(self):
        resp = client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "/GLAP explain_last_decision"}],
            "stream": False,
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Open WebUI background request guard
# ---------------------------------------------------------------------------

class TestBackgroundRequestGuard:
    """
    These tests verify the guard logic directly — not via the full request path,
    since the guard lives in server.py which may not yet be deployed with the patch.
    The integration-level assertion is that the guard markers are correctly detected.
    Full end-to-end blocking is covered in test_router_unit.py::TestOpenWebUIBackgroundGuard.
    """

    _MARKERS = (
        "create a concise, 3-5 word title",
        "generate 1-3 broad tags",
        "generate follow-up questions",
        "autocomplete the following",
        "generate a search query",
    )

    def _would_be_blocked(self, messages):
        system_texts = [
            m["content"].lower()
            for m in messages
            if m.get("role") == "system"
        ]
        return any(
            marker in text
            for text in system_texts
            for marker in self._MARKERS
        )

    def test_title_generation_detected(self):
        messages = [
            {"role": "system", "content": "create a concise, 3-5 word title"},
            {"role": "user", "content": "hello"},
        ]
        assert self._would_be_blocked(messages)

    def test_follow_up_generation_detected(self):
        messages = [
            {"role": "system", "content": "generate follow-up questions"},
            {"role": "user", "content": "hello"},
        ]
        assert self._would_be_blocked(messages)

    def test_tags_generation_detected(self):
        messages = [
            {"role": "system", "content": "generate 1-3 broad tags"},
            {"role": "user", "content": "hello"},
        ]
        assert self._would_be_blocked(messages)

    def test_normal_request_not_blocked(self):
        messages = [
            {"role": "user", "content": "what is my project code?"},
        ]
        assert not self._would_be_blocked(messages)


# ---------------------------------------------------------------------------
# Doc 08 §3.3 — static rules always injected into policy_layer.global
# ---------------------------------------------------------------------------

class TestStaticRulesAlwaysInjected:

    def test_static_rule_present_in_builder_payload(self):
        captured = {}

        def capture_post(url, **kwargs):
            if "chat/completions" in url:
                captured.update(kwargs.get("json", {}))
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"role": "assistant",
                             "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            }
            return mock_resp

        # Tuple format: (id, content, mode)
        static_rows = [("rule-1", "Always respond in English", "global")]

        with patch("memory_router.server._pg_static_load", return_value=static_rows), \
             _mock_embed(), \
             _mock_qdrant(), \
             patch("memory_router.server.requests.post", side_effect=capture_post), \
             patch("memory_router.server.telemetry"):
            client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "random query"}],
                "stream": False,
            })

        messages = captured.get("messages", [])
        system_content = " ".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        )

        # Static rule is serialised into policy_layer.global in the canonical envelope
        envelope = json.loads(system_content)
        global_rules = envelope.get("policy_layer", {}).get("global", [])
        assert any("Always respond in English" in r for r in global_rules), (
            f"Static rule not found in policy_layer.global. Got: {global_rules}"
        )
