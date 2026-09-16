from fastapi.testclient import TestClient

from embeddings import server


class _Vec:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return self._values


class _Slot:
    def __init__(self):
        self.entries = 0

    def __enter__(self):
        self.entries += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Embedder:
    def __init__(self):
        self.calls = []

    def embed(self, texts, *, batch_size, parallel):
        self.calls.append((list(texts), batch_size, parallel))
        return [_Vec([1.0, 2.0]) for _ in texts]


def test_embed_uses_bounded_batch_and_disables_parallel(monkeypatch):
    fake = _Embedder()
    slot = _Slot()
    monkeypatch.setattr(server, "embedder", fake)
    monkeypatch.setattr(server, "_embed_slots", slot)
    monkeypatch.setattr(server, "EMBEDDING_BATCH_SIZE", 2)
    monkeypatch.setattr(server, "EMBEDDING_MAX_TEXTS", 8)

    response = TestClient(server.app).post("/embed", json={"texts": ["a", "b", "c"]})

    assert response.status_code == 200
    assert fake.calls == [(["a", "b", "c"], 2, None)]
    assert slot.entries == 1
    assert len(response.json()["vectors"]) == 3


def test_embed_rejects_oversized_request(monkeypatch):
    monkeypatch.setattr(server, "EMBEDDING_MAX_TEXTS", 2)

    response = TestClient(server.app).post("/embed", json={"texts": ["a", "b", "c"]})

    assert response.status_code == 413
    assert "maximum per request is 2" in response.json()["detail"]
