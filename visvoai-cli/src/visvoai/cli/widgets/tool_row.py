"""Style B — "wired schematic" tool rendering.

A tool call is a node on a vertical box-drawing wire. Each `ToolRow`:

    {connector} {verb}  {target}                      {rail metadata} {glyph}

- **connector** (`├─` mid-cluster, `└─` last, `╶─` lone) is set by the owning
  `ToolGroup` — it shows cluster membership + where the cluster ends.
- **verb** = lowercase mapped tool name, coloured by *consequence*: reads/searches
  are muted (cheap, safe), edits/writes carry the brand accent (mutating), run is
  warning (side-effecting).
- **right-rail** = right-aligned metadata (counts · duration) + a lifecycle glyph
  (`✓` ok · `✗` failed · `⊘` stopped · spinner while running). The verb colour says
  WHAT KIND of action; the rail glyph says HOW IT WENT.

`ToolGroup` owns the wire: consecutive tool rows mount into one group so the
connectors join them; a non-tool block seals the group (the last row keeps `└─`).
"""
from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from visvoai.cli import theme

# Raw tool name → the calm lowercase verb shown in the row.
VERB_MAP = {
    "read_file": "read", "list_dir": "list", "list_files": "list",
    "list_tree": "tree", "grep": "search",
    "update_file": "edit", "edit_file": "edit", "write_file": "write", "create": "write",
    "run_shell": "run", "shell": "run",
    "web_search": "search", "web_fetch": "fetch",
}
# Raw tool name → the human DISPLAY name shown in the row (Title Case, readable) —
# distinct from the internal identifier the agent calls.
TOOL_DISPLAY = {
    "read_file": "Read", "list_files": "List", "list_dir": "List",
    "list_tree": "Tree", "grep": "Search",
    "edit_file": "Edit", "update_file": "Edit", "write_file": "Write", "create": "Write",
    "run_shell": "Bash", "shell": "Bash",
    "web_search": "Web", "web_fetch": "Fetch",
}
# Verb → palette key for the display-name colour (consequence: safe reads = calm
# `secondary` accent — coloured + readable in BOTH light/dark, not flat foreground;
# mutating = primary accent; side-effecting = warning).
_VERB_COLOR = {
    "read": "secondary", "list": "secondary", "tree": "secondary", "search": "secondary",
    "fetch": "secondary",
    "edit": "primary", "write": "primary",
    "run": "warning",
}
_NAME_W = 6  # fixed display-name column so targets align down the wire


def display_for(tool: str) -> str:
    return TOOL_DISPLAY.get(tool, tool.replace("_", " ").title())

SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
# status → (glyph, palette key). pending/running carry no static glyph (running
# animates a spinner instead); the rest are terminal.
_STATUS = {
    "complete": ("✓", "success"),
    "failed": ("✗", "error"),
    "denied": ("✗", "error"),
    "stopped": ("⊘", "muted"),
}


def verb_for(tool: str) -> str:
    return VERB_MAP.get(tool, tool)


