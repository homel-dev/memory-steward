from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from memory_router import server


client = TestClient(server.app)


def test_builder_payload_uses_pruned_history():
    """A message rejected by the global history budget must not reach Builder."""
    captured: dict = {}

    response = MagicMock()
    response.ok = True
    response.status_code = 200
    response.json.return_value = {
        "choices": [
            {
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }

    def post(url, **kwargs):
        if url.endswith("/chat/completions"):
            captured.update(kwargs["json"])
        return response

    empty_retrieval = {
        "policy_layer": {"global": [], "mode_conditioned": []},
        "system_ontology": {},
        "retrieval_context": {},
        "agent_reference": [],
        "selected_items": [],
        "accounting": {
            "dense_candidates": 0,
            "selected_topk": 0,
            "context_tokens_est": 0,
            "static_tokens_est": 0,
            "dynamic_tokens_est": 0,
            "dropped_budget": 0,
            "dropped_no_content": 0,
        },
    }

    def count_tokens(_model, text):
        return 999_999 if text == "OLD-HISTORY" else 1

    with patch("memory_router.server._count_tokens", side_effect=count_tokens), \
         patch("memory_router.server._retrieve_context_structured", return_value=empty_retrieval), \
         patch("memory_router.server._render_context_envelope", return_value="{}"), \
         patch("memory_router.server.requests.post", side_effect=post), \
         patch("memory_router.server._async_admit"), \
         patch("memory_router.server.telemetry"):
        result = client.post(
            "/v1/chat/completions",
            json={
                "messages": [
                    {"role": "user", "content": "OLD-HISTORY"},
                    {"role": "user", "content": "CURRENT"},
                ],
                "stream": False,
            },
        )

    assert result.status_code == 200
    sent = captured["messages"]
    assert all(message.get("content") != "OLD-HISTORY" for message in sent)
    assert any(message.get("content") == "CURRENT" for message in sent)
