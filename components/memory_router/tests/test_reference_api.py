from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

import memory_router.server as router

client = TestClient(router.app)


def _response(payload):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


def test_reference_search_filters_product_and_version():
    qdrant_result = {
        "result": [
            {
                "id": "chunk-1",
                "score": 0.91,
                "vector": {"dense": [0.1, 0.2]},
                "payload": {
                    "memory_type": "reference_memory",
                    "product": "kicad",
                    "version": "10",
                    "scope": "docs",
                    "source": "https://example.test/kicad",
                    "doc_section": "Schematic",
                    "content": "schematic file format",
                },
            }
        ]
    }
    with patch("memory_router.server._embed_one", return_value=[0.3, 0.4]), \
         patch("memory_router.server.requests.post", return_value=_response(qdrant_result)) as post:
        response = client.post(
            "/v1/reference/search",
            headers={"X-Project-ID": "rr"},
            json={
                "query": "schematic file format",
                "reference_filters": {"product": "kicad", "version": "10"},
                "limit": 4,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "rr"
    assert body["items"][0]["id"] == "chunk-1"
    assert body["items"][0]["score"] == 0.91
    assert body["items"][0]["source"] == "https://example.test/kicad"
    assert body["items"][0]["content"] == "schematic file format"

    must = post.call_args.kwargs["json"]["filter"]["must"]
    assert must == [
        {"key": "memory_type", "match": {"value": "reference_memory"}},
        {"key": "product", "match": {"value": "kicad"}},
        {"key": "version", "match": {"value": "10"}},
    ]


def test_reference_search_unknown_filter_returns_422():
    response = client.post(
        "/v1/reference/search",
        json={
            "query": "schematic file format",
            "reference_filters": {"project_id": "rr"},
        },
    )
    assert response.status_code == 422


def test_reference_search_limit_is_bounded():
    assert client.post(
        "/v1/reference/search", json={"query": "x", "limit": 0}
    ).status_code == 422
    assert client.post(
        "/v1/reference/search", json={"query": "x", "limit": 51}
    ).status_code == 422


def test_reference_get_returns_full_reference_chunk():
    qdrant_result = {
        "result": [
            {
                "id": "chunk-1",
                "payload": {
                    "memory_type": "reference_memory",
                    "product": "kicad",
                    "version": "10",
                    "scope": "docs",
                    "source": "https://example.test/kicad",
                    "content": "full reference chunk",
                },
            }
        ]
    }
    with patch("memory_router.server.requests.post", return_value=_response(qdrant_result)) as post:
        response = client.get(
            "/v1/reference/chunk-1",
            headers={"X-Project-ID": "rr"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "rr"
    assert body["id"] == "chunk-1"
    assert body["content"] == "full reference chunk"
    assert body["source"] == "https://example.test/kicad"
    assert post.call_args.kwargs["json"] == {
        "ids": ["chunk-1"],
        "with_payload": True,
        "with_vector": False,
    }


def test_reference_get_missing_returns_404():
    with patch(
        "memory_router.server.requests.post",
        return_value=_response({"result": []}),
    ):
        response = client.get("/v1/reference/missing")
    assert response.status_code == 404


def test_reference_get_hides_non_reference_points():
    qdrant_result = {
        "result": [
            {
                "id": "dynamic-1",
                "payload": {
                    "memory_type": "dynamic_memory",
                    "content": "must not leak",
                },
            }
        ]
    }
    with patch(
        "memory_router.server.requests.post",
        return_value=_response(qdrant_result),
    ):
        response = client.get("/v1/reference/dynamic-1")
    assert response.status_code == 404