class ToolRow(Static):
    """One node on the wire, rendered as a single justified line:
    `connector verb target` on the left, `rail glyph` pushed to the right edge.
    Right-alignment is computed from the widget width (re-rendered on resize)."""

    DEFAULT_CSS = """
    ToolRow { height: 1; padding: 0 1; }
    ToolRow.collapsible:hover { background: $hover; }
    """

    class Clicked(Message):
        pass

    def __init__(self, tool: str, target: str, rail: str = "") -> None:
        super().__init__()
        self.tool = tool
        self.verb = verb_for(tool)
        self.display_name = display_for(tool)   # NOT `display` — that's a Textual Widget prop
        self.target = target
        self.rail = rail
        self.status = "pending"
        self.connector = "╶─"   # lone by default; a ToolGroup overrides this
        self.collapsible = False
        self.collapsed = False
        self.tag: str | None = None   # faint rail tag, e.g. "auto-applied"
        self._frame = 0
        self._hover = False

    # ── state ─────────────────────────────────────────────────────────────────
    def set_status(self, status: str) -> None:
        self.status = status
        self._sync_spinner()
        self.refresh()

    def set_rail(self, rail: str) -> None:
        self.rail = rail
        self.refresh()

    def set_tag(self, tag: str | None) -> None:
        """A faint rail tag (e.g. 'auto-applied') shown before the status glyph."""
        self.tag = tag
        self.refresh()

    def set_connector(self, connector: str) -> None:
        self.connector = connector
        self.refresh()

    def set_collapsible(self, collapsible: bool) -> None:
        self.collapsible = collapsible
        self.set_class(collapsible, "collapsible")
        self.refresh()

    def set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = collapsed
        self.refresh()

    def _sync_spinner(self) -> None:
        running = self.status == "running"
        timer = getattr(self, "_timer", None)
        if running and timer is None:
            self._timer = self.set_interval(0.1, self.refresh)
        elif not running and timer is not None:
            timer.stop()
            self._timer = None

    # ── render ────────────────────────────────────────────────────────────────
    def _left(self, tv: dict) -> Text:
        t = Text()
        t.append(f"{self.connector} ", style=f"dim {tv['muted']}")
        # Display name reads first + clear (consequence-coloured, NOT muted);
        # the target/arg trails in muted so the action verb is what scans.
        name_color = tv[_VERB_COLOR.get(self.verb, "foreground")]
        t.append(self.display_name.ljust(_NAME_W), style=f"bold {name_color}")
        # On hover (only when clickable) brighten the target + hint so the
        # collapse affordance is unmistakable — mirrors the Thinking block.
        hov = self._hover and self.collapsible
        t.append(f" {self.target}", style=tv["foreground"] if hov else tv["muted"])
        if self.collapsible:
            hint = "(click to collapse)" if not self.collapsed else "(click to expand)"
            t.append(f"   {hint}", style=tv["secondary"] if hov else f"dim {tv['muted']}")
        return t

    def _right(self, tv: dict) -> Text:
        t = Text()
        if self.tag:
            t.append(f"{self.tag}  ", style=f"dim {tv['secondary']}")
        if self.rail:
            t.append(self.rail, style=tv["muted"])
        if self.status == "running":
            self._frame += 1
            t.append(f"  {SPINNER[self._frame % len(SPINNER)]}", style=tv["secondary"])
        elif self.status in _STATUS:
            glyph, key = _STATUS[self.status]
            t.append(f"  {glyph}", style=tv[key])
        return t

    def render(self) -> Text:
        tv = theme.palette(self)
        left, right = self._left(tv), self._right(tv)
        # Right-justify the rail: pad between left and right to the content width
        # (minus the row's 1-cell horizontal padding each side).
        width = (self.size.width or 80) - 2
        gap = max(1, width - left.cell_len - right.cell_len)
        out = left.copy()
        out.append(" " * gap)
        out.append_text(right)
        return out

    def on_resize(self) -> None:
        self.refresh()  # rail right-alignment depends on width

    def restyle(self) -> None:
        self.refresh()

    def on_enter(self, event) -> None:
        if self.collapsible:
            self._hover = True
            self.refresh()

    def on_leave(self, event) -> None:
        if self._hover:
            self._hover = False
            self.refresh()

    def on_click(self) -> None:
        if self.collapsible:
            self.post_message(self.Clicked())

    def stop(self) -> None:
        timer = getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()
            self._timer = None

    def on_unmount(self) -> None:
        self.stop()


class ToolErrorBody(Static):
    """A lean failure body: tool stdout (dim) then the error line(s) (red), no
    labels — the red ✗ on the row header already says 'this failed'."""

    can_focus = False
    MAX = 12

    DEFAULT_CSS = "ToolErrorBody { height: auto; }"

    def __init__(self, output, error) -> None:
        super().__init__()
        self.output = list(output or [])
        self.error = [error] if isinstance(error, str) else list(error or [])

    def render(self) -> Text:
        tv = theme.palette(self)
        rows: list[Text] = []
        for ln in self.output[: self.MAX]:
            rows.append(Text(ln, style=tv["muted"]))
        if len(self.output) > self.MAX:
            rows.append(Text(f"… +{len(self.output) - self.MAX} more", style=f"dim {tv['muted']}"))
        for ln in self.error:
            rows.append(Text(ln, style=tv["error"]))
        return Text("\n").join(rows)

    def restyle(self) -> None:
        self.refresh()


