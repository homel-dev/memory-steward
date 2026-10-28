from memory_steward_mcp import git_plane as gp


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_github_fetch_file_uses_raw_media_type_and_returns_bytes(monkeypatch) -> None:
    captured = {}

    def fake_get(url, *, headers, params, timeout):
        captured.update(url=url, headers=headers, params=params, timeout=timeout)
        return _Response(b"%PDF-1.7\npayload")

    monkeypatch.setattr(gp.requests, "get", fake_get)
    adapter = gp._GitHubAdapter(
        {
            "base_url": "https://api.github.com",
            "token": "test-token",
        }
    )

    raw = adapter.fetch_file("homel-dev/books", "books/os.pdf", "main")

    assert raw == b"%PDF-1.7\npayload"
    assert captured["headers"]["Accept"] == "application/vnd.github.raw+json"
    assert captured["params"] == {"ref": "main"}


class _FakeMCP:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, name=None):
        def decorator(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return decorator


class _Adapter:
    def list_files(self, project: str, path: str, ref: str):
        assert project == "homel-dev/books"
        assert path == "books"
        assert ref == "main"
        return [
            {"name": "os.pdf", "path": "books/os.pdf", "type": "blob"},
            {"name": "README.md", "path": "books/README.md", "type": "blob"},
        ]

    def fetch_file(self, project: str, file_path: str, ref: str) -> bytes:
        assert project == "homel-dev/books"
        assert file_path == "books/os.pdf"
        assert ref == "main"
        return b"%PDF-1.7\npayload"

    def file_url(self, project: str, file_path: str, ref: str) -> str:
        return f"https://github.com/{project}/blob/{ref}/{file_path}"


def test_git_ingest_repo_passes_pdf_bytes_to_shared_document_ingest(monkeypatch) -> None:
    mcp = _FakeMCP()
    captured = {}
    adapter = _Adapter()

    monkeypatch.setattr(
        gp,
        "_get_connection",
        lambda _name: {"provider": "github", "base_url": "https://api.github.com"},
    )
    monkeypatch.setattr(gp, "_adapter", lambda _conn: adapter)
    monkeypatch.setattr(gp.time, "sleep", lambda _seconds: None)

    def ingest_document_fn(**kwargs):
        captured.update(kwargs)
        return "✅ Ingested **2 chunks** for `os-book@9`."

    gp.register_git_tools(mcp, ingest_document_fn=ingest_document_fn)
    result = mcp.tools["git_ingest_repo"](
        connection="github-public",
        project="homel-dev/books",
        product="os-book",
        version="9",
        scope="reference",
        path="books",
        ref="main",
        file_extension=".pdf",
    )

    assert captured["raw"] == b"%PDF-1.7\npayload"
    assert captured["filename"] == "books/os.pdf"
    assert captured["source_url"].endswith("/homel-dev/books/blob/main/books/os.pdf")
    assert "Files: 1  chunks: 2  errors: 0" in result


def test_git_ingest_repo_surfaces_document_normalization_failure(monkeypatch) -> None:
    mcp = _FakeMCP()
    adapter = _Adapter()
    monkeypatch.setattr(
        gp,
        "_get_connection",
        lambda _name: {"provider": "github", "base_url": "https://api.github.com"},
    )
    monkeypatch.setattr(gp, "_adapter", lambda _conn: adapter)
    monkeypatch.setattr(gp.time, "sleep", lambda _seconds: None)

    gp.register_git_tools(
        mcp,
        ingest_document_fn=lambda **_kwargs: "Reference ingestion failed: PDF contains no extractable text layer",
    )
    result = mcp.tools["git_ingest_repo"](
        connection="github-public",
        project="homel-dev/books",
        product="os-book",
        version="9",
        path="books",
        file_extension=".pdf",
    )

    assert "errors: 1" in result
    assert "PDF contains no extractable text layer" in result
