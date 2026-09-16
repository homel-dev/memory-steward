import pytest

from memory_steward_mcp import content_plane as cp


class _Response:
    def __init__(self, text: str, content_type: str) -> None:
        self.text = text
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        return None


def test_extract_html_document_removes_chrome_and_preserves_headings() -> None:
    html = """
    <html>
      <body>
        <nav>site navigation</nav>
        <div id="content">
          <div id="toc" class="toc2">Table of Contents</div>
          <script>window.bad = "must not be indexed";</script>
          <style>.bad { color: hotpink; }</style>
          <h1>KiCad 10.0 Reference Manual</h1>
          <h2>Introduction</h2>
          <p>KiCad creates <strong>schematics</strong> and PCBs.</p>
          <h3>System Requirements</h3>
          <p>A dedicated graphics card is recommended.</p>
          <pre>kicad-cli version</pre>
        </div>
        <footer>site footer</footer>
      </body>
    </html>
    """

    text = cp._extract_html_document(html)

    assert "# KiCad 10.0 Reference Manual" in text
    assert "## Introduction" in text
    assert "### System Requirements" in text
    assert "KiCad creates schematics and PCBs." in text
    assert "kicad-cli version" in text
    assert "Table of Contents" not in text
    assert "window.bad" not in text
    assert "hotpink" not in text
    assert "site navigation" not in text
    assert "site footer" not in text


def test_fetch_url_detects_html_and_normalizes_it(monkeypatch) -> None:
    html = """
    <html><body><main>
      <h2>Installing KiCad</h2>
      <p>Install the package for your platform.</p>
    </main></body></html>
    """

    monkeypatch.setattr(
        cp.requests,
        "get",
        lambda *args, **kwargs: _Response(html, "text/html; charset=utf-8"),
    )

    text = cp._fetch_url("https://docs.example.test/manual.html")

    assert text == "## Installing KiCad\n\nInstall the package for your platform."


def test_chunk_markdown_preserves_markdown_hierarchy() -> None:
    chunks = cp._chunk_markdown(
        """
## Introduction
Overview.

### System Requirements
Requirements text.

## Installing and Upgrading KiCad
Installation text.
""".strip()
    )

    assert [chunk["section"] for chunk in chunks] == [
        "Introduction",
        "Introduction > System Requirements",
        "Installing and Upgrading KiCad",
    ]


def test_chunk_markdown_supports_asciidoc_headings() -> None:
    chunks = cp._chunk_markdown(
        """
= KiCad Reference Manual

== Introduction
Overview.

=== System Requirements
Requirements text.
""".strip()
    )

    assert [chunk["section"] for chunk in chunks] == [
        "General",
        "Introduction",
        "Introduction > System Requirements",
    ]
    assert chunks[0]["content"] == "= KiCad Reference Manual"


class _Qdrant:
    def __init__(self) -> None:
        self.calls = []

    def upsert(self, *, collection_name, points, wait):
        self.calls.append((collection_name, list(points), wait))


def test_reference_ingestion_embeds_and_upserts_in_bounded_batches(monkeypatch) -> None:
    qdrant = _Qdrant()
    embed_calls = []
    provenance = []

    monkeypatch.setattr(cp, "REFERENCE_EMBED_BATCH_SIZE", 2)
    monkeypatch.setattr(
        cp,
        "_chunk_markdown",
        lambda _text: [
            {"section": f"S{i}", "content": f"chunk-{i}"}
            for i in range(5)
        ],
    )

    def fake_embed(texts):
        embed_calls.append(list(texts))
        return [[float(index)] for index, _ in enumerate(texts)]

    monkeypatch.setattr(cp, "_embed", fake_embed)
    monkeypatch.setattr(cp, "_record_provenance", lambda *args: provenance.append(args))

    stats = cp._ingest_reference_content(
        qdrant,
        text="ignored",
        product="kicad",
        version="10.0",
        scope="reference",
        source_url="https://docs.example.test/kicad.html",
    )

    assert embed_calls == [
        ["chunk-0", "chunk-1"],
        ["chunk-2", "chunk-3"],
        ["chunk-4"],
    ]
    assert [len(call[1]) for call in qdrant.calls] == [2, 2, 1]
    assert all(call[2] is True for call in qdrant.calls)
    assert stats == {"chunk_count": 5, "processed_chunks": 5, "upserted_count": 5}
    assert len(provenance) == 1


def test_reference_ingestion_checks_cancel_between_batches(monkeypatch) -> None:
    qdrant = _Qdrant()
    checks = iter([False, True])

    monkeypatch.setattr(cp, "REFERENCE_EMBED_BATCH_SIZE", 2)
    monkeypatch.setattr(
        cp,
        "_chunk_markdown",
        lambda _text: [
            {"section": f"S{i}", "content": f"chunk-{i}"}
            for i in range(4)
        ],
    )
    monkeypatch.setattr(cp, "_embed", lambda texts: [[1.0] for _ in texts])
    monkeypatch.setattr(cp, "_record_provenance", lambda *args: None)

    try:
        cp._ingest_reference_content(
            qdrant,
            text="ignored",
            product="kicad",
            version="10.0",
            scope="reference",
            source_url="manual",
            cancel_fn=lambda: next(checks),
        )
    except cp.IngestionCancelled:
        pass
    else:
        raise AssertionError("expected IngestionCancelled")

    assert len(qdrant.calls) == 1
    assert len(qdrant.calls[0][1]) == 2


class _FakeMCP:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, name=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


def test_ref_ingest_url_queues_without_fetching_in_mcp_request(monkeypatch) -> None:
    mcp = _FakeMCP()
    qdrant = _Qdrant()
    captured = {}

    def fake_enqueue(**kwargs):
        captured.update(kwargs)
        return "00000000-0000-0000-0000-000000000123"

    monkeypatch.setattr(cp, "enqueue_url_job", fake_enqueue)
    monkeypatch.setattr(
        cp,
        "_fetch_url",
        lambda _url: (_ for _ in ()).throw(AssertionError("MCP request must not fetch")),
    )

    cp.register_content_tools(mcp, qdrant)
    result = mcp.tools["ref_ingest_url"](
        url="https://docs.example.test/kicad.html",
        product="kicad",
        version="10.0",
        scope="reference",
    )

    assert "00000000-0000-0000-0000-000000000123" in result
    assert captured == {
        "url": "https://docs.example.test/kicad.html",
        "product": "kicad",
        "version": "10.0",
        "scope": "reference",
    }


class _StreamingResponse:
    def __init__(self, blocks):
        self.blocks = blocks
        self.headers = {"content-type": "text/plain"}
        self.encoding = "utf-8"
        self.closed = False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size):
        assert chunk_size == 64 * 1024
        yield from self.blocks

    def close(self) -> None:
        self.closed = True


def test_fetch_url_enforces_decompressed_size_limit(monkeypatch) -> None:
    response = _StreamingResponse([b"1234", b"5678"])
    monkeypatch.setattr(cp, "REFERENCE_FETCH_MAX_BYTES", 6)
    monkeypatch.setattr(cp.requests, "get", lambda *args, **kwargs: response)

    with pytest.raises(ValueError, match="exceeds 6 bytes"):
        cp._fetch_url("https://docs.example.test/large.txt")

    assert response.closed is True