class ToolNode(Vertical):
    """A wired tool unit: a `ToolRow` header + an optional collapsible body. The
    body indents under the wire and, when expanded, sits on a subtle bg panel so
    it reads as a contained section. API: set_status / set_rail / set_body /
    set_collapsed / set_failure / mark_auto_applied."""

    DEFAULT_CSS = """
    ToolNode { background: transparent; height: auto; margin: 0; }
    /* Body indents under the verb/target zone; always transparent so it blends
       with the terminal background, like the rest of the app. Only the left indent
       — no interior padding. */
    ToolNode > .tn-body { height: auto; padding: 0 0 0 5; background: transparent; }
    /* Expanded: a single blank line below to separate from the next row. */
    ToolNode.expanded > .tn-body { margin: 0 0 1 0; }
    """

    def __init__(self, tool: str, target: str, rail: str = "") -> None:
        super().__init__()
        self.row = ToolRow(tool, target, rail)
        self._body: Widget | None = None

    def compose(self) -> ComposeResult:
        yield self.row

    # ── delegates to the header row ───────────────────────────────────────────
    def set_status(self, status: str) -> None:
        self.row.set_status(status)

    def set_rail(self, rail: str) -> None:
        self.row.set_rail(rail)

    def set_connector(self, connector: str) -> None:
        self.row.set_connector(connector)

    def mark_auto_applied(self, label: str = "auto-applied") -> None:
        self.row.set_status("complete")
        self.row.set_tag(label)

    # ── body ──────────────────────────────────────────────────────────────────
    async def set_body(self, body: Widget, collapsed: bool = False) -> None:
        if self._body is not None and self._body.is_mounted:
            await self._body.remove()
        body.add_class("tn-body")
        self._body = body
        self.row.set_collapsible(True)
        await self.mount(body)
        self.set_collapsed(collapsed)

    async def set_failure(self, output, error, status: str = "failed") -> ToolErrorBody:
        """Attach a lean output+error body and mark the row failed — the failure
        belongs to the tool (no orphaned error block)."""
        self.row.set_status(status)
        body = ToolErrorBody(output, error)
        await self.set_body(body, collapsed=False)
        return body

    def set_collapsed(self, collapsed: bool) -> None:
        if self._body is None:
            return
        self.row.set_collapsed(collapsed)
        self._body.display = not collapsed
        self.set_class(not collapsed, "expanded")
        self.refresh(layout=True)

    def on_tool_row_clicked(self, msg: ToolRow.Clicked) -> None:
        msg.stop()
        if self._body is None:
            return
        self.set_collapsed(not self.row.collapsed)


class ToolGroup(Vertical):
    """Owns the wire for a cluster of tool units. `add(item)` joins a `ToolRow` or
    `ToolNode` to the wire; the group keeps `├─` on every item except the last,
    which gets `└─`. A lone item (group of one) reads as a single `└─` leaf."""

    DEFAULT_CSS = """
    ToolGroup { background: transparent; height: auto; margin: 0; padding: 0; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._items: list = []   # ToolRow | ToolNode (both have set_connector)

    async def add(self, item):
        self._items.append(item)
        await self.mount(item)
        self._rewire()
        return item

    def _rewire(self) -> None:
        # A lone row is a single-line leaf `╶─`. In a multi-row cluster the first
        # row OPENS the wire downward with `┌─` (down+right) so it connects into the
        # ├─ below it; the `└─` corner closes the bottom.
        n = len(self._items)
        for i, item in enumerate(self._items):
            if n == 1:
                conn = "╶─"
            elif i == 0:
                conn = "┌─"
            elif i == n - 1:
                conn = "└─"
            else:
                conn = "├─"
            item.set_connector(conn)

    def rows(self) -> list:
        return list(self._items)
