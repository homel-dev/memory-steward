# components/steward_tui/src/steward_tui/app.py
"""Terminal Glass Pane: a Textual client for the Memory Steward MCP server.

Left pane lists every tool the server advertises, grouped by plane. Selecting a
tool renders a form built live from its JSON-Schema; Invoke calls it over MCP and
streams the result into the log. This is the operator-plane client Doc 07
(Glass Pane) posits, kept off the end-user OpenWebUI surface on purpose.
"""
from __future__ import annotations

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
    Switch,
)

from steward_tui import mcp_client as mc
from steward_tui.config import mcp_url


class StewardTUI(App):
    CSS = """
    #tools { width: 36; border-right: solid $primary; }
    #detail { padding: 0 1; }
    #title { padding: 1 0 0 0; }
    #desc { color: $text-muted; }
    #form { height: 1fr; border: round $panel; padding: 0 1; margin: 1 0; }
    #result { height: 14; border: round $panel; }
    .req { color: $error; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh tools"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.specs: list[mc.ToolSpec] = []
        self.current: mc.ToolSpec | None = None
        self.inputs: dict[str, Input | Switch] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield ListView(id="tools")
            with Vertical(id="detail"):
                yield Static("Select a tool", id="title")
                yield Static("", id="desc")
                yield VerticalScroll(id="form")
                yield Button("Invoke", id="invoke", variant="primary", disabled=True)
                yield RichLog(id="result", wrap=True, markup=False, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Memory Steward — Glass Pane TUI"
        self.sub_title = mcp_url()
        self.refresh_tools()

    # ---- tool discovery -----------------------------------------------------
    @work(exclusive=True)
    async def refresh_tools(self) -> None:
        lv = self.query_one("#tools", ListView)
        log = self.query_one("#result", RichLog)
        await lv.clear()
        try:
            self.specs = await mc.fetch_tools()
        except Exception as e:  # unreachable server, bad URL, protocol mismatch
            log.write(
                f"Cannot reach MCP at {mcp_url()}\n{type(e).__name__}: {e}\n\n"
                "Hint: kubectl port-forward svc/memory-steward-mcp 8081:8081"
            )
            return
        last_plane: str | None = None
        for s in self.specs:
            if s.plane != last_plane:
                header = ListItem(Label(f"— {s.plane} —"))
                header.disabled = True
                lv.append(header)
                last_plane = s.plane
            item = ListItem(Label(s.name))
            item.tool_name = s.name  # type: ignore[attr-defined]
            lv.append(item)
        log.write(f"Loaded {len(self.specs)} tools from {mcp_url()}")

    def action_refresh(self) -> None:
        self.refresh_tools()

    # ---- selection + dynamic form ------------------------------------------
    @on(ListView.Selected, "#tools")
    def _select(self, event: ListView.Selected) -> None:
        name = getattr(event.item, "tool_name", None)
        if not name:
            return
        self.current = next((s for s in self.specs if s.name == name), None)
        if self.current:
            self._render_form(self.current)

    def _render_form(self, spec: mc.ToolSpec) -> None:
        self.query_one("#title", Static).update(spec.name)
        self.query_one("#desc", Static).update(spec.description or "(no description)")
        form = self.query_one("#form", VerticalScroll)
        form.remove_children()
        self.inputs = {}
        widgets: list = []
        for fld in spec.fields:
            star = " [b $error]*[/]" if fld.required else ""
            widgets.append(Label(f"{fld.name}{star}  [dim]{fld.type}[/dim]"))
            if fld.description:
                widgets.append(Static(f"[dim]{fld.description}[/dim]"))
            if fld.type == "boolean":
                w: Input | Switch = Switch(value=bool(fld.default))
            else:
                placeholder = "" if fld.default is None else str(fld.default)
                w = Input(placeholder=placeholder)
            self.inputs[fld.name] = w
            widgets.append(w)
        if widgets:
            form.mount_all(widgets)
        self.query_one("#invoke", Button).disabled = False

    # ---- invocation ---------------------------------------------------------
    @on(Button.Pressed, "#invoke")
    def _invoke_pressed(self) -> None:
        self.do_invoke()

    @work(exclusive=True)
    async def do_invoke(self) -> None:
        if not self.current:
            return
        log = self.query_one("#result", RichLog)
        args: dict = {}
        try:
            for fld in self.current.fields:
                widget = self.inputs[fld.name]
                if fld.type == "boolean":
                    args[fld.name] = bool(widget.value)  # type: ignore[union-attr]
                else:
                    val = mc.coerce(fld, widget.value)  # type: ignore[union-attr]
                    if val is not None:
                        args[fld.name] = val
        except ValueError as e:
            log.write(f"Bad input: {e}")
            return
        log.write(f"\n> {self.current.name}({args})")
        try:
            out = await mc.invoke_tool(self.current.name, args)
        except Exception as e:
            log.write(f"{type(e).__name__}: {e}")
            return
        log.write(out)
