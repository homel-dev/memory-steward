# components/steward_tui/src/steward_tui/app.py
"""Terminal Glass Pane: a Textual client for the Memory Steward MCP server.

The TUI discovers the live MCP tool schema, renders an operator-friendly form,
and keeps keyboard focus explicit so a selected tool can be filled immediately.
"""
from __future__ import annotations

import json

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
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

# K9s-style dark palette, intentionally excluding magenta/pink/purple.
K9S_DARK = Theme(
    name="k9s-dark",
    primary="#00A8CC",
    secondary="#4EA1D3",
    accent="#5FD7FF",
    foreground="#D7E3EA",
    background="#0B0F14",
    surface="#111820",
    panel="#18242E",
    success="#5FD75F",
    warning="#FFD75F",
    error="#FF5F5F",
    dark=True,
    variables={
        "border": "#355061",
        "border-blurred": "#233542",
        "block-cursor-foreground": "#071015",
        "block-cursor-background": "#5FD7FF",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-foreground": "#D7E3EA",
        "block-cursor-blurred-background": "#1C2A35",
        "block-cursor-blurred-text-style": "none",
        "block-hover-background": "#16232D",
        "input-cursor-background": "#5FD7FF",
        "input-cursor-foreground": "#071015",
        "input-selection-background": "#2F80A060",
        "scrollbar": "#355061",
        "scrollbar-hover": "#4EA1D3",
        "scrollbar-active": "#5FD7FF",
        "scrollbar-background": "#0B0F14",
        "scrollbar-corner-color": "#0B0F14",
        "footer-foreground": "#AFC1CC",
        "footer-background": "#111820",
        "footer-key-foreground": "#5FD7FF",
        "footer-key-background": "transparent",
        "footer-description-foreground": "#8FA3B2",
        "footer-description-background": "transparent",
        "button-foreground": "#071015",
        "button-color-foreground": "#071015",
    },
)


