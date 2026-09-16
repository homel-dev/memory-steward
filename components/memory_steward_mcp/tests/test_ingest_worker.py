from memory_steward_mcp import ingest_worker as worker


def test_process_job_updates_progress_and_finishes_with_provenance(monkeypatch) -> None:
    progress_updates = []
    finished = []

    monkeypatch.setattr(worker, "_fetch_url", lambda _url: "manual")
    monkeypatch.setattr(worker.stop_event, "is_set", lambda: False)
    monkeypatch.setattr(worker, "cancel_requested", lambda **_kwargs: False)

    def fake_update_progress(**kwargs):
        progress_updates.append(kwargs)
        return True

    def fake_ingest(_qdrant, **kwargs):
        assert kwargs["record_provenance"] is False
        kwargs["progress_fn"](5, 0, 0)
        kwargs["progress_fn"](5, 5, 5)
        return {"chunk_count": 5, "processed_chunks": 5, "upserted_count": 5}

    def fake_finish(**kwargs):
        finished.append(kwargs)
        return True

    monkeypatch.setattr(worker, "update_progress", fake_update_progress)
    monkeypatch.setattr(worker, "_ingest_reference_content", fake_ingest)
    monkeypatch.setattr(worker, "finish_success_with_provenance", fake_finish)

    worker._process_job(
        object(),
        {
            "id": "00000000-0000-0000-0000-000000000123",
            "attempt_count": 3,
            "product": "kicad",
            "version": "10.0",
            "scope": "reference",
            "url": "https://docs.example.test/kicad.html",
        },
    )

    assert [item["processed_chunks"] for item in progress_updates] == [0, 5]
    assert all(item["worker_id"] == worker.WORKER_ID for item in progress_updates)
    assert all(item["attempt_count"] == 3 for item in progress_updates)
    assert finished[0]["attempt_count"] == 3
    assert finished[0]["source_url"] == "https://docs.example.test/kicad.html"
    assert finished[0]["upserted_count"] == 5
