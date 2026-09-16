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