class StewardTUI(App):
    CSS = """
    Screen {
        background: #0B0F14;
        color: #D7E3EA;
    }

    Header {
        background: #0B0F14;
        color: #5FD7FF;
    }

    Footer {
        background: #111820;
        color: #AFC1CC;
    }

    #workspace {
        height: 1fr;
        background: #0B0F14;
    }

    #tools {
        width: 34;
        min-width: 26;
        background: #0B0F14;
        color: #D7E3EA;
        border-right: solid #355061;
        padding-right: 1;
    }

    #tools > ListItem {
        background: #0B0F14;
        color: #D7E3EA;
        padding: 0 1;
    }

    #tools > ListItem:disabled {
        background: #0B0F14;
        color: #5FD7FF;
        text-style: bold;
    }

    #tools > ListItem.-highlight {
        background: #1C2A35;
        color: #D7E3EA;
    }

    #tools:focus {
        border-right: heavy #5FD7FF;
        background-tint: transparent;
    }

    #tools:focus > ListItem.-highlight {
        background: #5FD7FF;
        color: #071015;
        text-style: bold;
    }

    #detail {
        background: #0B0F14;
        padding: 0 1;
    }

    #title {
        height: 2;
        padding: 0 1;
        text-style: bold;
        color: #5FD7FF;
        background: #111820;
    }

    #meta {
        height: 1;
        padding: 0 1;
        color: #8FA3B2;
        background: #0B0F14;
    }

    #desc {
        height: auto;
        max-height: 7;
        padding: 0 1;
        color: #AFC1CC;
        background: #0B0F14;
        overflow-y: auto;
    }

    #form {
        height: 1fr;
        min-height: 12;
        background: #0B0F14;
        border: round #355061;
        padding: 1 2;
        margin: 1 0;
    }

    #form:focus-within {
        border: round #5FD7FF;
    }

    .field {
        height: auto;
        width: 1fr;
        margin: 0 0 1 0;
        padding: 0 1 1 1;
        background: #0B0F14;
        border-bottom: solid #18242E;
    }

    .field-label {
        height: 1;
        color: #D7E3EA;
        text-style: bold;
    }

    .field-help {
        height: auto;
        color: #8FA3B2;
    }

    Input {
        width: 1fr;
        height: 3;
        border: tall #233542;
        background: #111820;
        color: #D7E3EA;
    }

    Input:focus {
        border: tall #5FD7FF;
        background: #18242E;
        color: #FFFFFF;
    }

    Input.input-error {
        border: tall #FF5F5F;
    }

    Switch:focus {
        border: tall #5FD7FF;
    }

    #invoke {
        width: 1fr;
        height: 3;
        margin: 0 0 1 0;
        background: #00A8CC;
        color: #071015;
        text-style: bold;
    }

    #invoke:hover {
        background: #4EA1D3;
        color: #071015;
    }

    #invoke:focus {
        background: #5FD7FF;
        color: #071015;
        border: heavy #D7E3EA;
        text-style: bold;
    }

    #result {
        height: 10;
        min-height: 6;
        background: #0B0F14;
        color: #D7E3EA;
        border: round #355061;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+r", "refresh", "Refresh tools"),
        ("escape", "tools", "Tools"),
        ("ctrl+enter", "invoke", "Invoke"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.specs: list[mc.ToolSpec] = []
        self.current: mc.ToolSpec | None = None
        self.inputs: dict[str, Input | Switch] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            yield ListView(id="tools")
            with Vertical(id="detail"):
                yield Static("Select a tool", id="title")
                yield Static("Enter selects · Tab moves through fields · Ctrl+Enter invokes", id="meta")
                yield Static("", id="desc")
                yield VerticalScroll(id="form")
                yield Button("Invoke", id="invoke", variant="primary", disabled=True)
                yield RichLog(id="result", wrap=True, markup=False, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        self.register_theme(K9S_DARK)
        self.theme = "k9s-dark"
        self.title = "Memory Steward — Glass Pane TUI"
        self.sub_title = mcp_url()
        self.query_one("#tools", ListView).focus()
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
            log.write(f"Cannot reach MCP at {mcp_url()}\n{type(e).__name__}: {e}")
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

    def action_tools(self) -> None:
        self.query_one("#tools", ListView).focus()

    def action_invoke(self) -> None:
        if self.current:
            self.do_invoke()

    # ---- selection + dynamic form ------------------------------------------
    @on(ListView.Selected, "#tools")
    def _select(self, event: ListView.Selected) -> None:
        name = getattr(event.item, "tool_name", None)
        if not name:
            return
        self.current = next((s for s in self.specs if s.name == name), None)
        if self.current:
            self._render_form(self.current)

    @staticmethod
    def _placeholder(fld: mc.ToolField) -> str:
        if fld.default is not None:
            return f"default: {fld.default}"
        if fld.type == "object":
            return '{"key":"value"}'
        if fld.type == "array":
            return '["value"]'
        return "required" if fld.required else "optional"

    def _render_form(self, spec: mc.ToolSpec) -> None:
        self.query_one("#title", Static).update(spec.name)
        required = [fld.name for fld in spec.fields if fld.required]
        required_text = ", ".join(required) if required else "none"
        self.query_one("#meta", Static).update(
            f"{len(spec.fields)} fields · required: {required_text} · Tab/Shift+Tab navigate · Ctrl+Enter invoke"
        )
        self.query_one("#desc", Static).update(spec.description or "(no description)")

        form = self.query_one("#form", VerticalScroll)
        form.remove_children()
        self.inputs = {}
        blocks: list[Vertical | Static] = []
        first_control: Input | Switch | None = None
        first_required: Input | Switch | None = None

        for fld in spec.fields:
            marker = " *" if fld.required else ""
            label = Label(f"{fld.name}{marker}  ({fld.type})", classes="field-label")
            children: list = [label]
            if fld.description:
                children.append(Static(fld.description, classes="field-help"))

            if fld.type == "boolean":
                control: Input | Switch = Switch(value=bool(fld.default))
            else:
                input_type = "integer" if fld.type == "integer" else "number" if fld.type == "number" else "text"
                control = Input(placeholder=self._placeholder(fld), type=input_type)

            self.inputs[fld.name] = control
            children.append(control)
            blocks.append(Vertical(*children, classes="field"))

            first_control = first_control or control
            if fld.required and first_required is None:
                first_required = control

        if blocks:
            form.mount_all(blocks)
        else:
            form.mount(Static("This tool has no parameters. Press Ctrl+Enter to invoke."))

        invoke = self.query_one("#invoke", Button)
        invoke.disabled = False

        target = first_required or first_control or invoke
        self.call_after_refresh(form.scroll_home, animate=False)
        self.call_after_refresh(target.focus)

    # ---- invocation ---------------------------------------------------------
    @on(Button.Pressed, "#invoke")
    def _invoke_pressed(self) -> None:
        self.action_invoke()

    @on(Input.Changed)
    def _input_changed(self, event: Input.Changed) -> None:
        event.input.remove_class("input-error")

    @work(exclusive=True)
    async def do_invoke(self) -> None:
        if not self.current:
            return

        log = self.query_one("#result", RichLog)
        args: dict = {}

        for fld in self.current.fields:
            widget = self.inputs[fld.name]
            try:
                if fld.type == "boolean":
                    args[fld.name] = bool(widget.value)  # type: ignore[union-attr]
                else:
                    val = mc.coerce(fld, widget.value)  # type: ignore[union-attr]
                    if val is not None:
                        args[fld.name] = val
            except ValueError as exc:
                widget.add_class("input-error")
                widget.focus()
                log.write(f"Bad input — {exc}")
                return

        log.write(f"\n> {self.current.name}({json.dumps(args, ensure_ascii=False, default=str)})")
        try:
            out = await mc.invoke_tool(self.current.name, args)
        except Exception as e:
            log.write(f"{type(e).__name__}: {e}")
            return
        log.write(out)
