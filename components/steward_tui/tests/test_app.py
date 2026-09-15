# components/steward_tui/tests/test_app.py
"""Headless UI tests for keyboard focus, dynamic forms, and invocation."""
import pytest
from textual.widgets import Input, ListView

from steward_tui import mcp_client as mc
from steward_tui.app import StewardTUI

FAKE = [
    mc.ToolSpec(
        name="ref_ingest_url",
        description="Fetch a URL and ingest it as reference memory.",
        fields=[
            mc.ToolField("url", "string", required=True, description="source url"),
            mc.ToolField("product", "string", required=True),
            mc.ToolField("version", "string", required=True),
            mc.ToolField("scope", "string", required=False, default="general"),
        ],
    ),
    mc.ToolSpec(name="ref_list", description="List reference products.", fields=[]),
    mc.ToolSpec(name="static_list", description="List static rules.", fields=[]),
]


async def _select_ref_ingest(app: StewardTUI, pilot) -> None:
    lv = app.query_one("#tools", ListView)
    lv.focus()
    lv.index = 1
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_select_focuses_first_required_field_and_tab_moves(monkeypatch):
    async def fake_fetch(url=None):
        return FAKE

    monkeypatch.setattr(mc, "fetch_tools", fake_fetch)

    app = StewardTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select_ref_ingest(app, pilot)

        assert app.current is not None and app.current.name == "ref_ingest_url"
        assert list(app.inputs) == ["url", "product", "version", "scope"]
        assert app.screen.focused is app.inputs["url"]

        await pilot.press("tab")
        assert app.screen.focused is app.inputs["product"]
        await pilot.press("tab")
        assert app.screen.focused is app.inputs["version"]


@pytest.mark.asyncio
async def test_invalid_required_field_gets_focus_and_error_class(monkeypatch):
    async def fake_fetch(url=None):
        return FAKE

    monkeypatch.setattr(mc, "fetch_tools", fake_fetch)

    app = StewardTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select_ref_ingest(app, pilot)

        app.inputs["url"].value = "https://example.com/doc"
        app.inputs["product"].value = "acme"
        await pilot.press("ctrl+enter")
        await pilot.pause()

        version = app.inputs["version"]
        assert isinstance(version, Input)
        assert app.screen.focused is version
        assert version.has_class("input-error")


@pytest.mark.asyncio
async def test_app_invokes_with_all_required_fields(monkeypatch):
    captured = {}

    async def fake_fetch(url=None):
        return FAKE

    async def fake_invoke(name, arguments, url=None):
        captured["name"] = name
        captured["arguments"] = arguments
        return "OK: ingested 3 chunks"

    monkeypatch.setattr(mc, "fetch_tools", fake_fetch)
    monkeypatch.setattr(mc, "invoke_tool", fake_invoke)

    app = StewardTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select_ref_ingest(app, pilot)

        app.inputs["url"].value = "https://example.com/doc"
        app.inputs["product"].value = "acme"
        app.inputs["version"].value = "9.0"
        await pilot.press("ctrl+enter")
        await pilot.pause()

        assert captured["name"] == "ref_ingest_url"
        assert captured["arguments"] == {
            "url": "https://example.com/doc",
            "product": "acme",
            "version": "9.0",
        }


@pytest.mark.asyncio
async def test_escape_returns_focus_to_tool_list(monkeypatch):
    async def fake_fetch(url=None):
        return FAKE

    monkeypatch.setattr(mc, "fetch_tools", fake_fetch)

    app = StewardTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _select_ref_ingest(app, pilot)
        await pilot.press("escape")
        assert app.screen.focused is app.query_one("#tools", ListView)
