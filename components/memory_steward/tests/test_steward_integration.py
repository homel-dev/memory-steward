# components/memory_steward/tests/test_steward_integration.py
"""
Integration tests for the Memory Steward admission pipeline.

Doc 08 invariants tested:
  3.2 Async admission — no fragments is not an error
  Admission endpoint contract — required fields, response shape
"""
import sys
import types
import pytest
import importlib
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


_stub("psycopg", connect=MagicMock())
_stub("memory_steward.telemetry", StewardTelemetryWriter=MagicMock())

steward_server = importlib.import_module("memory_steward.server")
client = TestClient(steward_server.app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_extract(fragments):
    return patch("memory_steward.server._extract", return_value=fragments)

def _mock_embed(vectors=None):
    return patch("memory_steward.server._embed",
                 return_value=vectors or [[0.1] * 10])

def _mock_pg():
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.__enter__ = MagicMock(return_value=mock_cur)
    mock_cur.__exit__ = MagicMock(return_value=False)
    mock_cur.rowcount = 1
    mock_conn.__enter__ = MagicMock(return_value=mock_conn)
    mock_conn.__exit__ = MagicMock(return_value=False)
    mock_conn.cursor = MagicMock(return_value=mock_cur)
    return patch("memory_steward.server._pg", return_value=mock_conn)

def _mock_qdrant_put():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.raise_for_status = MagicMock()
    return patch("memory_steward.server.requests.put", return_value=mock_resp)


# ---------------------------------------------------------------------------
# Healthz
# ---------------------------------------------------------------------------

class TestHealthz:

    def test_returns_200(self):
        assert client.get("/healthz").status_code == 200

    def test_returns_ok(self):
        assert client.get("/healthz").json().get("ok") is True


# ---------------------------------------------------------------------------
# Admission pipeline
# ---------------------------------------------------------------------------

class TestAdmission:

    def test_admission_happy_path(self):
        with _mock_extract(["Project code is 994"]), \
             _mock_embed(), \
             _mock_pg(), \
             _mock_qdrant_put():
            resp = client.post("/admit", json={
                "request_id": "req-001",
                "project_id": "test-project",
                "messages": [{"role": "user", "content": "My project code is 994"}],
            })
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_no_fragments_is_not_an_error(self):
        """Doc 08 §3.2: steward returning nothing must not be an error."""
        with _mock_extract([]), _mock_pg():
            resp = client.post("/admit", json={
                "request_id": "req-002",
                "project_id": "test-project",
                "messages": [{"role": "user", "content": "hello there"}],
            })
        assert resp.status_code == 200
        assert resp.json()["inserted"] == 0

    def test_requires_request_id(self):
        resp = client.post("/admit", json={
            "project_id": "test-project",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert resp.status_code == 422

    def test_requires_project_id(self):
        resp = client.post("/admit", json={
            "request_id": "req-003",
            "messages": [{"role": "user", "content": "hello"}],
        })
        assert resp.status_code == 422

    def test_inserted_count_reflects_new_rows(self):
        with _mock_extract(["fact one", "fact two"]), \
             _mock_embed([[0.1]*10, [0.2]*10]), \
             _mock_pg(), \
             _mock_qdrant_put():
            resp = client.post("/admit", json={
                "request_id": "req-004",
                "project_id": "test-project",
                "messages": [{"role": "user", "content": "two facts here"}],
            })
        assert resp.status_code == 200
        # rowcount=1 per insert, 2 fragments → inserted=2
        assert resp.json()["inserted"] == 2
