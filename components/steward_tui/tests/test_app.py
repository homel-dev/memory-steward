# components/steward_tui/tests/test_app.py
"""Headless UI test via Textual's Pilot. The MCP layer is monkeypatched so no
network is touched — we only verify wiring: tools populate, selecting a tool
renders its form, and Invoke marshals typed args and shows the result.
"""
import pytest
from textual.widgets import ListView

from steward_tui import mcp_client as mc
from steward_tui.app import StewardTUI

FAKE = [
    mc.ToolSpec(
        name="ref_ingest_url",
        description="Fetch a URL and ingest it as reference memory.",
        fields=[
            mc.ToolField("url", "string", required=True, description="source url"),
            mc.ToolField("product", "string", required=True),
            mc.ToolField("version", "string", required=False, default="latest"),
        ],
    ),
    mc.ToolSpec(name="ref_list", description="List reference products.", fields=[]),
    mc.ToolSpec(name="static_list", description="List static rules.", fields=[]),
]


@pytest.mark.asyncio
async def test_app_lists_tools_and_invokes(monkeypatch):
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
        # tools loaded: 3 real tools + 2 plane headers (ref, static)
        assert len(app.specs) == 3

        # select the first real tool (ref_ingest_url); index 0 is the "ref" header.
        # Drive it like a user: focus the list, move the cursor, press enter.
        lv = app.query_one("#tools", ListView)
        lv.focus()
        lv.index = 1
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.current is not None and app.current.name == "ref_ingest_url"

        # fill the two required fields
        app.inputs["url"].value = "https://example.com/doc"
        app.inputs["product"].value = "acme"
        await pilot.pause()

        app.query_one("#invoke").press()
        await pilot.pause()

        assert captured["name"] == "ref_ingest_url"
        # optional empty 'version' omitted; required fields present
        assert captured["arguments"] == {
            "url": "https://example.com/doc",
            "product": "acme",
        }
