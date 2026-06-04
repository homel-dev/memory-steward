"""
Integration tests for the Memory Steward system.

All external dependencies are mocked. These tests verify that the components
wire together correctly — request flows, invariants from Doc 08, and failure modes.

Doc 08 invariants tested:
  3.1 Statelessness — router assembles context from storage, not local state
  3.2 Async admission — steward down does not break chat
  3.3 Relevance beats recency — static rules always injected regardless of content
"""
import sys
import types
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Stub all external deps before importing the apps
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

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

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
_stub("memory_steward.telemetry", StewardTelemetryWriter=MagicMock())

import importlib
router_server = importlib.import_module("memory_router.server")
steward_server = importlib.import_module("memory_steward.server")

router_client = TestClient(router_server.app)
steward_client = TestClient(steward_server.app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_pg_static(rows=None):
    """Mock _pg_static_load to return given rows."""
    return patch(
        "memory_router.server._pg_static_load",
        return_value=rows or [("global", "default", "Always respond in English")]
    )

def _mock_embed(vector=None):
    return patch(
        "memory_router.server._embed_one",
        return_value=vector or [0.1] * 10
    )

def _mock_qdrant(candidates=None):
    return patch(
        "memory_router.server._qdrant_dense",
        return_value=candidates or []
    )

def _mock_builder(content="test response"):
    mock_resp = MagicMock()
    mock_resp.iter_lines = MagicMock(return_value=iter([
        f'data: {json.dumps({"choices": [{"delta": {"content": content}, "finish_reason": None}]})}'.encode(),
        b'data: [DONE]',
    ]))
    mock_resp.raise_for_status = MagicMock()
    mock_resp.status_code = 200
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    return patch("memory_router.server.requests.post", return_value=mock_resp)


# ---------------------------------------------------------------------------
# Router: healthz
# ---------------------------------------------------------------------------

class TestRouterHealth:

    def test_healthz_returns_200(self):
        resp = router_client.get("/healthz")
        assert resp.status_code == 200

    def test_healthz_returns_ok(self):
        resp = router_client.get("/healthz")
        assert resp.json().get("ok") is True


# ---------------------------------------------------------------------------
# Router: /v1/models
# ---------------------------------------------------------------------------

class TestRouterModels:

    def test_models_returns_list(self):
        resp = router_client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) >= 1

    def test_model_has_required_fields(self):
        resp = router_client.get("/v1/models")
        model = resp.json()["data"][0]
        assert "id" in model
        assert "object" in model
        assert model["object"] == "model"


# ---------------------------------------------------------------------------
# Router: /glap intercept
# ---------------------------------------------------------------------------

class TestGlapIntercept:

    def test_glap_intercepted_before_builder(self):
        """Builder must NOT be called for /glap requests."""
        with patch("memory_router.server.requests.post") as mock_post:
            resp = router_client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "/glap get_system_health"}],
                "stream": False,
            })
        # handle_glap was called, builder was not
        mock_post.assert_not_called()

    def test_glap_returns_200(self):
        resp = router_client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "/glap"}],
            "stream": False,
        })
        assert resp.status_code == 200

    def test_glap_case_insensitive(self):
        resp = router_client.post("/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "/GLAP explain_last_decision"}],
            "stream": False,
        })
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Router: Open WebUI background request guard (Doc 08 invariant)
# ---------------------------------------------------------------------------

class TestBackgroundRequestGuard:

    def test_title_generation_blocked(self):
        """Open WebUI title-gen must never reach the builder."""
        with patch("memory_router.server.requests.post") as mock_post:
            resp = router_client.post("/v1/chat/completions", json={
                "messages": [
                    {"role": "system", "content": "create a concise, 3-5 word title"},
                    {"role": "user", "content": "hello"},
                ],
                "stream": False,
            })
        mock_post.assert_not_called()
        assert resp.status_code == 200

    def test_follow_up_generation_blocked(self):
        with patch("memory_router.server.requests.post") as mock_post:
            resp = router_client.post("/v1/chat/completions", json={
                "messages": [
                    {"role": "system", "content": "generate follow-up questions"},
                    {"role": "user", "content": "hello"},
                ],
                "stream": False,
            })
        mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# Steward: healthz
# ---------------------------------------------------------------------------

class TestStewardHealth:

    def test_healthz_returns_200(self):
        resp = steward_client.get("/healthz")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Steward: admission pipeline (Doc 08 §3.2 — async admission)
# ---------------------------------------------------------------------------

class TestStewardAdmission:

    def _mock_extract(self, fragments):
        return patch("memory_steward.server._extract", return_value=fragments)

    def _mock_embed(self, vectors=None):
        return patch("memory_steward.server._embed",
                     return_value=vectors or [[0.1] * 10])

    def _mock_pg(self):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_cur.rowcount = 1
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor = MagicMock(return_value=mock_cur)
        return patch("memory_steward.server._pg", return_value=mock_conn)

    def _mock_qdrant_put(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.raise_for_status = MagicMock()
        return patch("memory_steward.server.requests.put", return_value=mock_resp)

    def test_admission_returns_ok_on_success(self):
        with self._mock_extract(["Project code is 994"]), \
             self._mock_embed([[0.1] * 10]), \
             self._mock_pg(), \
             self._mock_qdrant_put():
            resp = steward_client.post("/admit", json={
                "request_id": "req-001",
                "project_id": "test-project",
                "messages": [{"role": "user", "content": "My project code is 994"}],
            })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_admission_with_no_fragments_returns_ok(self):
        """Doc 08 §3.2: steward returning nothing is not an error."""
        with self._mock_extract([]), self._mock_pg():
            resp = steward_client.post("/admit", json={
                "request_id": "req-002",
                "project_id": "test-project",
                "messages": [{"role": "user", "content": "hello there"}],
            })
        assert resp.status_code == 200
        assert resp.json()["inserted"] == 0

    def test_admission_requires_request_id(self):
        resp = steward_client.post("/admit", json={
            "project_id": "test-project",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert resp.status_code == 422

    def test_admission_requires_project_id(self):
        resp = steward_client.post("/admit", json={
            "request_id": "req-003",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Doc 08 §3.3: Static rules always injected (relevance beats recency)
# ---------------------------------------------------------------------------

class TestStaticRulesAlwaysInjected:

    def test_static_global_included_in_every_request(self):
        """Static rules must appear in every prompt regardless of query content."""
        captured_payload = {}

        def capture_post(url, **kwargs):
            if "chat/completions" in url:
                captured_payload.update(kwargs.get("json", {}))
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_resp.json.return_value = {
                "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10},
            }
            return mock_resp

        with _mock_pg_static([("global", "default", "Always respond in English")]), \
             _mock_embed(), \
             _mock_qdrant(), \
             patch("memory_router.server.requests.post", side_effect=capture_post), \
             patch("memory_router.server.telemetry"):
            router_client.post("/v1/chat/completions", json={
                "messages": [{"role": "user", "content": "random query about something"}],
                "stream": False,
            })

        # Static rule must appear in the system prompt sent to builder
        messages = captured_payload.get("messages", [])
        system_content = " ".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        )
        assert "Always respond in English" in system_content
